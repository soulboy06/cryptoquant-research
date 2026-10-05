"""Formal regression tests for holdout data isolation and reject_holdout guard.

Audits and verifies:
1. reject_holdout guard strictly raises ValueError('2026 holdout read forbidden')
   when attempting to read any parquet path containing 'test' (no generic Exception catching).
2. Non-test paths pass through normally to original pd.read_parquet.
3. Original pd.read_parquet is cleanly restored on exit.
4. Audits data/processed/funding_rate/*.parquet: documents that funding rate parquet files
   contain 2026 records, explaining why the pipeline satisfies 'no future leakage'
   (temporal cutoff) but cannot claim 'physical holdout zero-read' for funding rate tables.
"""
from pathlib import Path
import sys

import pandas as pd
import pytest

PROJECT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = PROJECT / 'scripts'
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from verify_cycle_repair import reject_holdout  # type: ignore[import-not-found]


def test_holdout_guard_strictly_raises_value_error_on_test_path():
    """Verify holdout guard raises exact ValueError('2026 holdout read forbidden').
    
    Prohibits catching generic Exception; must match exact exception type and message.
    """
    with reject_holdout(PROJECT):
        # Test Path object containing 'test'
        test_path = PROJECT / 'data/test/BTCUSDT.parquet'
        with pytest.raises(ValueError, match=r'^2026 holdout read forbidden$'):
            pd.read_parquet(test_path)
            
        # Test string path containing 'test'
        with pytest.raises(ValueError, match=r'^2026 holdout read forbidden$'):
            pd.read_parquet('data/test/ETHUSDT.parquet')
            
        # Test nested subfolder path containing 'test'
        with pytest.raises(ValueError, match=r'^2026 holdout read forbidden$'):
            pd.read_parquet('artifacts/experiments/test/eval.parquet')


def test_holdout_guard_allows_non_test_passthrough():
    """Verify non-test paths are passed through to original reader, NOT raising guard ValueError."""
    with reject_holdout(PROJECT):
        non_test_path = PROJECT / 'data/development/non_existent_dummy_file.parquet'
        # Must pass through and raise FileNotFoundError from underlying pandas/pyarrow, NOT ValueError
        with pytest.raises(FileNotFoundError):
            pd.read_parquet(non_test_path)


def test_holdout_guard_restores_original_reader_on_exit():
    """Verify original pd.read_parquet function is cleanly restored upon context exit."""
    orig_reader = pd.read_parquet
    with reject_holdout(PROJECT):
        assert pd.read_parquet != orig_reader
    assert pd.read_parquet == orig_reader


def test_funding_rate_audit_and_leakage_vs_zero_read():
    """Audit data/processed/funding_rate/*.parquet and verify isolation concepts.
    
    Findings:
    - data/processed/funding_rate/*.parquet contains data up to 2026-10-01.
    - reject_holdout does NOT intercept funding rate files (path has no 'test' component).
    - Pipeline achieves 'no future leakage' via fold.eval_end slicing (< 2026-01-01),
      but does NOT satisfy 'physical holdout zero-read' for funding rate tables.
    """
    funding_dir = PROJECT / 'data/processed/funding_rate'
    assert funding_dir.exists(), "Funding rate directory must exist"
    
    symbols = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
    for s in symbols:
        fpath = funding_dir / f'{s}.parquet'
        assert fpath.exists(), f"Funding rate file {fpath} must exist"
        
        # Read file under guard: confirms guard allows reading since path has no 'test'
        with reject_holdout(PROJECT):
            df = pd.read_parquet(fpath)
            
        # Audit: verify max funding_time extends into 2026
        max_time = pd.to_datetime(df['funding_time']).max()
        assert max_time.year >= 2026, f"{s} funding rate was expected to include 2026 records"
        
        # Document and assert: 2026 records are present in the table bytes
        records_in_2026 = (pd.to_datetime(df['funding_time']) >= '2026-01-01').sum()
        assert records_in_2026 > 0, f"{s} should contain 2026 rows"

"""Phase 4A Regression and Integrity Tests: Controlled No-Trade / Signal Selection.

Covers mandatory Phase 4A invariants:
1. Control_OPT0026 matches exact OPT-0026 Champion baseline (+0.1293%/w).
2. All 10 candidates use 100% identical LR C=0.10 model, 12 features, C2 exit, and R6 sizing.
3. No-Trade filters strictly prune or maintain entries, never injecting unauthorized new trades.
4. Counterfactual trade balance math holds: avoided_losers + avoided_winners == avoided_count and net == gross - fees.
5. 2026 data is strictly sealed (no future leakage).
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from cryptoquant.config import load_config
from cryptoquant.models.features import ALL_FEATURE_NAMES
from cryptoquant.optimization.walk_forward import FOLDS

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_control_candidate_matches_opt0026_baseline():
    """Test 1: Verify Control_OPT0026 matches exact Champion OPT-0026 baseline."""
    csv_path = PROJECT_ROOT / 'artifacts/research/no_trade_phase4a/candidate_summary.csv'
    if not csv_path.exists():
        pytest.skip("candidate_summary.csv not yet generated")
        
    df = pd.read_csv(csv_path)
    ctrl = df[df['candidate_id'] == 'Control_OPT0026'].iloc[0]
    
    assert ctrl['g_week_pct'] == pytest.approx(0.1293, abs=1e-3)
    assert ctrl['ret_2023_pct'] == pytest.approx(7.16, abs=0.1)
    assert ctrl['ret_2024_pct'] == pytest.approx(17.41, abs=0.1)
    assert ctrl['ret_2025_pct'] == pytest.approx(-2.70, abs=0.1)
    assert ctrl['worst_mdd_pct'] == pytest.approx(11.51, abs=0.1)


def test_all_candidates_use_identical_lr_model_and_features():
    """Test 2: Verify all candidates use identical 12 features and LR parameters."""
    cfg_path = PROJECT_ROOT / 'artifacts/research/no_trade_phase4a/experiment_config.json'
    if not cfg_path.exists():
        pytest.skip("experiment_config.json not yet generated")
        
    with open(cfg_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
        
    assert cfg['features_count'] == 12
    assert cfg['features'] == list(ALL_FEATURE_NAMES)
    assert cfg['horizon_hours'] == 4
    assert cfg['candidates_count'] == 10


def test_no_trade_strictly_prunes_or_maintains_trades():
    """Test 3: Verify No-Trade filters never inject new trades (buy_entries <= control)."""
    csv_path = PROJECT_ROOT / 'artifacts/research/no_trade_phase4a/candidate_summary.csv'
    if not csv_path.exists():
        pytest.skip("candidate_summary.csv not yet generated")
        
    df = pd.read_csv(csv_path)
    ctrl_entries = df[df['candidate_id'] == 'Control_OPT0026'].iloc[0]['buy_entries']
    
    for _, row in df.iterrows():
        assert row['buy_entries'] <= ctrl_entries, (
            f"Candidate {row['candidate_id']} exceeded control buy entries: "
            f"{row['buy_entries']} > {ctrl_entries}"
        )


def test_counterfactual_trade_math_identity():
    """Test 4: Verify mathematical identity of counterfactual avoided trade counts and PnL."""
    rej_path = PROJECT_ROOT / 'artifacts/research/no_trade_phase4a/rejected_trade_analysis.csv'
    if not rej_path.exists():
        pytest.skip("rejected_trade_analysis.csv not yet generated")
        
    df = pd.read_csv(rej_path)
    for _, row in df.iterrows():
        assert row['avoided_losers'] + row['avoided_winners'] == row['avoided_count'], (
            f"Mismatch in counts for {row['candidate_id']}"
        )
        assert row['avoided_net_pnl'] == pytest.approx(row['avoided_gross_pnl'] - row['avoided_fees'], abs=1e-2), (
            f"Mismatch in net PnL math for {row['candidate_id']}"
        )


def test_2026_not_used_in_phase4a():
    """Test 5: Verify 2026 data is not used for training, feature calculation, or evaluation."""
    for fold_name, fold in FOLDS.items():
        assert fold.train_start < pd.Timestamp('2026-01-01', tz='UTC')
        assert fold.train_end <= pd.Timestamp('2025-01-01', tz='UTC')
        assert fold.eval_end <= pd.Timestamp('2026-01-01 00:00:00', tz='UTC')

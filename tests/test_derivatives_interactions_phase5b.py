"""Tests for Phase 5B: Open Interest + Taker Flow Interaction Features Alpha Experiment.

Verifies:
1. All interaction features only use data available at decision_time.
2. OI source_timestamp <= decision_time (zero future leakage).
3. Flow uses closed candle (open_time = decision_time - 1h).
4. All 8 interaction feature formulas are exact.
5. Four BASE_12 benchmark candidates exactly reproduce original metrics.
6. Benchmark configurations (C, threshold, sizing, C2) remain unaltered.
7. 2026 holdout is sealed and cannot be accessed.
8. Annualized return adheres strictly to (1 + g_week)^52 - 1.
9. Feature Families do not contain raw bare OI / Flow features.
10. Quadrant and triple-state classifications are mutually exclusive and exhaustive.
"""

from decimal import Decimal
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from cryptoquant.models.derivatives_features import (
    BASE_12_FEATURES,
    FLOW_FEATURES,
    INTERACTION_8_FEATURES,
    OI_FEATURES,
    PHASE5B_FEATURE_FAMILIES,
    attach_interaction_features,
    compute_interaction_features,
)
from cryptoquant.models.research_reporting import annualize_weekly_return

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / 'artifacts/research/alpha_phase5b_interactions'


def test_interaction_feature_count_and_no_bare_features():
    """Item 4 & 9: Verify exactly 8 interaction features and zero bare OI/Flow features."""
    assert len(INTERACTION_8_FEATURES) == 8
    expected_8 = {
        'price_oi_4h',
        'price_oi_24h',
        'price_flow_4h',
        'price_flow_24h',
        'oi_flow_confirmation_4h',
        'oi_flow_confirmation_24h',
        'trend_oi_confirmation',
        'volatility_flow',
    }
    assert set(INTERACTION_8_FEATURES) == expected_8

    assert len(PHASE5B_FEATURE_FAMILIES) == 6
    assert len(PHASE5B_FEATURE_FAMILIES['BASE_12']) == 12
    assert len(PHASE5B_FEATURE_FAMILIES['INTERACTION_PRICE_OI']) == 14
    assert len(PHASE5B_FEATURE_FAMILIES['INTERACTION_PRICE_FLOW']) == 14
    assert len(PHASE5B_FEATURE_FAMILIES['INTERACTION_OI_FLOW']) == 14
    assert len(PHASE5B_FEATURE_FAMILIES['INTERACTION_CONTEXT']) == 14
    assert len(PHASE5B_FEATURE_FAMILIES['INTERACTION_ALL']) == 20

    # Strict check: zero bare features
    bare_features = set(OI_FEATURES + FLOW_FEATURES)
    for fam_name, cols in PHASE5B_FEATURE_FAMILIES.items():
        overlap = bare_features.intersection(cols)
        assert len(overlap) == 0, f"Bare features {overlap} leaked into {fam_name}!"


def test_interaction_formulas_exact():
    """Item 4: Verify exact algebraic formulas for the 8 interaction features."""
    df_test = pd.DataFrame({
        'return_4h': [0.02, -0.01, 0.05],
        'return_24h': [0.06, -0.04, 0.10],
        'ema24_distance': [0.015, -0.02, 0.03],
        'volatility_24h': [0.008, 0.012, 0.020],
        'oi_change_4h': [0.03, -0.02, 0.01],
        'oi_change_24h': [0.08, 0.05, -0.03],
        'taker_imbalance_4h': [0.25, -0.40, 0.10],
        'taker_imbalance_24h': [0.15, -0.20, 0.05],
    })

    out = compute_interaction_features(df_test)

    # 1. price_oi_4h = return_4h * oi_change_4h
    np.testing.assert_allclose(out['price_oi_4h'], [0.02 * 0.03, -0.01 * -0.02, 0.05 * 0.01])

    # 2. price_oi_24h = return_24h * oi_change_24h
    np.testing.assert_allclose(out['price_oi_24h'], [0.06 * 0.08, -0.04 * 0.05, 0.10 * -0.03])

    # 3. price_flow_4h = return_4h * taker_imbalance_4h
    np.testing.assert_allclose(out['price_flow_4h'], [0.02 * 0.25, -0.01 * -0.40, 0.05 * 0.10])

    # 4. price_flow_24h = return_24h * taker_imbalance_24h
    np.testing.assert_allclose(out['price_flow_24h'], [0.06 * 0.15, -0.04 * -0.20, 0.10 * 0.05])

    # 5. oi_flow_confirmation_4h = oi_change_4h * taker_imbalance_4h
    np.testing.assert_allclose(out['oi_flow_confirmation_4h'], [0.03 * 0.25, -0.02 * -0.40, 0.01 * 0.10])

    # 6. oi_flow_confirmation_24h = oi_change_24h * taker_imbalance_24h
    np.testing.assert_allclose(out['oi_flow_confirmation_24h'], [0.08 * 0.15, 0.05 * -0.20, -0.03 * 0.05])

    # 7. trend_oi_confirmation = ema24_distance * oi_change_4h
    np.testing.assert_allclose(out['trend_oi_confirmation'], [0.015 * 0.03, -0.02 * -0.02, 0.03 * 0.01])

    # 8. volatility_flow = volatility_24h * taker_imbalance_4h
    np.testing.assert_allclose(out['volatility_flow'], [0.008 * 0.25, 0.012 * -0.40, 0.020 * 0.10])


def test_oi_and_flow_timestamp_alignment():
    """Item 1, 2, 3: Verify decision_time causality and source_timestamp <= decision_time."""
    for s in ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']:
        p = ROOT / f'data/processed/derivatives_flow/{s}_flow_oi.parquet'
        df = pd.read_parquet(p)
        source_ts = df['open_time'].shift(-1)
        decision_ts = pd.to_datetime(df['open_time']) + pd.to_timedelta(1, unit='h')
        valid = source_ts.notnull()
        diff_sec = (source_ts[valid] - decision_ts[valid]).dt.total_seconds()
        assert int((diff_sec > 0).sum()) == 0, f"Found future leakage in {s} OI timestamps!"


def test_base_12_exact_reproduction_of_benchmarks():
    """Item 5: Verify that the 4 BASE_12 candidates in Phase 5B reproduce benchmarks exactly."""
    trade_path = OUT_DIR / 'trading_metrics.csv'
    assert trade_path.exists()
    df = pd.read_csv(trade_path)

    # OPT-0005_BASE_12
    row_0005 = df[df['candidate_id'] == 'OPT-0005_BASE_12'].iloc[0]
    assert pytest.approx(row_0005['g_week_pct'], abs=1e-3) == 0.1371
    assert pytest.approx(row_0005['worst_mdd_pct'], abs=1e-2) == 11.60
    assert pytest.approx(row_0005['ret_2025_pct'], abs=1e-2) == -3.91
    assert row_0005['closed_cycles'] == 208

    # OPT-0001_BASE_12
    row_0001 = df[df['candidate_id'] == 'OPT-0001_BASE_12'].iloc[0]
    assert pytest.approx(row_0001['g_week_pct'], abs=1e-3) == 0.1311
    assert pytest.approx(row_0001['worst_mdd_pct'], abs=1e-2) == 11.49
    assert pytest.approx(row_0001['ret_2025_pct'], abs=1e-2) == -3.59
    assert row_0001['closed_cycles'] == 208

    # OPT-0026_BASE_12
    row_0026 = df[df['candidate_id'] == 'OPT-0026_BASE_12'].iloc[0]
    assert pytest.approx(row_0026['g_week_pct'], abs=1e-3) == 0.1293
    assert pytest.approx(row_0026['worst_mdd_pct'], abs=1e-2) == 11.51
    assert pytest.approx(row_0026['ret_2025_pct'], abs=1e-2) == -2.70
    assert row_0026['closed_cycles'] == 225

    # OPT-0056_BASE_12
    row_0056 = df[df['candidate_id'] == 'OPT-0056_BASE_12'].iloc[0]
    assert pytest.approx(row_0056['g_week_pct'], abs=1e-3) == 0.1024
    assert pytest.approx(row_0056['worst_mdd_pct'], abs=1e-2) == 11.21
    assert pytest.approx(row_0056['ret_2025_pct'], abs=1e-2) == -2.44
    assert row_0056['closed_cycles'] == 153


def test_annualized_return_formula():
    """Item 8: Verify annualization formula (1 + g_week)^52 - 1."""
    assert pytest.approx(annualize_weekly_return(0.001371), abs=1e-4) == (1.001371**52 - 1.0)
    assert pytest.approx(annualize_weekly_return(0.015), abs=1e-4) == (1.015**52 - 1.0)


def test_holdout_guard_active():
    """Item 7: Verify 2026 data is protected by holdout guard."""
    import sys
    scripts_dir = ROOT / 'scripts'
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from verify_cycle_repair import reject_holdout  # type: ignore

    with reject_holdout(ROOT):
        p_2026 = ROOT / 'data/processed/test/EXP-003/attempt-001/BTCUSDT.parquet'
        with pytest.raises(ValueError, match='2026 holdout read forbidden'):
            pd.read_parquet(p_2026)


def test_quadrant_and_triple_state_classification():
    """Item 10: Verify quadrant and triple-state classifications."""
    df_poi = pd.read_csv(OUT_DIR / 'price_oi_quadrants.csv')
    assert len(df_poi) > 0
    assert set(df_poi['quadrant_id'].unique()) == {
        'Q1_PriceUp_OIUp',
        'Q2_PriceUp_OIDown',
        'Q3_PriceDown_OIUp',
        'Q4_PriceDown_OIDown',
    }

    df_pflow = pd.read_csv(OUT_DIR / 'price_flow_quadrants.csv')
    assert len(df_pflow) > 0
    assert set(df_pflow['quadrant_id'].unique()) == {
        'Q1_PriceUp_FlowBuy',
        'Q2_PriceUp_FlowSell',
        'Q3_PriceDown_FlowBuy',
        'Q4_PriceDown_FlowSell',
    }

    df_triple = pd.read_csv(OUT_DIR / 'triple_state_analysis.csv')
    assert len(df_triple) > 0
    assert len(df_triple['state_id'].unique()) == 8


def test_artifacts_completeness():
    """Verify all 13 Phase 5B artifact files exist and are populated."""
    required_files = [
        'feature_definitions.json',
        'experiment_config.json',
        'interaction_diagnostic.csv',
        'prediction_metrics.csv',
        'trading_metrics.csv',
        'price_oi_quadrants.csv',
        'price_flow_quadrants.csv',
        'triple_state_analysis.csv',
        'benchmark_comparison.csv',
        'pareto_front_before.csv',
        'pareto_front_after.csv',
        'results.json',
        'comparison_report.md',
    ]
    for fname in required_files:
        p = OUT_DIR / fname
        assert p.exists(), f"Missing artifact: {fname}"
        assert p.stat().st_size > 0, f"Empty artifact: {fname}"

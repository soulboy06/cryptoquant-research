"""Tests for Phase 5A Open Interest + Taker Flow Controlled Ablation Experiment.

Verifies:
1. New features only use past data (no future leakage).
2. Rolling/zscore has no future leakage.
3. Feature family column counts match specifications exactly.
4. BASE_12 candidates exactly reproduce the four Pareto benchmarks.
5. Benchmark configurations are unchanged.
6. 2026 data is not read or evaluated during optimization / walk-forward.
7. Annualized return adheres strictly to (1 + g_week)^52 - 1.
"""

from decimal import Decimal
import json
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from cryptoquant.models.derivatives_features import (
    BASE_12_FEATURES,
    FEATURE_FAMILIES,
    FLOW_FEATURES,
    OI_FEATURES,
    build_derivatives_features_for_symbol,
)
from cryptoquant.models.research_reporting import annualize_weekly_return


ROOT = Path(__file__).resolve().parent.parent


def test_feature_family_column_counts():
    """Requirement 3: Verify feature column counts."""
    assert len(OI_FEATURES) == 3
    assert set(OI_FEATURES) == {'oi_change_4h', 'oi_change_24h', 'oi_zscore_72h'}

    assert len(FLOW_FEATURES) == 4
    assert set(FLOW_FEATURES) == {
        'taker_imbalance_1h',
        'taker_imbalance_4h',
        'taker_imbalance_24h',
        'taker_imbalance_zscore_72h',
    }

    assert len(FEATURE_FAMILIES['BASE_12']) == 12
    assert len(FEATURE_FAMILIES['OI_ONLY']) == 15
    assert len(FEATURE_FAMILIES['FLOW_ONLY']) == 16
    assert len(FEATURE_FAMILIES['OI_FLOW']) == 19

    feat_def_path = ROOT / 'artifacts/research/alpha_phase5a_derivatives_flow/feature_definitions.json'
    assert feat_def_path.exists()
    defs = json.loads(feat_def_path.read_text(encoding='utf-8'))
    assert len(defs['feature_families']['BASE_12']['columns']) == 12
    assert len(defs['feature_families']['OI_ONLY']['columns']) == 15
    assert len(defs['feature_families']['FLOW_ONLY']['columns']) == 16
    assert len(defs['feature_families']['OI_FLOW']['columns']) == 19


def test_no_future_leakage_in_feature_construction(tmp_path):
    """Requirement 1 & 2: Verify shifting and rolling use only historical bars."""
    # Synthetic dataset with 200 bars
    rng = np.random.default_rng(42)
    dates = pd.date_range('2023-01-01', periods=200, freq='h', tz='UTC')
    df = pd.DataFrame({
        'open_time': dates,
        'taker_buy_quote_volume': rng.uniform(100, 500, size=200),
        'total_quote_volume': rng.uniform(600, 1000, size=200),
        'taker_imbalance': rng.uniform(-0.5, 0.5, size=200),
        'sum_open_interest_ffill': rng.uniform(1000, 2000, size=200),
    })

    # Save original
    df.to_parquet(tmp_path / 'TEST_flow_oi.parquet')
    feat_orig = build_derivatives_features_for_symbol('TEST', data_dir=tmp_path)

    # Modify future row at index 100
    df_mod = df.copy()
    df_mod.loc[100, 'taker_buy_quote_volume'] = 9999999.0
    df_mod.loc[100, 'total_quote_volume'] = 9999999.0
    df_mod.loc[100, 'taker_imbalance'] = 1.0
    df_mod.loc[100, 'sum_open_interest_ffill'] = 9999999.0

    df_mod.to_parquet(tmp_path / 'TEST_flow_oi.parquet')
    feat_mod = build_derivatives_features_for_symbol('TEST', data_dir=tmp_path)

    # All decision rows strictly prior to index 100 (decision_time <= dates[99] + 1h) must be completely identical
    cutoff_time = dates[98] + pd.Timedelta(hours=1)
    orig_sub = feat_orig[feat_orig['decision_time'] <= cutoff_time].reset_index(drop=True)
    mod_sub = feat_mod[feat_mod['decision_time'] <= cutoff_time].reset_index(drop=True)
    pd.testing.assert_frame_equal(orig_sub, mod_sub)


def test_annualized_return_formula():
    """Requirement 7: Verify annualized return formula (1 + g_week)^52 - 1."""
    # Benchmark g_weeks
    g_0005 = 0.001371
    ann_0005 = annualize_weekly_return(g_0005)
    expected_0005 = (1.0 + g_0005) ** 52 - 1.0
    assert ann_0005 is not None and abs(ann_0005 - expected_0005) < 1e-6

    g_0056 = 0.001024
    ann_0056 = annualize_weekly_return(g_0056)
    expected_0056 = (1.0 + g_0056) ** 52 - 1.0
    assert ann_0056 is not None and abs(ann_0056 - expected_0056) < 1e-6


def test_base_12_exact_reproduction_of_benchmarks():
    """Requirement 4 & 5: Verify BASE_12 exact match with Pareto benchmarks."""
    trades_path = ROOT / 'artifacts/research/alpha_phase5a_derivatives_flow/trading_metrics.csv'
    assert trades_path.exists()
    df = pd.read_csv(trades_path)

    # OPT-0005
    r5 = df[df['candidate_id'] == 'OPT-0005_BASE_12'].iloc[0]
    assert abs(r5['g_week_pct'] - 0.1371) < 1e-3
    assert abs(r5['annualized_return_pct'] - 7.38) < 1e-1
    assert abs(r5['worst_mdd_pct'] - 11.60) < 1e-1

    # OPT-0001
    r1 = df[df['candidate_id'] == 'OPT-0001_BASE_12'].iloc[0]
    assert abs(r1['g_week_pct'] - 0.1311) < 1e-3
    assert abs(r1['annualized_return_pct'] - 7.05) < 1e-1
    assert abs(r1['worst_mdd_pct'] - 11.49) < 1e-1

    # OPT-0026
    r26 = df[df['candidate_id'] == 'OPT-0026_BASE_12'].iloc[0]
    assert abs(r26['g_week_pct'] - 0.1293) < 1e-3
    assert abs(r26['annualized_return_pct'] - 6.95) < 1e-1
    assert abs(r26['worst_mdd_pct'] - 11.51) < 1e-1

    # OPT-0056
    r56 = df[df['candidate_id'] == 'OPT-0056_BASE_12'].iloc[0]
    assert abs(r56['g_week_pct'] - 0.1024) < 1e-3
    assert abs(r56['annualized_return_pct'] - 5.47) < 1e-1
    assert abs(r56['worst_mdd_pct'] - 11.21) < 1e-1


def test_benchmark_configs_unaltered():
    """Requirement 5: Verify the 4 benchmark configurations are frozen."""
    cfg_path = ROOT / 'artifacts/research/alpha_phase5a_derivatives_flow/experiment_config.json'
    assert cfg_path.exists()
    config = json.loads(cfg_path.read_text(encoding='utf-8'))
    benchmarks = config['benchmarks']

    assert benchmarks['OPT-0005']['model_params']['C'] == 0.05
    assert benchmarks['OPT-0005']['threshold'] == 0.48

    assert benchmarks['OPT-0001']['model_params']['C'] == 0.05
    assert benchmarks['OPT-0001']['threshold'] == 0.48

    assert benchmarks['OPT-0026']['model_params']['C'] == 0.10
    assert benchmarks['OPT-0026']['threshold'] == 0.48

    assert benchmarks['OPT-0056']['model_params']['C'] == 0.50
    assert benchmarks['OPT-0056']['threshold'] == 0.50


def test_holdout_guard_active():
    """Requirement 6: Verify 2026 data is protected by holdout guard."""
    import sys
    scripts_dir = ROOT / 'scripts'
    if str(scripts_dir) not in sys.path:
        sys.path.insert(0, str(scripts_dir))
    from verify_cycle_repair import reject_holdout

    with reject_holdout(ROOT):
        p_2026 = ROOT / 'data/processed/test/EXP-003/attempt-001/BTCUSDT.parquet'
        with pytest.raises(ValueError, match='2026 holdout read forbidden'):
            pd.read_parquet(p_2026)

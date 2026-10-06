"""Unit tests for Phase 5B2: INTERACTION_CONTEXT Yield Source & Robustness Audit."""

from decimal import Decimal
import json
from pathlib import Path
import pytest
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
AUDIT_DIR = PROJECT / 'artifacts/research/alpha_phase5b2_context_audit'


def test_audit_artifacts_completeness():
    """Verify all 8 mandatory Phase 5B2 audit artifacts exist."""
    required_files = [
        'audit_summary.json',
        'cycle_comparison.csv',
        'trade_level_attribution.csv',
        'monthly_performance_breakdown.csv',
        'cost_stress_test.csv',
        'threshold_region_diagnostics.csv',
        'block_bootstrap_results.json',
        'audit_report.md',
    ]
    for fn in required_files:
        p = AUDIT_DIR / fn
        assert p.exists(), f"Missing required audit artifact: {fn}"
        assert p.stat().st_size > 0, f"Artifact {fn} is empty"


def test_baseline_and_challenger_replication():
    """Verify Control and Challenger metrics are replicated with zero drift."""
    with open(AUDIT_DIR / 'audit_summary.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    ctrl = data['baseline_control']
    chal = data['challenger']

    # OPT-0005 BASE_12 exact metrics
    assert ctrl['candidate_id'] == 'OPT-0005_BASE_12'
    assert abs(ctrl['g_week_pct'] - 0.1371) < 1e-3
    assert abs(ctrl['annualized_pct'] - 7.38) < 1e-1
    assert ctrl['closed_cycles'] == 208
    assert abs(ctrl['total_fees_usdt'] - 10.03) < 1e-1

    # OPT-0005 INTERACTION_CONTEXT exact metrics
    assert chal['candidate_id'] == 'OPT-0005_INTERACTION_CONTEXT'
    assert abs(chal['g_week_pct'] - 0.1453) < 1e-3
    assert abs(chal['annualized_pct'] - 7.84) < 1e-1
    assert chal['closed_cycles'] == 222
    assert abs(chal['total_fees_usdt'] - 10.75) < 1e-1

    # Delta g_week
    assert abs(data['delta_g_week_bps'] - 0.82) < 1e-2


def test_cycle_alignment_and_attribution_conservation():
    """Verify trade cycles sum to exact difference and counts match."""
    df_cycles = pd.read_csv(AUDIT_DIR / 'cycle_comparison.csv')
    df_attr = pd.read_csv(AUDIT_DIR / 'trade_level_attribution.csv')

    # Total matched records
    assert len(df_cycles) > 0

    # Total attribution delta PnL matches net profit difference
    with open(AUDIT_DIR / 'audit_summary.json', 'r', encoding='utf-8') as f:
        summary = json.load(f)
    tot_delta = summary['delta_net_profit_usdt']

    sum_attr_delta = df_attr['delta_pnl_usdt'].sum()
    assert abs(sum_attr_delta - tot_delta) < 0.05, f"Attribution mismatch: {sum_attr_delta} vs {tot_delta}"


def test_monthly_concentration_anomaly():
    """Verify that excess return is heavily concentrated in Nov 2023."""
    df_monthly = pd.read_csv(AUDIT_DIR / 'monthly_performance_breakdown.csv')
    assert len(df_monthly) == 36, f"Expected 36 months, got {len(df_monthly)}"

    nov_2023 = df_monthly[df_monthly['month'] == '2023-11']
    assert len(nov_2023) == 1
    nov_pnl = float(nov_2023.iloc[0]['delta_pnl_usdt'])

    # Nov 2023 excess PnL is greater than the total 3-year excess PnL (> 100% share)
    with open(AUDIT_DIR / 'audit_summary.json', 'r', encoding='utf-8') as f:
        summary = json.load(f)
    tot_delta = summary['delta_net_profit_usdt']
    assert nov_pnl > tot_delta, f"Nov 2023 PnL {nov_pnl} should exceed total delta {tot_delta}"


def test_cost_stress_testing_scenarios():
    """Verify all 3 pre-frozen cost stress testing scenarios are recorded."""
    df_stress = pd.read_csv(AUDIT_DIR / 'cost_stress_test.csv')
    assert len(df_stress) == 3
    scenarios = set(df_stress['cost_scenario'])
    assert scenarios == {'1.0x_Base', '1.5x_Cost', '2.0x_Cost'}

    # 2.0x cost should significantly reduce annualized yield
    row_2x = df_stress[df_stress['cost_scenario'] == '2.0x_Cost'].iloc[0]
    assert row_2x['chal_annualized_pct'] < 4.0, "Annualized return at 2.0x should be under 4%"
    assert row_2x['chal_fees_usdt'] > 18.0, "Total fees at 2.0x should exceed 18 USDT"


def test_block_bootstrap_not_statistically_significant():
    """Verify that Block Bootstrap 95% CI includes zero and p-value is not significant."""
    with open(AUDIT_DIR / 'block_bootstrap_results.json', 'r', encoding='utf-8') as f:
        boot = json.load(f)

    # 4w, 8w, 12w block bootstrap
    for b in ['block_size_4w', 'block_size_8w', 'block_size_12w']:
        res = boot[b]
        assert res['ci_contains_zero'] is True, f"Block {b} CI should contain zero"
        assert res['statistically_significant_at_005'] is False, f"Block {b} should NOT be significant"
        assert res['p_value_one_sided_le_zero'] > 0.20, f"Block {b} p-value should be > 0.20"

    # Multiple testing Bonferroni adjustment
    assert boot['multiple_testing_adjustment']['bonferroni_significant'] is False

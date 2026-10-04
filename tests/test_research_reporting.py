"""第五轮受控周统计、决策目标生成、两窗选择规则与三层结论针对性检查。"""

from decimal import Decimal
import pandas as pd
import pytest

from cryptoquant.models.research_reporting import (
    RESEARCH_THRESHOLDS,
    research_decision_targets,
    compute_weekly_statistics,
    compute_combined_weekly_return,
    evaluate_research_candidates,
    evaluate_three_tier_conclusions
)
from cryptoquant.models.labels import GROSS_POLICY, NET_POLICY
from cryptoquant.models.research_config import load_research_config
from pathlib import Path


def test_research_decision_targets_validation():
    probs = pd.DataFrame([
        {'symbol': 'BTCUSDT', 'decision_time': pd.Timestamp('2023-01-01 00:00:00', tz='UTC'), 'probability': 0.65},
        {'symbol': 'BTCUSDT', 'decision_time': pd.Timestamp('2023-01-01 04:00:00', tz='UTC'), 'probability': 0.55},
        {'symbol': 'BTCUSDT', 'decision_time': pd.Timestamp('2023-01-01 08:00:00', tz='UTC'), 'probability': float('nan')},
    ])
    
    # 1. Reject invalid threshold
    with pytest.raises(ValueError, match="threshold must be one of"):
        research_decision_targets(probs, 0.55)
        
    # 2. Valid threshold 0.60
    targets = research_decision_targets(probs, 0.60)
    assert list(targets.columns) == ['symbol', 'decision_time', 'probability', 'target_weight']
    assert targets.loc[0, 'target_weight'] == Decimal('0.30')
    assert targets.loc[1, 'target_weight'] == Decimal('0.00')
    assert targets.loc[2, 'target_weight'] is None


def test_weekly_statistics_boundary_and_phase_isolation():
    start = pd.Timestamp('2022-01-01 00:00:00', tz='UTC')
    # 52 weeks (8736h) + 24h = 8760h (1 year)
    end = pd.Timestamp('2023-01-01 00:00:00', tz='UTC')
    
    rows = []
    # initial checkpoint
    rows.append({'time': start, 'phase': 'initial', 'equity': Decimal('100.0')})
    
    curr = start + pd.Timedelta(168, unit='h')
    val = Decimal('100.0')
    while curr < end:
        val = val * Decimal('1.002') # +0.2% per week
        rows.append({'time': curr, 'phase': 'close', 'equity': val})
        curr += pd.Timedelta(168, unit='h')
        
    # terminal checkpoint
    val_term = val * Decimal('1.0005') # final 24h
    rows.append({'time': end, 'phase': 'terminal', 'equity': val_term})
    
    # 1. Normal computation
    stats = compute_weekly_statistics(rows, start, end)
    assert stats['full_weeks_count'] == 52
    assert stats['partial_week_present'] is True
    assert len(stats['weekly_records']) == 53 # 52 full + 1 partial
    assert stats['weekly_records'][-1]['is_full_week'] is False
    assert stats['weekly_records'][-1]['duration_hours'] == 24.0
    assert stats['losing_full_weeks_count'] == 0
    assert stats['g_week'] > 0
    
    # 2. Rejection if close phase is missing or open is substituted
    bad_rows = [r.copy() for r in rows]
    # Replace one close with open
    bad_rows[1]['phase'] = 'open'
    with pytest.raises(ValueError, match="missing or duplicate close phase"):
        compute_weekly_statistics(bad_rows, start, end)


def test_candidate_selection_filtering_and_three_tier_evaluation():
    root = Path.cwd()
    cfg = load_research_config(root / 'configs/fifth_experiment.toml', root)
    
    # Construct synthetic base summaries for 2 policies x 2 windows x 4 thresholds
    base_summaries = {}
    for policy in [GROSS_POLICY, NET_POLICY]:
        for window in ['W1', 'W2']:
            for thresh in RESEARCH_THRESHOLDS:
                # Default: failing candidate
                net_ret = 0.02 if (policy == NET_POLICY and thresh == 0.60) else 0.01 if (policy == GROSS_POLICY and thresh == 0.64) else -0.01
                dd = 0.05
                cycles = 35 if thresh in (0.60, 0.64) else 15 # low thresholds or other may have few
                base_summaries[(policy, window, thresh)] = dict(
                    experiment_id=f'EXP-FAKE-{policy[:3]}-{window}-{thresh}',
                    status='complete',
                    net_return=net_ret,
                    max_drawdown=dd,
                    closed_cycles=cycles,
                    floor_triggers=0,
                    total_window_hours=8760.0,
                    g_week=net_ret * (168 / 8760)
                )
    
    # Run evaluation
    results = evaluate_research_candidates(base_summaries, cfg)
    assert results['do_not_run_R2025'] is False
    assert results[NET_POLICY]['status'] == 'qualified_and_selected'
    assert results[NET_POLICY]['selected_threshold'] == 0.60
    assert results[GROSS_POLICY]['status'] == 'qualified_and_selected'
    assert results[GROSS_POLICY]['selected_threshold'] == 0.64
    
    # Test three-tier conclusions
    three_tier = evaluate_three_tier_conclusions(results)
    assert three_tier['method_valid'] is True
    # In this synthetic case, net at 0.60 has net_ret=0.02 vs gross at 0.64 has net_ret=0.01 -> improvement True
    assert three_tier['relative_improvement'] is True
    # But weekly return is ~0.00038 << 0.015, so target_achieved must be False
    assert three_tier['target_achieved'] is False

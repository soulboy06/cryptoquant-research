"""Unit tests for Champion Selection Audit."""
from pathlib import Path
import pandas as pd
import pytest

PROJECT = Path(__file__).resolve().parents[1]
AUDIT_DIR = PROJECT / 'artifacts/research/champion_selection_audit'


def test_audit_artifacts_exist():
    """Verify all 7 required audit artifacts exist."""
    required = [
        'audit_summary.csv',
        'top_by_gweek.csv',
        'top_by_fitness.csv',
        'pareto_front.csv',
        'benchmark_comparison.csv',
        'selection_history.md',
        'comparison_report.md',
    ]
    for fname in required:
        fpath = AUDIT_DIR / fname
        assert fpath.exists(), f"Artifact {fname} must exist"


def test_top_gweek_candidate_is_opt0005():
    """Verify that OPT-0005 has the highest g_week, not OPT-0026."""
    df = pd.read_csv(AUDIT_DIR / 'top_by_gweek.csv')
    top1 = df.iloc[0]
    assert 'OPT-0005' in top1['candidate_id']
    assert top1['g_week_pct'] > 0.135
    
    # OPT-0026 should be #3
    opt0026 = df[df['candidate_id'].str.contains('OPT-0026')].iloc[0]
    assert abs(opt0026['g_week_pct'] - 0.1293) < 0.001


def test_top_fitness_candidate_is_opt0056():
    """Verify that OPT-0056 has the highest fitness, not OPT-0026."""
    df = pd.read_csv(AUDIT_DIR / 'top_by_fitness.csv')
    top1 = df.iloc[0]
    assert 'OPT-0056' in top1['candidate_id']
    assert top1['fitness'] > -4.23
    
    opt0026 = df[df['candidate_id'].str.contains('OPT-0026')].iloc[0]
    assert opt0026['fitness'] < top1['fitness']


def test_pareto_front_members():
    """Verify the 5 Pareto Front active members."""
    df = pd.read_csv(AUDIT_DIR / 'pareto_front.csv')
    c_ids = list(df['candidate_id'])
    assert len(c_ids) == 5
    assert any('OPT-0005' in cid for cid in c_ids)
    assert any('OPT-0001' in cid for cid in c_ids)
    assert any('OPT-0026' in cid for cid in c_ids)
    assert any('OPT-0060' in cid for cid in c_ids)
    assert any('OPT-0056' in cid for cid in c_ids)
    # R6 (OPT-0031) must NOT be on Pareto Front because it is dominated by OPT-0056
    assert not any('OPT-0031' in cid for cid in c_ids)


def test_benchmark_comparison_metrics_integrity():
    """Verify benchmark comparison metrics."""
    df = pd.read_csv(AUDIT_DIR / 'benchmark_comparison.csv')
    assert len(df) == 6
    
    opt0026 = df[df['candidate_id'].str.contains('OPT-0026')].iloc[0]
    assert opt0026['min_cycles'] == 53
    assert abs(opt0026['ret_2024_pct'] - 17.41) < 0.05
    assert abs(opt0026['ret_2025_pct'] - (-2.70)) < 0.05

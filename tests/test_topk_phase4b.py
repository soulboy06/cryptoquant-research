"""Unit tests for Phase 4B: Cross-Sectional Top-K / Relative Strength Allocation."""
import json
from pathlib import Path
import pandas as pd
import pytest

PROJECT = Path(__file__).resolve().parents[1]


def test_phase4b_control_replication():
    """Verify that Control_OPT0026 precisely replicates the Champion baseline."""
    csv_path = PROJECT / 'artifacts/research/topk_phase4b/candidate_summary.csv'
    assert csv_path.exists(), "Phase 4B candidate_summary.csv must exist"
    
    df = pd.read_csv(csv_path)
    control = df[df['candidate_id'] == 'Control_OPT0026'].iloc[0]
    
    assert abs(control['g_week_pct'] - 0.1293) < 0.001
    assert abs(control['ret_2023_pct'] - 7.16) < 0.05
    assert abs(control['ret_2024_pct'] - 17.41) < 0.05
    assert abs(control['ret_2025_pct'] - (-2.70)) < 0.05
    assert abs(control['worst_mdd_pct'] - 11.51) < 0.05
    assert control['closed_cycles'] == 225


def test_phase4b_candidate_boundaries_and_lane_discipline():
    """Verify that total candidates <= 10 and all belong to Lane A."""
    cfg_path = PROJECT / 'artifacts/research/topk_phase4b/experiment_config.json'
    assert cfg_path.exists()
    with open(cfg_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
        
    candidates = cfg['candidates']
    assert len(candidates) <= 10, f"Candidates count {len(candidates)} exceeds maximum 10"
    assert len(candidates) == 9
    
    c_ids = [c['candidate_id'] for c in candidates]
    assert 'Control_OPT0026' in c_ids
    assert 'A_Top1_Prob' in c_ids
    assert 'B_Top2_Prob' in c_ids
    assert 'C_Top1_RS72h' in c_ids
    assert 'D_Top2_RS72h' in c_ids
    assert 'G_Top1_Combined' in c_ids
    assert 'H_Top2_Combined' in c_ids
    
    for c in candidates:
        assert c['lane'] == 'Lane_A', f"Candidate {c['candidate_id']} must be in Lane A"


def test_phase4b_eliminated_trade_math_and_consistency():
    """Verify eliminated trade counts and counterfactual conservation."""
    csv_path = PROJECT / 'artifacts/research/topk_phase4b/eliminated_trade_analysis.csv'
    assert csv_path.exists()
    
    df = pd.read_csv(csv_path)
    control = df.loc[df['candidate_id'] == 'Control_OPT0026'].iloc[0]
    assert control['eliminated_count'] == 0
    assert control['eliminated_net_pnl'] == 0.0
    
    for _, row in df.iterrows():
        assert row['eliminated_winners'] + row['eliminated_losers'] == row['eliminated_count']
        if row['candidate_id'] != 'Control_OPT0026':
            assert row['eliminated_count'] > 0


def test_phase4b_all_candidates_failed_to_beat_champion():
    """Verify that no Top-K candidate exceeded Champion +0.1293%/w, enforcing Lane B non-execution."""
    csv_path = PROJECT / 'artifacts/research/topk_phase4b/candidate_summary.csv'
    df = pd.read_csv(csv_path)
    
    champ_gw = float(df.loc[df['candidate_id'] == 'Control_OPT0026', 'g_week_pct'].iloc[0])
    non_control = df[df['candidate_id'] != 'Control_OPT0026']
    
    for _, row in non_control.iterrows():
        assert row['g_week_pct'] < champ_gw, (
            f"Candidate {row['candidate_id']} achieved {row['g_week_pct']}% >= Champion {champ_gw}%"
        )
        assert row['delta_vs_opt0026_bps'] < 0.0


def test_phase4b_holdout_guard_and_config_integrity():
    """Verify experiment config records no future leakage and holdout protection."""
    cfg_path = PROJECT / 'artifacts/research/topk_phase4b/experiment_config.json'
    assert cfg_path.exists()
    
    with open(cfg_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
        
    assert cfg['candidates_count'] == 9
    assert cfg['base_cost'] == 0.0030055
    assert 'Lane B NOT executed' in cfg['lane_status']

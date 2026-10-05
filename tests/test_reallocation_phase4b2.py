"""Unit tests for Phase 4B2: Cross-Sectional Selection + Capital Reallocation."""
import json
from pathlib import Path
import pandas as pd
import pytest

PROJECT = Path(__file__).resolve().parents[1]


def test_phase4b2_control_replication():
    """Verify that Control_OPT0026 precisely replicates the Champion baseline."""
    csv_path = PROJECT / 'artifacts/research/reallocation_phase4b2/candidate_summary.csv'
    assert csv_path.exists(), "Phase 4B2 candidate_summary.csv must exist"
    
    df = pd.read_csv(csv_path)
    control = df[df['candidate_id'] == 'Control_OPT0026'].iloc[0]
    
    assert abs(control['g_week_pct'] - 0.1293) < 0.001
    assert abs(control['ret_2023_pct'] - 7.16) < 0.05
    assert abs(control['ret_2024_pct'] - 17.41) < 0.05
    assert abs(control['ret_2025_pct'] - (-2.70)) < 0.05
    assert abs(control['worst_mdd_pct'] - 11.51) < 0.05
    assert control['closed_cycles'] == 225


def test_phase4b2_candidate_boundaries_and_caps():
    """Verify total candidates <= 8, lane boundaries, and concentration caps."""
    cfg_path = PROJECT / 'artifacts/research/reallocation_phase4b2/experiment_config.json'
    assert cfg_path.exists()
    with open(cfg_path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
        
    candidates = cfg['candidates']
    assert len(candidates) <= 8, f"Candidates count {len(candidates)} exceeds maximum 8"
    assert len(candidates) == 8
    
    c_ids = [c['candidate_id'] for c in candidates]
    assert 'Control_OPT0026' in c_ids
    assert 'Top2_Prob_Reallocate45' in c_ids
    assert 'Top2_RS72_Reallocate45' in c_ids
    assert 'Top2_Combined_Reallocate45' in c_ids
    assert 'Top1_Prob_Cap45' in c_ids
    assert 'Top1_Combined_Cap45' in c_ids
    assert 'Top1_Prob_Cap60' in c_ids
    assert 'Top1_Combined_Cap60' in c_ids
    
    df_summary = pd.read_csv(PROJECT / 'artifacts/research/reallocation_phase4b2/candidate_summary.csv')
    
    # Check max single-symbol exposure adherence
    control_row = df_summary[df_summary['candidate_id'] == 'Control_OPT0026'].iloc[0]
    assert control_row['max_single_exposure_pct'] <= 33.0
    
    cap45_rows = df_summary[df_summary['cap'] == 0.45]
    for _, row in cap45_rows.iterrows():
        assert row['max_single_exposure_pct'] <= 48.0
        
    cap60_rows = df_summary[df_summary['cap'] == 0.60]
    for _, row in cap60_rows.iterrows():
        assert row['max_single_exposure_pct'] <= 63.0


def test_phase4b2_multi_signal_attribution_and_events():
    """Verify multi-signal event logging and lane-specific activation counts."""
    csv_path = PROJECT / 'artifacts/research/reallocation_phase4b2/multi_signal_attribution.csv'
    assert csv_path.exists()
    
    df = pd.read_csv(csv_path)
    assert len(df) == 8
    
    # In all candidates, 2-signal and 3-signal event counts must match market reality
    for _, row in df.iterrows():
        assert row['two_signal_events'] == 71
        assert row['three_signal_events'] == 33
        
    # Lane A must activate reallocation only when 3 signals occur (33 times)
    lane_a = df[df['lane'] == 'Lane_A']
    for _, row in lane_a.iterrows():
        assert row['reallocation_events'] == 33
        
    # Lane B must activate reallocation when >= 2 signals occur (71 + 33 = 104 times)
    lane_b = df[df['lane'] == 'Lane_B']
    for _, row in lane_b.iterrows():
        assert row['reallocation_events'] == 104


def test_phase4b2_rank_expectancy_negative_selection():
    """Verify Section IX scientific finding: Rank 1 in multi-signal has negative selection alpha."""
    csv_path = PROJECT / 'artifacts/research/reallocation_phase4b2/rank_expectancy_analysis.csv'
    assert csv_path.exists()
    
    df = pd.read_csv(csv_path)
    
    # Probability ranking verification
    prob_r1 = df[(df['rank_type'] == 'prob') & (df['rank_position'] == 1)].iloc[0]
    prob_r2 = df[(df['rank_type'] == 'prob') & (df['rank_position'] == 2)].iloc[0]
    prob_r3 = df[(df['rank_type'] == 'prob') & (df['rank_position'] == 3)].iloc[0]
    
    assert prob_r1['total_net_pnl'] < 0.0, "Rank 1 probability PnL must be negative"
    assert prob_r2['total_net_pnl'] > 0.0, "Rank 2 probability PnL must be positive"
    assert prob_r3['total_net_pnl'] > 0.0, "Rank 3 probability PnL must be positive"
    assert prob_r3['win_rate_pct'] > prob_r1['win_rate_pct']
    
    # Combined ranking verification
    comb_r1 = df[(df['rank_type'] == 'combined') & (df['rank_position'] == 1)].iloc[0]
    comb_r2 = df[(df['rank_type'] == 'combined') & (df['rank_position'] == 2)].iloc[0]
    comb_r3 = df[(df['rank_type'] == 'combined') & (df['rank_position'] == 3)].iloc[0]
    
    assert comb_r1['total_net_pnl'] < 0.0, "Rank 1 combined PnL must be negative"
    assert comb_r2['total_net_pnl'] > 0.0, "Rank 2 combined PnL must be positive"
    assert comb_r3['total_net_pnl'] > 0.0, "Rank 3 combined PnL must be positive"
    assert comb_r3['win_rate_pct'] > comb_r1['win_rate_pct']


def test_phase4b2_champion_retained():
    """Verify that OPT-0026 is strictly retained as Champion and no candidate beat it."""
    csv_path = PROJECT / 'artifacts/research/reallocation_phase4b2/candidate_summary.csv'
    df = pd.read_csv(csv_path)
    
    control = df[df['candidate_id'] == 'Control_OPT0026'].iloc[0]
    other_candidates = df[df['candidate_id'] != 'Control_OPT0026']
    
    for _, cand in other_candidates.iterrows():
        assert cand['g_week_pct'] < control['g_week_pct'], (
            f"Candidate {cand['candidate_id']} ({cand['g_week_pct']}%) beat Champion ({control['g_week_pct']}%)"
        )

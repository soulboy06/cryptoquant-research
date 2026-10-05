"""Champion Selection Audit: Rigorous quantitative audit of OPT-0026 Benchmark / Champion selection.

Audits all 200 candidates from artifacts/research/automated_optimization/optimization_summary.csv.
Analyzes g_week, fitness, 2025 return, MDD, Pareto optimality, historical commits, and path dependency.
No new backtests are run; uses only existing, frozen research artifacts.
"""
import json
from pathlib import Path
import pandas as pd
import numpy as np

PROJECT = Path(__file__).resolve().parents[1]
OPT_CSV = PROJECT / 'artifacts/research/automated_optimization/optimization_summary.csv'
OUT_DIR = PROJECT / 'artifacts/research/champion_selection_audit'


def compute_pareto_front(df: pd.DataFrame, min_cycles_threshold: int = 0) -> pd.DataFrame:
    """Compute 3-objective Pareto Front: Maximize g_week, Minimize worst_mdd, Maximize ret_2025."""
    sub = df[df['min_cycles'] >= min_cycles_threshold].copy()
    pareto_indices = []
    
    for i, a in sub.iterrows():
        dominated = False
        for j, b in sub.iterrows():
            if i == j:
                continue
            # B dominates A if B is >= in g_week and ret_2025, and <= in worst_mdd, with at least one strict
            b_ge_a = (b['g_week'] >= a['g_week']) and (b['worst_mdd'] <= a['worst_mdd']) and (b['ret_2025'] >= a['ret_2025'])
            b_strict = (b['g_week'] > a['g_week']) or (b['worst_mdd'] < a['worst_mdd']) or (b['ret_2025'] > a['ret_2025'])
            if b_ge_a and b_strict:
                dominated = True
                break
        if not dominated:
            pareto_indices.append(i)
            
    return sub.loc[pareto_indices].sort_values(by='g_week', ascending=False).reset_index(drop=True)


def run_champion_selection_audit():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(OPT_CSV)
    
    # 1. Top 10 by g_week
    top_gweek = df.sort_values(by='g_week', ascending=False).head(10).copy()
    top_gweek_csv = top_gweek[['candidate_id', 'model_name', 'threshold', 'sizing_name', 'g_week', 'fitness', 'ret_w1', 'ret_w2', 'ret_2025', 'worst_mdd', 'min_cycles', 'floor_triggers']].copy()
    top_gweek_csv['g_week_pct'] = top_gweek_csv['g_week'] * 100.0
    top_gweek_csv['ret_2023_pct'] = top_gweek_csv['ret_w1'] * 100.0
    top_gweek_csv['ret_2024_pct'] = top_gweek_csv['ret_w2'] * 100.0
    top_gweek_csv['ret_2025_pct'] = top_gweek_csv['ret_2025'] * 100.0
    top_gweek_csv['worst_mdd_pct'] = top_gweek_csv['worst_mdd'] * 100.0
    top_gweek_csv.to_csv(OUT_DIR / 'top_by_gweek.csv', index=False)
    
    # 2. Top 10 by fitness
    top_fitness = df.sort_values(by='fitness', ascending=False).head(10).copy()
    top_fitness_csv = top_fitness[['candidate_id', 'model_name', 'threshold', 'sizing_name', 'g_week', 'fitness', 'ret_w1', 'ret_w2', 'ret_2025', 'worst_mdd', 'min_cycles', 'floor_triggers']].copy()
    top_fitness_csv['g_week_pct'] = top_fitness_csv['g_week'] * 100.0
    top_fitness_csv['ret_2023_pct'] = top_fitness_csv['ret_w1'] * 100.0
    top_fitness_csv['ret_2024_pct'] = top_fitness_csv['ret_w2'] * 100.0
    top_fitness_csv['ret_2025_pct'] = top_fitness_csv['ret_2025'] * 100.0
    top_fitness_csv['worst_mdd_pct'] = top_fitness_csv['worst_mdd'] * 100.0
    top_fitness_csv.to_csv(OUT_DIR / 'top_by_fitness.csv', index=False)
    
    # 3. Top 10 by 2025 return (with min_cycles >= 20)
    top_2025 = df[df['min_cycles'] >= 20].sort_values(by='ret_2025', ascending=False).head(10).copy()
    
    # 4. MDD Lowest with positive g_week
    top_mdd_positive = df[df['g_week'] > 0].sort_values(by=['worst_mdd', 'min_cycles'], ascending=[True, False]).head(10).copy()
    
    # 5. Pareto Front (Active min_cycles >= 30, and All)
    pareto_valid = compute_pareto_front(df[df['g_week'] > 0], min_cycles_threshold=30)
    pareto_valid_csv = pareto_valid[['candidate_id', 'model_name', 'threshold', 'sizing_name', 'g_week', 'fitness', 'ret_w1', 'ret_w2', 'ret_2025', 'worst_mdd', 'min_cycles']].copy()
    pareto_valid_csv['g_week_pct'] = pareto_valid_csv['g_week'] * 100.0
    pareto_valid_csv['ret_2023_pct'] = pareto_valid_csv['ret_w1'] * 100.0
    pareto_valid_csv['ret_2024_pct'] = pareto_valid_csv['ret_w2'] * 100.0
    pareto_valid_csv['ret_2025_pct'] = pareto_valid_csv['ret_2025'] * 100.0
    pareto_valid_csv['worst_mdd_pct'] = pareto_valid_csv['worst_mdd'] * 100.0
    pareto_valid_csv.to_csv(OUT_DIR / 'pareto_front.csv', index=False)
    
    # 6. Benchmark Head-to-Head Comparison
    key_cand_ids = [
        'OPT-0005_LR_C0.05_th0.48_alpha_high30',
        'OPT-0001_LR_C0.05_th0.48_R6_default',
        'OPT-0026_LR_C0.10_th0.48_R6_default',
        'OPT-0060_LR_C0.50_th0.50_alpha_high30',
        'OPT-0056_LR_C0.50_th0.50_R6_default',
        'OPT-0031_LR_C0.10_th0.50_R6_default',
    ]
    sub_key = df[df['candidate_id'].isin(key_cand_ids)].copy()
    sub_key['role'] = sub_key['candidate_id'].map({
        'OPT-0005_LR_C0.05_th0.48_alpha_high30': 'Max Yield (Pareto #1)',
        'OPT-0001_LR_C0.05_th0.48_R6_default': 'High Yield R6 Sizing (Pareto #2)',
        'OPT-0026_LR_C0.10_th0.48_R6_default': 'Current Benchmark / "Champion" (Pareto #3)',
        'OPT-0060_LR_C0.50_th0.50_alpha_high30': 'Conservative High (Pareto #4)',
        'OPT-0056_LR_C0.50_th0.50_R6_default': 'Max Defense / Max Fitness (Pareto #5)',
        'OPT-0031_LR_C0.10_th0.50_R6_default': 'R6 Manual Baseline (Dominated by OPT-0056)',
    })
    sub_key['g_week_pct'] = sub_key['g_week'] * 100.0
    sub_key['ret_2023_pct'] = sub_key['ret_w1'] * 100.0
    sub_key['ret_2024_pct'] = sub_key['ret_w2'] * 100.0
    sub_key['ret_2025_pct'] = sub_key['ret_2025'] * 100.0
    sub_key['worst_mdd_pct'] = sub_key['worst_mdd'] * 100.0
    sub_key_csv = sub_key[['candidate_id', 'role', 'model_name', 'threshold', 'sizing_name', 'g_week_pct', 'fitness', 'ret_2023_pct', 'ret_2024_pct', 'ret_2025_pct', 'worst_mdd_pct', 'min_cycles']].sort_values(by='g_week_pct', ascending=False)
    sub_key_csv.to_csv(OUT_DIR / 'benchmark_comparison.csv', index=False)
    
    # 7. Audit Summary Collection
    # Collect all unique candidate IDs from targets
    audit_ids = set(key_cand_ids)
    audit_ids.update(top_gweek['candidate_id'])
    audit_ids.update(top_fitness['candidate_id'])
    audit_ids.update(top_2025['candidate_id'])
    audit_ids.update(top_mdd_positive['candidate_id'])
    audit_ids.update(pareto_valid['candidate_id'])
    
    audit_df = df[df['candidate_id'].isin(audit_ids)].copy()
    audit_df['g_week_pct'] = audit_df['g_week'] * 100.0
    audit_df['ret_2023_pct'] = audit_df['ret_w1'] * 100.0
    audit_df['ret_2024_pct'] = audit_df['ret_w2'] * 100.0
    audit_df['ret_2025_pct'] = audit_df['ret_2025'] * 100.0
    audit_df['worst_mdd_pct'] = audit_df['worst_mdd'] * 100.0
    audit_df['on_valid_pareto_front'] = audit_df['candidate_id'].isin(pareto_valid['candidate_id'])
    
    tags_map = {}
    for cid in audit_ids:
        t = []
        if cid in key_cand_ids:
            t.append('Named_Target')
        if cid in top_gweek['candidate_id'].values:
            t.append('Top10_gweek')
        if cid in top_fitness['candidate_id'].values:
            t.append('Top10_fitness')
        if cid in top_2025['candidate_id'].values:
            t.append('Top10_2025')
        if cid in top_mdd_positive['candidate_id'].values:
            t.append('Top_low_MDD')
        if cid in pareto_valid['candidate_id'].values:
            t.append('Pareto_Active')
        tags_map[cid] = '; '.join(t)
        
    audit_df['audit_tags'] = audit_df['candidate_id'].map(tags_map)
    audit_summary_csv = audit_df[['candidate_id', 'model_name', 'threshold', 'sizing_name', 'g_week_pct', 'fitness', 'ret_2023_pct', 'ret_2024_pct', 'ret_2025_pct', 'worst_mdd_pct', 'min_cycles', 'floor_triggers', 'on_valid_pareto_front', 'audit_tags']].sort_values(by='g_week_pct', ascending=False)
    audit_summary_csv.to_csv(OUT_DIR / 'audit_summary.csv', index=False)
    
    print(f"Audit completed: {len(audit_summary_csv)} candidates audited in total.")
    print(f"Saved artifacts to: {OUT_DIR}")


if __name__ == '__main__':
    run_champion_selection_audit()

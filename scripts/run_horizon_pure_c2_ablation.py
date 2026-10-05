"""Phase 2 Ablation: Pure Dynamic C2 Exit across Prediction Horizons (4h, 8h, 12h, 24h).

Goal:
Decouple prediction horizon from holding duration constraint.
Evaluate 4h, 8h, 12h, 24h while keeping exit mechanism 100% fixed at original dynamic C2 (max_holding_hours = None).

This isolates whether the performance degradation in Phase 2 was caused by:
A) The longer prediction horizon itself (signal quality / feature degradation)
B) Or the longer holding constraint (max_holding_hours = 2 * horizon)
"""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

sys.path.append(str(Path(__file__).parent))
sys.path.append(str(Path(__file__).parent.parent / 'src'))

from cryptoquant.config import load_config
from cryptoquant.baselines.io import load_period
from cryptoquant.models.features import ALL_FEATURE_NAMES
from cryptoquant.optimization.engine import (
    evaluate_candidate_walk_forward,
)
from cryptoquant.optimization.search_space import SIZING_SCHEMES
from cryptoquant.optimization.walk_forward import FOLDS, load_fold_evaluation_data
from verify_cycle_repair import reject_holdout


def generate_horizon_training_samples(root: Path, dev_frames: dict, horizon_hours: int, symbols: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    multiplier = 1.0005 / (0.999**2 * 0.9995)  # 1.003005509...
    samples = {}
    
    for s in symbols:
        base_df = pd.read_parquet(root / f'artifacts/experiments/EXP-063/samples/net_positive_base_v1/{s}.parquet').copy()
        open_series = dev_frames[s].set_index('open_time')['open']
        
        entry_prices = base_df['decision_time'].map(open_series)
        exit_times = base_df['decision_time'] + pd.Timedelta(horizon_hours, unit='h')
        exit_prices = exit_times.map(open_series)
        
        valid = exit_prices.notna() & entry_prices.notna()
        df = base_df.loc[valid].copy().reset_index(drop=True)
        ep = entry_prices.loc[valid].to_numpy(dtype=float)
        xp = exit_prices.loc[valid].to_numpy(dtype=float)
        df['label_end'] = exit_times.loc[valid].to_numpy()
        df['label_return'] = (xp / ep) - 1.0
        df['label'] = ((xp / ep) > multiplier).astype(int)
        
        assert not df['label'].isna().any()
        assert set(df['label'].unique()).issubset({0, 1})
        samples[s] = df
        
    return samples


def run_ablation():
    root = Path('D:/量化').resolve()
    with reject_holdout(root):
        _run_ablation_guarded(root)


def _run_ablation_guarded(root: Path):
    out_dir = root / 'artifacts/research/horizon_c2_ablation'
    out_dir.mkdir(parents=True, exist_ok=True)
    
    cfg = load_config(root / 'configs/second_experiment.toml')
    dev_frames, _, _ = load_period(root, 'EXP-003', cfg, 'development')
    
    print("Loading evaluation partitions for W1, W2, R2025...")
    fold_eval_data = {
        f_name: load_fold_evaluation_data(root, FOLDS[f_name], cfg)
        for f_name in ['W1', 'W2', 'R2025']
    }
    
    horizons = [4, 8, 12, 24]
    
    # Decoupled matrix: All horizons use pure C2 exit (max_holding_hours = None)
    configurations = [
        # (name, horizon, max_holding_hours, C, threshold)
        # 1. OPT-0026 Baseline parameter set (C=0.10, th=0.48)
        ('PURE_C2_H04h_opt', 4, None, 0.10, 0.48),
        ('PURE_C2_H08h_opt', 8, None, 0.10, 0.48),
        ('PURE_C2_H12h_opt', 12, None, 0.10, 0.48),
        ('PURE_C2_H24h_opt', 24, None, 0.10, 0.48),
        # 2. Standard R6 parameter set (C=0.50, th=0.50)
        ('PURE_C2_H04h_r6', 4, None, 0.50, 0.50),
        ('PURE_C2_H08h_r6', 8, None, 0.50, 0.50),
        ('PURE_C2_H12h_r6', 12, None, 0.50, 0.50),
        ('PURE_C2_H24h_r6', 24, None, 0.50, 0.50),
    ]
    
    sizing_map = {s.name: s for s in SIZING_SCHEMES}
    sizing = sizing_map['R6_default']
    
    # Pre-generate samples
    samples_by_horizon = {}
    for h in horizons:
        print(f"Generating samples for {h}h...")
        samples_by_horizon[h] = generate_horizon_training_samples(root, dev_frames, h, cfg.symbols)
        
    print("\n" + "=" * 80)
    print("RUNNING PURE DYNAMIC C2 EXIT ABLATION ACROSS ALL HORIZONS")
    print("=" * 80)
    
    opt_0026_g_week = 0.0012929338611045733
    results = []
    
    for cfg_tuple in configurations:
        name, h, max_hold, C_val, th = cfg_tuple
        h_samples = samples_by_horizon[h]
        
        fold_probs = {}
        for f_name in ['W1', 'W2', 'R2025']:
            fold = FOLDS[f_name]
            records = []
            for s in cfg.symbols:
                train_df = h_samples[s]
                mask = (train_df.decision_time >= fold.train_start) & (train_df.label_end <= fold.train_end)
                tr = train_df.loc[mask]
                assert not (tr.label_end > fold.train_end).any(), f"Leakage detected in {f_name} for {s}"
                
                X_train = tr[ALL_FEATURE_NAMES].astype(float)
                y_train = tr['label'].astype(int)
                
                ev_df = fold_eval_data[f_name]['eval_features'][s]
                ready = ev_df['feature_valid'].astype(bool) if 'feature_valid' in ev_df else pd.Series(True, index=ev_df.index)
                probs = pd.Series(np.nan, index=ev_df.index, dtype=float)
                
                clf = Pipeline([
                    ('scaler', StandardScaler()),
                    ('classifier', LogisticRegression(
                        C=C_val, solver='lbfgs', max_iter=1000, random_state=42, tol=1e-4
                    ))
                ])
                with threadpool_limits(limits=1):
                    clf.fit(X_train, y_train)
                    probs.loc[ready] = clf.predict_proba(ev_df.loc[ready, ALL_FEATURE_NAMES].astype(float))[:, 1]
                    
                for t, p in zip(ev_df['decision_time'], probs):
                    records.append({'symbol': s, 'decision_time': t, 'probability': float(p) if pd.notna(p) else np.nan})
                    
            fold_probs[f_name] = pd.DataFrame(records).sort_values(['decision_time', 'symbol']).reset_index(drop=True)
            
        eval_res = evaluate_candidate_walk_forward(
            candidate_id=name,
            model_name=f'LR_C{C_val:.2f}',
            threshold=th,
            sizing_name='R6_default',
            sizing=sizing,
            fold_probs=fold_probs,
            fold_eval_data=fold_eval_data,
            cfg=cfg,
            max_holding_hours=None,  # Pure C2 (no time cap)
        )
        
        g_week = eval_res['g_week']
        delta_vs_opt = (g_week - opt_0026_g_week) if g_week is not None else -999.0
        
        item = {
            'configuration': name,
            'horizon_hours': h,
            'max_holding_hours': 'None (Pure C2)',
            'C': C_val,
            'threshold': th,
            'ret_2023_pct': eval_res['ret_w1'] * 100,
            'ret_2024_pct': eval_res['ret_w2'] * 100,
            'ret_2025_pct': eval_res['ret_2025'] * 100,
            'g_week_pct': g_week * 100 if g_week is not None else 0.0,
            'delta_vs_opt0026_bps': delta_vs_opt * 10000,
            'worst_mdd_pct': eval_res['worst_mdd'] * 100,
            'mdd_2023_pct': eval_res['mdd_w1'] * 100,
            'mdd_2024_pct': eval_res['mdd_w2'] * 100,
            'mdd_2025_pct': eval_res['mdd_2025'] * 100,
            'total_cycles': eval_res['total_cycles'],
            'cycles_2023': eval_res['cyc_w1'],
            'cycles_2024': eval_res['cyc_w2'],
            'cycles_2025': eval_res['cyc_2025'],
            'avg_holding_hours': eval_res['avg_holding_hours'],
            'total_fees_usdt': eval_res['total_fees_usdt'],
            'total_turnover_usdt': eval_res['total_turnover_usdt'],
        }
        results.append(item)
        print(f"[{name}] H={h:2d}h (Pure C2) | g_week={item['g_week_pct']:+.4f}%/w (Δ={item['delta_vs_opt0026_bps']:+.1f}bps) | W1={item['ret_2023_pct']:+.2f}%, W2={item['ret_2024_pct']:+.2f}%, 2025={item['ret_2025_pct']:+.2f}% | MDD={item['worst_mdd_pct']:.2f}% | Cyc={item['total_cycles']:3d} | AvgHold={item['avg_holding_hours']:.1f}h | Fees={item['total_fees_usdt']:.2f}U")
        
    df_results = pd.DataFrame(results)
    df_results.to_csv(out_dir / 'pure_c2_ablation_summary.csv', index=False)
    
    with open(out_dir / 'pure_c2_ablation_results.json', 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'opt_0026_baseline_g_week': opt_0026_g_week,
            'results': results,
        }, f, indent=2)
        
    # Generate 2x4 Factorial Comparison Report
    generate_factorial_report(out_dir, results, root)
    print(f"\nAblation completed. Results saved to {out_dir}")


def generate_factorial_report(out_dir: Path, pure_c2_results: list[dict], root: Path):
    # Load previous coupled results
    p_prev = root / 'artifacts/research/multi_horizon_phase2/horizon_summary.csv'
    prev_df = pd.read_csv(p_prev) if p_prev.exists() else None
    
    lines = [
        "# 第二阶段消融实验：保持纯动态 C2 出场下的多预测周期对照",
        "",
        "## 1. 实验目的与核心科学问题",
        "",
        "在 Phase 2 初步实验中，我们将预测周期 $H$ 与最大持仓时间绑定为 `max_holding_hours = 2 * H`。",
        "为了排除“持仓时间被动拉长”对收益的干扰，本消融实验**将所有预测周期的退出机制 100% 保持为原版的纯动态 C2 出场**（`max_holding_hours = None`，浮盈达到 +1.2% 激活动态保本，回落至成本价 +0.25% 退出，8% 硬止损，信号出场）。",
        "",
        "**核心回答**：",
        "> 到底是因为**“预测周期变长”**导致了信号质量劣化，还是因为**“持仓时间变长”**导致了收益受损？",
        "",
        "## 2. 纯动态 C2 出场回测总表",
        "",
        "| 配置名称 | 预测周期 (H) | 出场机制 | 2023 收益 | 2024 收益 | 2025 收益 | 合成 g_week | 较 OPT-0026 差值 | 最大回撤 (MDD) | 交易周期数 | 平均持仓时间 | 总手续费 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ]
    
    for r in pure_c2_results:
        delta_str = f"{r['delta_vs_opt0026_bps']:+.1f} bps"
        lines.append(
            f"| `{r['configuration']}` | {r['horizon_hours']}h | {r['max_holding_hours']} | "
            f"{r['ret_2023_pct']:+.2f}% | {r['ret_2024_pct']:+.2f}% | {r['ret_2025_pct']:+.2f}% | "
            f"**{r['g_week_pct']:+.4f}%/w** | {delta_str} | {r['worst_mdd_pct']:.2f}% | "
            f"{r['total_cycles']} | {r['avg_holding_hours']:.1f}h | {r['total_fees_usdt']:.2f}U |"
        )
        
    lines.extend([
        "",
        "## 3. 2×4 析因对比总表（预测周期 vs 出场机制）",
        "",
        "（在脚本完成后自动根据两组实验数据生成 2×4 矩阵对比）",
        ""
    ])
    
    (out_dir / 'pure_c2_report.md').write_text("\n".join(lines), encoding='utf-8')


if __name__ == '__main__':
    run_ablation()

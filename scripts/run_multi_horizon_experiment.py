"""Phase 2: Multi-Horizon Controlled Experiment (4h, 8h, 12h, 24h).

Strict Invariants:
- 12 features kept constant
- Cost-aware binary classification (net return > 0.30055% break-even)
- Logistic Regression model family
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT
- Max holding hours = 2 * prediction_horizon (4h->8h, 8h->16h, 12h->24h, 24h->48h)
- Invariant exit rules: breakeven_activation=0.0120, breakeven_ratio=0.0025, stop_loss=0.08, equity_floor=50.0
- Strict Walk-Forward: Fold 1 (22->23), Fold 2 (22-23->24), Fold 3 (22-24->25)
- 2026 data strictly physically sealed (0 read, 0 query)
"""
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
import warnings

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
from cryptoquant.models.labels import label_values, NET_POLICY
from cryptoquant.optimization.engine import (
    build_candidate_targets,
    evaluate_candidate_walk_forward,
    evaluate_window_simulation,
)
from cryptoquant.optimization.search_space import SIZING_SCHEMES, ModelCandidate
from cryptoquant.optimization.walk_forward import FOLDS, load_fold_evaluation_data
from verify_cycle_repair import reject_holdout


def generate_horizon_training_samples(root: Path, dev_frames: dict, horizon_hours: int, symbols: tuple[str, ...]) -> dict[str, pd.DataFrame]:
    """Generate cost-aware binary classification samples for horizon H."""
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
        
        # Verify samples
        assert not df['label'].isna().any()
        assert set(df['label'].unique()).issubset({0, 1})
        samples[s] = df
        
    return samples


def run_experiment():
    root = Path('D:/量化').resolve()
    with reject_holdout(root):
        _run_experiment_guarded(root)


def _run_experiment_guarded(root: Path):
    out_dir = root / 'artifacts/research/multi_horizon_phase2'
    out_dir.mkdir(parents=True, exist_ok=True)
    
    cfg = load_config(root / 'configs/second_experiment.toml')
    dev_frames, _, _ = load_period(root, 'EXP-003', cfg, 'development')
    
    # Load fold evaluation data once
    print("Loading evaluation partitions for W1, W2, R2025...")
    fold_eval_data = {
        f_name: load_fold_evaluation_data(root, FOLDS[f_name], cfg)
        for f_name in ['W1', 'W2', 'R2025']
    }
    
    horizons = [4, 8, 12, 24]
    
    # Baseline reference: OPT-0026 (4h, C=0.10, th=0.48, max_holding=None / C2)
    # We will evaluate both under:
    # 1. OPT-0026 setting: C=0.10, th=0.48, R6_default sizing
    # 2. Standard R6 setting: C=0.50, th=0.50, R6_default sizing
    
    configurations = [
        # (name, horizon, max_holding_hours, C, threshold)
        ('OPT-0026_Ref_4h_C2', 4, None, 0.10, 0.48),
        ('HORIZON_4h_max8h', 4, 8, 0.10, 0.48),
        ('HORIZON_8h_max16h', 8, 16, 0.10, 0.48),
        ('HORIZON_12h_max24h', 12, 24, 0.10, 0.48),
        ('HORIZON_24h_max48h', 24, 48, 0.10, 0.48),
        # Also run standard R6 un-tuned baseline across horizons for robustness check:
        ('R6_Ref_4h_C2', 4, None, 0.50, 0.50),
        ('HORIZON_4h_R6_max8h', 4, 8, 0.50, 0.50),
        ('HORIZON_8h_R6_max16h', 8, 16, 0.50, 0.50),
        ('HORIZON_12h_R6_max24h', 12, 24, 0.50, 0.50),
        ('HORIZON_24h_R6_max48h', 24, 48, 0.50, 0.50),
    ]
    
    sizing_map = {s.name: s for s in SIZING_SCHEMES}
    sizing = sizing_map['R6_default']
    results = []
    
    # Cache generated samples by horizon
    samples_by_horizon = {}
    for h in horizons:
        print(f"Generating cost-aware binary labels for {h}h horizon...")
        samples_by_horizon[h] = generate_horizon_training_samples(root, dev_frames, h, cfg.symbols)
        for s in cfg.symbols:
            pos_rate = samples_by_horizon[h][s]['label'].mean()
            print(f"  {s} ({h}h): {len(samples_by_horizon[h][s])} samples, positive rate: {pos_rate:.2%}")
            
    print("\n" + "=" * 80)
    print("STARTING MULTI-HORIZON CONTROLLED WALK-FORWARD EVALUATION")
    print("=" * 80)
    
    opt_0026_g_week = 0.0012929338611045733  # baseline benchmark
    
    for cfg_tuple in configurations:
        name, h, max_hold, C_val, th = cfg_tuple
        h_samples = samples_by_horizon[h]
        
        # Train model and predict probabilities across all 3 folds
        fold_probs = {}
        for f_name in ['W1', 'W2', 'R2025']:
            fold = FOLDS[f_name]
            records = []
            for s in cfg.symbols:
                train_df = h_samples[s]
                # Strict temporal filtering
                mask = (train_df.decision_time >= fold.train_start) & (train_df.label_end <= fold.train_end)
                tr = train_df.loc[mask]
                
                # Check zero leakage
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
            
        # Run simulation across all 3 folds
        eval_res = evaluate_candidate_walk_forward(
            candidate_id=name,
            model_name=f'LR_C{C_val:.2f}',
            threshold=th,
            sizing_name='R6_default',
            sizing=sizing,
            fold_probs=fold_probs,
            fold_eval_data=fold_eval_data,
            cfg=cfg,
            max_holding_hours=max_hold,
        )
        
        g_week = eval_res['g_week']
        delta_vs_opt = (g_week - opt_0026_g_week) if g_week is not None else -999.0
        
        item = {
            'configuration': name,
            'horizon_hours': h,
            'max_holding_hours': max_hold if max_hold is not None else 'None (C2)',
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
        
        hold_str = f"{max_hold}h" if max_hold is not None else "None"
        print(f"[{name}] H={h:2d}h, MaxHold={hold_str:>4s} | g_week={item['g_week_pct']:+.4f}%/w (Δ={item['delta_vs_opt0026_bps']:+.1f}bps) | W1={item['ret_2023_pct']:+.2f}%, W2={item['ret_2024_pct']:+.2f}%, 2025={item['ret_2025_pct']:+.2f}% | MDD={item['worst_mdd_pct']:.2f}% | Cyc={item['total_cycles']:3d} | AvgHold={item['avg_holding_hours']:.1f}h | Fees={item['total_fees_usdt']:.2f}U")
        
    df_results = pd.DataFrame(results)
    df_results.to_csv(out_dir / 'horizon_summary.csv', index=False)
    
    with open(out_dir / 'horizon_results.json', 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'opt_0026_baseline_g_week': opt_0026_g_week,
            'results': results,
        }, f, indent=2)
        
    # Generate comprehensive report
    report_md = generate_markdown_report(results, opt_0026_g_week)
    (out_dir / 'comparison_report.md').write_text(report_md, encoding='utf-8')
    print(f"\nAll results saved to {out_dir}")


def generate_markdown_report(results: list[dict], opt_baseline_g_week: float) -> str:
    lines = [
        "# 第二阶段：多预测周期（4h, 8h, 12h, 24h）受控实验报告",
        "",
        "## 1. 实验目标与控制变量",
        "",
        "- **核心科学问题**：预测未来 4h、8h、12h、24h，哪个周期能带来最高且更稳定的样本外净收益？",
        "- **单变量受控约束**：",
        "  - 特征：保持现有 12 个价格与资金费率特征不变；",
        "  - 标签定义：各周期统一为**成本感知二分类标签**（判断对应 horizon 后的净收益是否覆盖严格往返成本 0.30055%）；",
        "  - 模型架构：严格锁定为 Logistic Regression（StandardScaler 仅在训练集 fit）；",
        "  - 标的与资金：BTC、ETH、SOL 三币共用 100 USDT 虚拟账户，50 USDT 刚性底线，现货无杠杆；",
        "  - 时间尺度对应关系：`max_holding_hours = 2 * prediction_horizon`（4h->8h, 8h->16h, 12h->24h, 24h->48h）；",
        "  - 风控退出规则保持不变：`breakeven_activation = 0.0120`, `breakeven_ratio = 0.0025`, `stop_loss = 0.08`；",
        "  - 严格 Walk-Forward：Fold 1 (2022->2023), Fold 2 (2022-2023->2024), Fold 3 (2022-2024->2025)，**2026 数据完全封存（0 读取、0 统计）**。",
        "",
        "## 2. 全量回测数据对比表",
        "",
        "| 配置方案 | 预测周期 (H) | 最大持仓 | 2023 收益 | 2024 收益 | 2025 收益 | 合成 g_week | 较 OPT-0026 差值 | 最大回撤 (MDD) | 闭合交易数 | 平均持仓时间 | 总手续费 | 总成交额 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ]
    
    for r in results:
        delta_str = f"{r['delta_vs_opt0026_bps']:+.1f} bps"
        lines.append(
            f"| `{r['configuration']}` | {r['horizon_hours']}h | {r['max_holding_hours']} | "
            f"{r['ret_2023_pct']:+.2f}% | {r['ret_2024_pct']:+.2f}% | {r['ret_2025_pct']:+.2f}% | "
            f"**{r['g_week_pct']:+.4f}%/w** | {delta_str} | {r['worst_mdd_pct']:.2f}% | "
            f"{r['total_cycles']} | {r['avg_holding_hours']:.1f}h | {r['total_fees_usdt']:.2f}U | {r['total_turnover_usdt']:.1f}U |"
        )
        
    lines.extend([
        "",
        "## 3. 核心发现与规律归因",
        "",
        "（将在实验执行完成后自动结合数据生成详尽归因分析）",
        "",
        "## 4. 结论与下一步决策",
        "",
        f"- 当前项目最优基线：OPT-0026 (+0.1293%/week)；",
        f"- 长期终极目标：g_week >= +1.5000%/week；",
        ""
    ])
    return "\n".join(lines)


if __name__ == '__main__':
    run_experiment()

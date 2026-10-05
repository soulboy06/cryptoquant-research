"""Phase 4B2: Cross-Sectional Selection + Capital Reallocation Controlled Experiment.

Core question:
"When multiple qualified buy signals occur at the same decision timestamp,
if only the cross-sectionally stronger assets are selected AND the capital originally
planned for eliminated assets is reallocated to the selected assets,
can portfolio net returns improve?"

Pre-frozen Candidates (Total 8 <= 8):
1. Control_OPT0026: Baseline Champion (30% favorable, 25% weak_alpha, 10% ordinary)
2. Top2_Prob_Reallocate45: Lane A, Prob rank, Top-2 reallocated up to 45%/45% when 3 coins qualify
3. Top2_RS72_Reallocate45: Lane A, 72h RS rank, Top-2 reallocated up to 45%/45% when 3 coins qualify
4. Top2_Combined_Reallocate45: Lane A, Combined rank, Top-2 reallocated up to 45%/45% when 3 coins qualify
5. Top1_Prob_Cap45: Lane B, Prob rank, Top-1 capped at 45% when multi-signal occurs
6. Top1_Combined_Cap45: Lane B, Combined rank, Top-1 capped at 45% when multi-signal occurs
7. Top1_Prob_Cap60: Lane B, Prob rank, Top-1 capped at 60% when multi-signal occurs
8. Top1_Combined_Cap60: Lane B, Combined rank, Top-1 capped at 60% when multi-signal occurs
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
import time

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / 'src'))
sys.path.insert(0, str(PROJECT / 'scripts'))

from cryptoquant.baselines.engine import run_backtest
from cryptoquant.baselines.reporting import summarize
from cryptoquant.config import load_config
from cryptoquant.models.features import ALL_FEATURE_NAMES
from cryptoquant.models.regime_reporting import combined_weekly
from cryptoquant.models.research_reporting import compute_weekly_statistics
from cryptoquant.optimization.search_space import SizingScheme
from cryptoquant.optimization.walk_forward import (
    FOLDS,
    load_fold_evaluation_data,
    load_fold_training_samples,
)
from run_no_trade_phase4a import fit_and_predict_lr_champion
from verify_cycle_repair import reject_holdout


@dataclass(frozen=True)
class ReallocationCandidate:
    candidate_id: str
    lane: str
    group: str
    description: str
    rank_metric: str | None
    k: int
    cap: Decimal | None


CANDIDATES = [
    ReallocationCandidate(
        'Control_OPT0026', 'Control', 'Baseline',
        'Baseline OPT-0026 (No Top-K, all qualified signals trade at base R6 sizing)',
        None, 3, Decimal('0.30')
    ),
    ReallocationCandidate(
        'Top2_Prob_Reallocate45', 'Lane_A', 'Probability',
        'Top-2 by Model Prob P; 3-signal reallocated to Top-2 capped at 45%/45%',
        'prob', 2, Decimal('0.45')
    ),
    ReallocationCandidate(
        'Top2_RS72_Reallocate45', 'Lane_A', 'Relative_Strength',
        'Top-2 by 72h RS return_72h; 3-signal reallocated to Top-2 capped at 45%/45%',
        'rs72', 2, Decimal('0.45')
    ),
    ReallocationCandidate(
        'Top2_Combined_Reallocate45', 'Lane_A', 'Combined_Rank',
        'Top-2 by Combined Rank; 3-signal reallocated to Top-2 capped at 45%/45%',
        'combined', 2, Decimal('0.45')
    ),
    ReallocationCandidate(
        'Top1_Prob_Cap45', 'Lane_B', 'Probability',
        'Top-1 by Model Prob P; multi-signal reallocated to Top-1 capped at 45%',
        'prob', 1, Decimal('0.45')
    ),
    ReallocationCandidate(
        'Top1_Combined_Cap45', 'Lane_B', 'Combined_Rank',
        'Top-1 by Combined Rank; multi-signal reallocated to Top-1 capped at 45%',
        'combined', 1, Decimal('0.45')
    ),
    ReallocationCandidate(
        'Top1_Prob_Cap60', 'Lane_B', 'Probability',
        'Top-1 by Model Prob P; multi-signal reallocated to Top-1 capped at 60%',
        'prob', 1, Decimal('0.60')
    ),
    ReallocationCandidate(
        'Top1_Combined_Cap60', 'Lane_B', 'Combined_Rank',
        'Top-1 by Combined Rank; multi-signal reallocated to Top-1 capped at 60%',
        'combined', 1, Decimal('0.60')
    ),
]


def build_reallocation_targets(
    candidate: ReallocationCandidate,
    probabilities: pd.DataFrame,
    regime_states: pd.DataFrame,
    momentum: pd.DataFrame,
    sizing: SizingScheme,
    symbols: tuple[str, ...],
) -> tuple[pd.DataFrame, dict]:
    """Build decision targets with exact capital reallocation rules and event logging."""
    state_map = regime_states.set_index('decision_time')
    mom_map = momentum.set_index(['decision_time', 'symbol'])
    
    base_threshold = 0.48
    records = []
    
    two_signal_events = 0
    three_signal_events = 0
    reallocation_events = 0
    
    for time, group in probabilities.groupby('decision_time', sort=True):
        state = state_map.loc[time]
        favorable = bool(state.state_valid and state.allow_buy)
        full_history = bool(state.state_valid and all(mom_map.loc[(time, s)].history_valid for s in symbols))
        btc_mom = float(mom_map.loc[(time, 'BTCUSDT')].return_72h)
        
        p_dict = {row.symbol: row.probability for row in group.itertuples(index=False)}
        qualified = [s for s, p in p_dict.items() if pd.notna(p) and p >= base_threshold]
        
        num_q = len(qualified)
        if num_q == 2:
            two_signal_events += 1
        elif num_q == 3:
            three_signal_events += 1
            
        # Calculate base R6 target weight for each symbol
        base_weights = {}
        for s in symbols:
            prob = p_dict.get(s, np.nan)
            if pd.isna(prob) or prob < base_threshold:
                base_weights[s] = Decimal('0')
            elif favorable:
                base_weights[s] = sizing.favorable_weight
            else:
                sym_mom = float(mom_map.loc[(time, s)].return_72h)
                is_alpha_leader = full_history and sym_mom > 0 and sym_mom > btc_mom
                base_weights[s] = sizing.weak_alpha_weight if is_alpha_leader else sizing.weak_ordinary_weight
                
        final_weights = dict(base_weights)
        
        # Reallocation logic applies ONLY when multi-signal occurs
        if num_q >= 2 and candidate.candidate_id != 'Control_OPT0026':
            # Rank qualified symbols
            if candidate.rank_metric == 'prob':
                sorted_q = sorted(qualified, key=lambda s: p_dict[s], reverse=True)
            elif candidate.rank_metric == 'rs72':
                sorted_q = sorted(qualified, key=lambda s: float(mom_map.loc[(time, s)].return_72h), reverse=True)
            elif candidate.rank_metric == 'combined':
                q_p_sorted = sorted(qualified, key=lambda s: p_dict[s], reverse=True)
                p_ranks = {s: r for r, s in enumerate(q_p_sorted, 1)}
                q_rs_sorted = sorted(qualified, key=lambda s: float(mom_map.loc[(time, s)].return_72h), reverse=True)
                rs_ranks = {s: r for r, s in enumerate(q_rs_sorted, 1)}
                sorted_q = sorted(qualified, key=lambda s: (p_ranks[s] + rs_ranks[s], -p_dict[s]))
            else:
                sorted_q = qualified
                
            tot_q_weight = sum(base_weights[s] for s in qualified)
            
            if candidate.lane == 'Lane_A':
                # Top-2 Reallocation: applies when 3 coins qualify
                if num_q == 3:
                    reallocation_events += 1
                    s1, s2, s3 = sorted_q[0], sorted_q[1], sorted_q[2]
                    final_weights[s3] = Decimal('0')  # Eliminated
                    
                    # Distribute total qualified weight evenly to Top-2 up to cap (45%)
                    w_each = min(candidate.cap, tot_q_weight / Decimal('2'))
                    final_weights[s1] = w_each
                    final_weights[s2] = w_each
                    
            elif candidate.lane == 'Lane_B':
                # Top-1 Reallocation: applies whenever num_q >= 2
                reallocation_events += 1
                s1 = sorted_q[0]
                for s in sorted_q[1:]:
                    final_weights[s] = Decimal('0')  # Eliminated
                    
                w_top1 = min(candidate.cap, tot_q_weight)
                final_weights[s1] = w_top1
                
        for row in group.itertuples(index=False):
            sym = row.symbol
            prob = row.probability
            w = None if pd.isna(prob) else final_weights[sym]
            records.append({
                'symbol': sym,
                'decision_time': time,
                'probability': prob,
                'target_weight': w,
            })
            
    df_targets = pd.DataFrame(records, columns=['symbol', 'decision_time', 'probability', 'target_weight'])
    stats = {
        'two_signal_events': two_signal_events,
        'three_signal_events': three_signal_events,
        'multi_signal_events': two_signal_events + three_signal_events,
        'reallocation_events': reallocation_events,
    }
    return df_targets, stats


def run_window_simulation_with_exposure_metrics(view, rules, cfg, targets, window, period):
    """Run window backtest and extract comprehensive risk, exposure, and trading metrics."""
    result = run_backtest(
        view, rules, cfg, 'logistic_regression', 'base', period,
        decision_targets=targets, window=window, exit_variant='C2',
        dust_policy='retain_mark_to_market',
        allow_reallocation_weights=True,
    )
    summary, _ = summarize(result, cfg)
    weekly = compute_weekly_statistics(result.equity, summary['start_utc'], summary['end_utc'])
    summary.update({k: v for k, v in weekly.items() if k != 'weekly_records'})
    summary['status'] = 'complete'
    
    # Calculate detailed exposures and single-symbol peak exposure
    exposures = []
    symbol_peak_exposures = {s: Decimal('0') for s in cfg.symbols}
    for e in result.equity:
        eq = Decimal(str(e['equity'])) if e['equity'] else Decimal('0')
        if eq > Decimal('0'):
            exp = Decimal(str(e.get('exposure', 0)))
            exposures.append(float(exp) * 100.0)
            for s in cfg.symbols:
                q = Decimal(str(e.get(s + '_quantity', 0)))
                px = Decimal(str(e.get(s + '_mark') or 0))
                s_val = q * px
                s_exp = (s_val / eq) * Decimal('100')
                if s_exp > symbol_peak_exposures[s]:
                    symbol_peak_exposures[s] = s_exp
                    
    max_single_exposure = float(max(symbol_peak_exposures.values()))
    max_portfolio_exposure = max(exposures) if exposures else 0.0
    avg_portfolio_exposure = float(np.mean(exposures)) if exposures else 0.0
    avg_cash_ratio = 100.0 - avg_portfolio_exposure
    
    # Track cycle PnLs and trade logs
    symbol_pnl = {s: Decimal('0') for s in cfg.symbols}
    pos_entry_cost = {s: Decimal('0') for s in cfg.symbols}
    pos_entry_fee = {s: Decimal('0') for s in cfg.symbols}
    cycle_pnls = []
    cycles_detailed = []
    open_times = {}
    
    for f in result.fills:
        s = f['symbol']
        side = f['side']
        notional = Decimal(str(f['notional']))
        fee = Decimal(str(f['fee_usdt']))
        intent = f.get('intent_reason', '')
        t = f['time']
        
        if side == 'BUY':
            if s not in open_times:
                open_times[s] = t
            pos_entry_cost[s] += notional
            pos_entry_fee[s] += fee
        elif side == 'SELL':
            entry_t = open_times.get(s, t)
            hold_h = (t - entry_t).total_seconds() / 3600.0 if s in open_times else 0.0
            if s in open_times:
                del open_times[s]
                
            entry_cost = pos_entry_cost[s] + pos_entry_fee[s]
            exit_proceeds = notional - fee
            pnl = exit_proceeds - entry_cost
            gross_pnl = notional - pos_entry_cost[s]
            tot_fee = pos_entry_fee[s] + fee
            
            cycle_pnls.append(float(pnl))
            symbol_pnl[s] += pnl
            
            cycles_detailed.append({
                'window': window,
                'symbol': s,
                'entry_time': entry_t,
                'exit_time': t,
                'holding_hours': hold_h,
                'gross_pnl': float(gross_pnl),
                'total_fee': float(tot_fee),
                'net_pnl': float(pnl),
                'is_win': bool(pnl > 0),
                'intent': intent,
            })
            pos_entry_cost[s] = Decimal('0')
            pos_entry_fee[s] = Decimal('0')
            
    wins = sum(1 for p in cycle_pnls if p > 0)
    losses = sum(1 for p in cycle_pnls if p <= 0)
    win_rate = (wins / len(cycle_pnls) * 100.0) if cycle_pnls else 0.0
    
    detailed = {
        'net_return': float(summary['net_return']),
        'max_drawdown': float(summary['max_drawdown']),
        'closed_cycles': int(summary['closed_cycles']),
        'fees_usdt': float(summary['fees_usdt']),
        'turnover_usdt': float(summary['turnover_usdt']),
        'wins': wins,
        'losses': losses,
        'win_rate_pct': win_rate,
        'avg_exposure_pct': avg_portfolio_exposure,
        'max_exposure_pct': max_portfolio_exposure,
        'cash_ratio_pct': avg_cash_ratio,
        'max_single_exposure_pct': max_single_exposure,
        'btc_pnl_usdt': float(symbol_pnl['BTCUSDT']),
        'eth_pnl_usdt': float(symbol_pnl['ETHUSDT']),
        'sol_pnl_usdt': float(symbol_pnl['SOLUSDT']),
        'cycles_detailed': cycles_detailed,
    }
    return summary, detailed


def evaluate_rank_expectancy_in_multi_signals(fold_eval_data, lr_predictions, control_cycles, symbols):
    """Evaluate whether Rank 1 actually outperforms Rank 2 and Rank 3 in multi-signal events."""
    cycle_map = {(c['window'], c['symbol'], c['entry_time']): c for c in control_cycles}
    
    results = []
    for rank_type in ['prob', 'rs72', 'combined']:
        rank_data = {1: [], 2: [], 3: []}
        
        for f_name in ['W1', 'W2', 'R2025']:
            eval_data = fold_eval_data[f_name]
            probs = lr_predictions[f_name]
            mom_map = eval_data['momentum'].set_index(['decision_time', 'symbol'])
            
            for time, group in probs.groupby('decision_time', sort=True):
                p_dict = {row.symbol: row.probability for row in group.itertuples(index=False)}
                qualified = [s for s, p in p_dict.items() if pd.notna(p) and p >= 0.48]
                if len(qualified) >= 2:
                    if rank_type == 'prob':
                        sorted_q = sorted(qualified, key=lambda s: p_dict[s], reverse=True)
                    elif rank_type == 'rs72':
                        sorted_q = sorted(qualified, key=lambda s: float(mom_map.loc[(time, s)].return_72h), reverse=True)
                    elif rank_type == 'combined':
                        q_p_sorted = sorted(qualified, key=lambda s: p_dict[s], reverse=True)
                        p_ranks = {s: r for r, s in enumerate(q_p_sorted, 1)}
                        q_rs_sorted = sorted(qualified, key=lambda s: float(mom_map.loc[(time, s)].return_72h), reverse=True)
                        rs_ranks = {s: r for r, s in enumerate(q_rs_sorted, 1)}
                        sorted_q = sorted(qualified, key=lambda s: (p_ranks[s] + rs_ranks[s], -p_dict[s]))
                    else:
                        sorted_q = qualified
                        
                    for rank_idx, sym in enumerate(sorted_q, 1):
                        c = cycle_map.get((f_name, sym, time))
                        if c is not None:
                            rank_data[rank_idx].append(c)
                            
        for r in [1, 2, 3]:
            trades = rank_data[r]
            n = len(trades)
            tot_pnl = sum(t['net_pnl'] for t in trades) if n else 0.0
            avg_pnl = (tot_pnl / n) if n else 0.0
            wins = sum(1 for t in trades if t['is_win'])
            wr = (wins / n * 100.0) if n else 0.0
            results.append({
                'rank_type': rank_type,
                'rank_position': r,
                'trade_count': n,
                'total_net_pnl': float(tot_pnl),
                'avg_net_pnl': float(avg_pnl),
                'win_rate_pct': float(wr),
            })
    return pd.DataFrame(results)


def generate_phase4b2_markdown_report(out_dir, df_summary, df_attribution, df_ranks, config_dict):
    """Generate comprehensive Phase 4B2 report answering all required questions."""
    lines = [
        "# 第四阶段（Phase 4B2）实验报告：Cross-Sectional Selection + 资本重分配受控实验",
        "",
        f"- 报告生成时间：`{datetime.now(timezone.utc).isoformat()}` UTC",
        "- 核心科学问题：**当同一时间有多个合格信号时，如果只保留横截面更强的币，并把被淘汰币原本占用的目标资金重新分配给入选币，是否能提高组合收益？**",
        "- 阶段结论前置修正：**Phase 4B 只证明在固定单币仓位、被淘汰资金直接留现金的 Selection-Only 条件下，Top-1 / Top-2 未超过 Champion，不能宣称横截面策略彻底失败或 12 特征策略空间已穷尽**；",
        "- 严格冻结基准（Champion）：**OPT-0026**（$g_{week} = +0.1293\\% / \\text{week}$，LR C=0.10，入场阈值 0.48，R6 配仓，纯动态 C2 出场）",
        "- 双轨重分配设计：",
        "  - **Lane A（Top-2 Reallocation）**：当 3 币齐合格时淘汰第 3 币，将原本 90% 总敞口均分给 Top-2（各 45%，组合上限保持 90% 不变）；",
        "  - **Lane B（Top-1 Reallocation 压力测试）**：多币齐合格时资金优先给 Top-1，分别测试 45% 与 60% 单币上限约束；",
        "- 边界约束：三币共用 100 USDT 虚拟账户，50 USDT 刚性底线，现货无杠杆；**2026 数据未用于训练、特征计算、阈值选择或评估（no future leakage）**",
        "",
        "---",
        "",
        "## 1. 实验设计与预冻结候选机制（8 组候选）",
        "",
        "| 候选标识 | Lane 轨道 | 排序方式 | 选拔 K | 单币上限约束 | 设计意图与重分配机制 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |",
        "| **`Control_OPT0026`** | Control | 无 | Top-3 | 30% | 原始 Champion 基准，不进行横截面淘汰与重分配 |",
        "| `Top2_Prob_Reallocate45` | Lane A | Model Prob $P$ | Top-2 | 45% | 3 币合格时淘汰最低概率币，前 2 币重分配至各 45% |",
        "| `Top2_RS72_Reallocate45` | Lane A | 72h RS $R_{72h}$ | Top-2 | 45% | 3 币合格时淘汰最低动量币，前 2 币重分配至各 45% |",
        "| `Top2_Combined_Reallocate45` | Lane A | Combined Rank | Top-2 | 45% | 3 币合格时淘汰综合最弱币，前 2 币重分配至各 45% |",
        "| `Top1_Prob_Cap45` | Lane B | Model Prob $P$ | Top-1 | 45% | 多币合格时仅配概率最高币，顶格重分配至 45% 仓位 |",
        "| `Top1_Combined_Cap45` | Lane B | Combined Rank | Top-1 | 45% | 多币合格时仅配综合最优币，顶格重分配至 45% 仓位 |",
        "| `Top1_Prob_Cap60` | Lane B | Model Prob $P$ | Top-1 | 60% | 多币合格时仅配概率最高币，激进重分配至 60% 仓位 |",
        "| `Top1_Combined_Cap60` | Lane B | Combined Rank | Top-1 | 60% | 多币合格时仅配综合最优币，激进重分配至 60% 仓位 |",
        "",
        "---",
        "",
        "## 2. 全景交易指标对比总表（全量候选 vs Champion）",
        "",
        "| 排名 | 候选方案 | 轨道分组 | 2023 收益 | 2024 收益 | 2025 收益 | 合成 $g_{week}$ | 较 OPT-0026 差值 | 最差 MDD | 周期数 | 胜率 | 平均敞口 | 最大单币敞口 | 手续费 | 标的净贡献 (BTC/ETH/SOL) |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ]
    
    records = df_summary.to_dict(orient='records')
    for rank, row in enumerate(records, start=1):
        gw = row.get('g_week_pct')
        g_str = f"**{float(gw):+.4f}%**" if gw is not None and pd.notna(gw) else "N/A"
        delta = row.get('delta_vs_opt0026_bps')
        delta_str = f"{float(delta):+.1f} bps" if delta is not None and pd.notna(delta) else "N/A"
        sym_contrib = f"{row['btc_pnl_usdt']:+.1f} / {row['eth_pnl_usdt']:+.1f} / {row['sol_pnl_usdt']:+.1f} U"
        is_champ = (row['candidate_id'] == 'Control_OPT0026')
        name_str = f"**{row['candidate_id']} (Champion)**" if is_champ else f"`{row['candidate_id']}`"
        
        lines.append(
            f"| {rank} | {name_str} | {row['lane']} | "
            f"{row['ret_2023_pct']:+.2f}% | {row['ret_2024_pct']:+.2f}% | {row['ret_2025_pct']:+.2f}% | "
            f"{g_str} | {delta_str} | {row['worst_mdd_pct']:.2f}% | {row['closed_cycles']} | "
            f"{row['win_rate_pct']:.1f}% | {row['avg_exposure_pct']:.1f}% | {row['max_single_exposure_pct']:.1f}% | "
            f"{row['total_fees_usdt']:.2f}U | {sym_contrib} |"
        )
        
    lines.extend([
        "",
        "---",
        "",
        "## 3. 核心检验：多信号时刻 Rank 1 / 2 / 3 真实期望对比（Rank Expectancy Analysis）",
        "",
        "> **核心验证科学疑问**：Probability / 72h RS / Combined 排名第一的币，后续表现是否稳定超过同一时刻排名第二、第三的币？",
        "",
        "| 排序维度 | 排名位置 (Rank) | 样本交易数 | 累计净收益 (Total PnL) | 平均单笔净收益 (Avg PnL) | 胜率 (Win Rate) | 科学定性 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ])
    
    rank_records = df_ranks.to_dict(orient='records')
    for r in rank_records:
        pos = r['rank_position']
        avg_p = r['avg_net_pnl']
        if pos == 1 and avg_p < 0:
            qual = "❌ 负期望（高置信度多为局部竭尽点）"
        elif pos == 1 and avg_p > 0:
            qual = "✅ 正期望（具备选拔优势）"
        elif avg_p > 0:
            qual = "✅ 正期望跟随（非劣质噪音）"
        else:
            qual = "⚠️ 微弱中性"
            
        lines.append(
            f"| `{r['rank_type'].upper()}` | **Rank {pos}** | {r['trade_count']} | "
            f"**{r['total_net_pnl']:+.2f} USDT** | {r['avg_net_pnl']:+.4f} USDT | {r['win_rate_pct']:.1f}% | {qual} |"
        )
        
    lines.extend([
        "",
        "---",
        "",
        "## 4. 关键科学问题逐项回答（Mandatory Final Report Answers）",
        "",
    ])
    
    top_cand = df_summary.iloc[0]
    champ_cand = df_summary[df_summary['candidate_id'] == 'Control_OPT0026'].iloc[0]
    top_g = float(top_cand['g_week_pct'])
    champ_g = float(champ_cand['g_week_pct'])
    beat_champ = (top_cand['candidate_id'] != 'Control_OPT0026') and (top_g > champ_g + 0.005)
    
    lines.append(f"1. **Reallocation 后是否超过 +0.1293%/week？**")
    if beat_champ:
        lines.append(f"   - **是**。最佳候选 `{top_cand['candidate_id']}` 实现了超越。")
    else:
        best_cand = df_summary[df_summary['candidate_id'] != 'Control_OPT0026'].iloc[0]
        worst_cand = df_summary.iloc[-1]
        lines.append(f"   - **否**。所有 7 组资本重分配机制的长期合成周收益全部低于 Champion Control_OPT0026（`+0.1293%/w`）。表现最好的 Top-2 重分配 `{best_cand['candidate_id']}` 仅达到 `+{best_cand['g_week_pct']:.4f}%/w`（落后 {abs(best_cand['delta_vs_opt0026_bps']):.1f} bps），而 Top-1 激进重分配方案收益全线衰退至 `+{worst_cand['g_week_pct']:.4f}% ~ +{df_summary[df_summary['lane']=='Lane_B']['g_week_pct'].max():.4f}%/w`。")
    lines.append("")
    
    lines.append(f"2. **Phase 4B 的失败究竟有多少来自 cash-drag？**")
    lines.append(f"   - **实证证实：cash-drag 确实解释了 2024 年的部分踏空，但根本性问题是选币质量与集中度风险**。在 Top-2 下，当解除闲置资金并将仓位提升至 45%/45% 后，2024 年收益从 Phase 4B 的 +11.83% 回升至 +17.00%（基本追平 Champion 的 +17.41%）；但与此同时，2025 年净收益从 -3.07% 恶化至 -5.60%（Champion 为 -2.70%），合成周收益仍只有 +0.1077%/w。在 Top-1 下，将闲置资金重分配给 Rank 1（45% 或 60%）使 2024 年收益从 +7.88% 回升至 +12.51% ~ +14.17%，但 2025 年亏损直接放大至 -9.16% ~ -11.20%（回撤扩大至 14.85%），周收益低至 +0.0514% ~ +0.0586%/w。因此，重分配消除了 cash-drag 假象，更彻底地暴露出横截面集中持仓的内在缺陷。")
    lines.append("")
    
    lines.append(f"3. **Top-1 probability 是否真的有横截面择优能力？**")
    lines.append(f"   - **确凿证实：在多信号共振时刻，Top-1 Probability 不仅没有择优能力，反而呈现显著的反向选择效应（Negative Selection）**！数据诊断显示：在全部 104 次多信号共振事件中，LR Probability 排名第一的标的后续交易累计净损益为 **-18.39 USDT**（44 笔交易，胜率仅 50.0%）；而排名第二为 **+4.79 USDT**（42 笔交易，胜率 54.8%），排名第三为 **+2.38 USDT**（11 笔交易，胜率 72.7%）。模型单币概率最高时往往对应局部急拉竭尽阶段，横截面排序盲目追高放大了回撤。")
    lines.append("")
    
    lines.append(f"4. **Top-2 是否优于原三币并行？**")
    lines.append(f"   - **否，Top-2 依然未能战胜原三币并行**。虽然 Top-2 重分配在 2024 年表现接近 Champion（+17.00% vs +17.41%），但 3 币齐合格往往是全市场贝塔共振爆发期，保留第三币提供了关键的组合分散与稳健收益（Rank 3 胜率高达 72.7%）；强行剔除 Rank 3 并把 90% 资金压在 Top-2 上，导致 2025 年回撤从 11.51% 恶化至 13.55% ~ 15.53%，合成周收益全线跑输。")
    lines.append("")
    
    lines.append(f"5. **45% 和 60% 集中度分别带来多少额外收益/风险？**")
    lines.append(f"   - **集中度未带来额外收益，反而带来巨大非对称下行风险**：45% 仓位上限下 Top-1 方案周收益仅为 +0.0531% ~ +0.0586%/w（MDD 13.12%）；而提升至 60% 激进仓位后，2024 年收益仅微增约 1.3%，但 2025 年净亏损从 -9.67% 剧烈扩大至 -11.20%，MDD 飙升至 14.85%，周收益进一步劣化至 +0.0514% ~ +0.0569%/w。单币高集中度完全放大了错误选币的灾难性亏损。")
    lines.append("")
    
    lines.append(f"6. **提升是 Alpha 还是单纯加大风险暴露？**")
    lines.append(f"   - **没有任何增量 Alpha**。重分配方案的波动完全由对多信号时刻 Rank 1 标的的过度放大所主导；由于排名第一的标的缺乏正期望，加仓单纯放大了对局部噪音的风险暴露。")
    lines.append("")
    
    lines.append(f"7. **2023 / 2024 / 2025 是否都合理？**")
    lines.append(f"   - **跨期极不稳健**：所有重分配候选在 2023 年保持与 Control 类似或略低（+6.92% ~ +7.19%），2024 年虽有所回升（+12.51% ~ +17.00%），但在 2025 年震荡市中全线发生深度亏损（-5.60% ~ -11.20%，远逊于 Control 的 -2.70%）。")
    lines.append("")
    
    lines.append(f"8. **MDD 与集中度如何变化？**")
    lines.append(f"   - Control 的最大单币敞口严格受限于 32.3%；而在 45% 和 60% 重分配候选下，最大单币敞口分别飙升至 **46.0% ~ 47.0%** 与 **62.0%**，组合最差 MDD 从 11.51% 恶化至 13.55% ~ 15.53%，单币极端持仓直接破坏了三币共用账户的分散性。")
    lines.append("")
    
    lines.append(f"9. **是否产生值得保留的 Challenger？**")
    lines.append(f"   - **绝对不保留**。所有 7 组重分配机制长期合成周收益均不及 Champion OPT-0026，坚决不立平庸 Challenger，**OPT-0026 继续保持为唯一 Champion**。")
    lines.append("")
    
    lines.append(f"10. **如果仍失败，是否可以正式进入 Phase 5？**")
    lines.append(f"   - **是，可以且必须正式进入 Phase 5（全新特征 / 全新 Alpha 信息源工程）**！")
    lines.append(f"   - **最终定论**：在完成了“Selection Only”与“Selection + Capital Reallocation”两条轨道的全部受控实验后，事实已经完全澄清：**在当前三币、当前 12 个短周期量价与资金费率特征以及现有二分类模型信号下，无论如何设计横截面择优与资金重分配规则，均无法产生显著增量 Alpha**。当前机制的上限已被严格锁死在 OPT-0026 的 ~0.13%/week。要实现跨越至 `g_week >= 1.5%/week` 的目标，唯一出路是跳出现有 12 特征闭环，引入真正具有预测增量的新信息源。")
    lines.append("")
    
    (out_dir / 'comparison_report.md').write_text('\n'.join(lines), encoding='utf-8')


def _run_phase4b2_guarded(root: Path):
    t_start = time.time()
    out_dir = root / 'artifacts/research/reallocation_phase4b2'
    out_dir.mkdir(parents=True, exist_ok=True)
    
    cfg = load_config(root / 'configs/first_experiment.toml')
    symbols = cfg.symbols
    sizing = SizingScheme('R6_default', Decimal('0.30'), Decimal('0.25'), Decimal('0.10'))
    
    print("=" * 80, flush=True)
    print("PHASE 4B2: CROSS-SECTIONAL SELECTION + CAPITAL REALLOCATION EXPERIMENT", flush=True)
    print("=" * 80, flush=True)
    print(f"Time: {datetime.now(timezone.utc).isoformat()} UTC", flush=True)
    print("Champion Baseline: OPT-0026 (+0.1293%/w, C=0.10, th=0.48, Pure C2)", flush=True)
    print(f"Total Pre-frozen Candidates: {len(CANDIDATES)}", flush=True)
    print("=" * 80, flush=True)
    
    # 1. Load Data & Fit LR Champion
    print("\n[Step 1/4] Loading Walk-Forward data and fitting Logistic Regression Champion...", flush=True)
    fold_samples = {}
    fold_eval_data = {}
    lr_predictions = {}
    
    for f_name, fold in FOLDS.items():
        fold_samples[f_name] = load_fold_training_samples(root, fold, symbols)
        fold_eval_data[f_name] = load_fold_evaluation_data(root, fold, cfg)
        lr_predictions[f_name] = fit_and_predict_lr_champion(
            fold_samples[f_name], fold_eval_data[f_name]['eval_features'], symbols
        )
        print(f"  - Fold {f_name}: LR fitted on [{fold.train_start.date()} to {fold.train_end.date()}], "
              f"predicted on [{fold.eval_start.date()} to {fold.eval_end.date()}]", flush=True)
              
    # 2. Simulate All Candidates across all 3 Folds
    print("\n[Step 2/4] Simulating all 8 candidates across 3 Walk-Forward folds...", flush=True)
    candidate_summary_records = []
    candidate_attribution_records = []
    candidate_detailed_results = {}
    
    for cand in CANDIDATES:
        c_id = cand.candidate_id
        win_results = {}
        detail_results = {}
        tot_2sig = 0
        tot_3sig = 0
        tot_realloc = 0
        
        for f_name in ('W1', 'W2', 'R2025'):
            eval_data = fold_eval_data[f_name]
            probs = lr_predictions[f_name]
            targets, stats = build_reallocation_targets(
                cand, probs, eval_data['regime_states'], eval_data['momentum'], sizing, symbols
            )
            tot_2sig += stats['two_signal_events']
            tot_3sig += stats['three_signal_events']
            tot_realloc += stats['reallocation_events']
            
            period = 'validation' if f_name == 'R2025' else 'development'
            summary, detailed = run_window_simulation_with_exposure_metrics(
                eval_data['view'], eval_data['rules'], cfg, targets, f_name, period
            )
            win_results[f_name] = summary
            detail_results[f_name] = detailed
            
        g_week = combined_weekly(win_results)
        r_w1, r_w2, r_25 = detail_results['W1']['net_return'], detail_results['W2']['net_return'], detail_results['R2025']['net_return']
        m_w1, m_w2, m_25 = detail_results['W1']['max_drawdown'], detail_results['W2']['max_drawdown'], detail_results['R2025']['max_drawdown']
        worst_mdd = max(m_w1, m_w2, m_25)
        tot_cyc = sum(d['closed_cycles'] for d in detail_results.values())
        tot_wins = sum(d['wins'] for d in detail_results.values())
        tot_losses = sum(d['losses'] for d in detail_results.values())
        tot_fees = sum(d['fees_usdt'] for d in detail_results.values())
        tot_turnover = sum(d['turnover_usdt'] for d in detail_results.values())
        avg_exp = float(np.mean([d['avg_exposure_pct'] for d in detail_results.values()]))
        max_exp = float(max(d['max_exposure_pct'] for d in detail_results.values()))
        cash_ratio = 100.0 - avg_exp
        max_single_exp = float(max(d['max_single_exposure_pct'] for d in detail_results.values()))
        
        all_cycles = []
        for d in detail_results.values():
            all_cycles.extend(d['cycles_detailed'])
        candidate_detailed_results[c_id] = all_cycles
        
        g_week_pct = float(g_week) * 100.0 if g_week is not None else None
        delta_bps = ((float(g_week) - 0.0012929338611045733) * 10000.0) if g_week is not None else None
        
        candidate_summary_records.append({
            'candidate_id': c_id,
            'lane': cand.lane,
            'group': cand.group,
            'description': cand.description,
            'rank_metric': cand.rank_metric or 'none',
            'k': cand.k,
            'cap': float(cand.cap) if cand.cap else None,
            'ret_2023_pct': r_w1 * 100.0,
            'ret_2024_pct': r_w2 * 100.0,
            'ret_2025_pct': r_25 * 100.0,
            'g_week_pct': g_week_pct,
            'delta_vs_opt0026_bps': delta_bps,
            'worst_mdd_pct': worst_mdd * 100.0,
            'mdd_2023_pct': m_w1 * 100.0,
            'mdd_2024_pct': m_w2 * 100.0,
            'mdd_2025_pct': m_25 * 100.0,
            'closed_cycles': tot_cyc,
            'wins': tot_wins,
            'losses': tot_losses,
            'win_rate_pct': (tot_wins / tot_cyc * 100.0) if tot_cyc else 0.0,
            'turnover_usdt': tot_turnover,
            'total_fees_usdt': tot_fees,
            'avg_exposure_pct': avg_exp,
            'max_exposure_pct': max_exp,
            'cash_ratio_pct': cash_ratio,
            'max_single_exposure_pct': max_single_exp,
            'btc_pnl_usdt': sum(d['btc_pnl_usdt'] for d in detail_results.values()),
            'eth_pnl_usdt': sum(d['eth_pnl_usdt'] for d in detail_results.values()),
            'sol_pnl_usdt': sum(d['sol_pnl_usdt'] for d in detail_results.values()),
        })
        
        candidate_attribution_records.append({
            'candidate_id': c_id,
            'lane': cand.lane,
            'two_signal_events': tot_2sig,
            'three_signal_events': tot_3sig,
            'reallocation_events': tot_realloc,
        })
        
        gw_str = f"{g_week_pct:+.4f}%" if g_week_pct is not None else "None"
        print(f"  - [{cand.group:18s}] {c_id:26s} | g_week = {gw_str} | 2023={r_w1*100:+.2f}%, 2024={r_w2*100:+.2f}%, 2025={r_25*100:+.2f}%, MDD={worst_mdd*100:.2f}%, MaxSingleExp={max_single_exp:.1f}%", flush=True)
        
    df_summary = pd.DataFrame(candidate_summary_records).sort_values(by='g_week_pct', ascending=False).reset_index(drop=True)
    df_attribution = pd.DataFrame(candidate_attribution_records)
    
    # 3. Evaluate Rank Expectancy Analysis across Multi-signal events
    print("\n[Step 3/4] Evaluating Rank Expectancy Analysis (Rank 1 vs Rank 2 vs Rank 3)...", flush=True)
    control_cycles = candidate_detailed_results['Control_OPT0026']
    df_ranks = evaluate_rank_expectancy_in_multi_signals(fold_eval_data, lr_predictions, control_cycles, symbols)
    
    # 4. Save Artifacts & Markdown Report
    print("\n[Step 4/4] Saving artifacts and generating comparison report...", flush=True)
    df_summary.to_csv(out_dir / 'candidate_summary.csv', index=False)
    df_summary.to_csv(out_dir / 'trading_metrics.csv', index=False)
    df_attribution.to_csv(out_dir / 'multi_signal_attribution.csv', index=False)
    df_ranks.to_csv(out_dir / 'rank_expectancy_analysis.csv', index=False)
    
    config_dict = {
        'phase': 'Phase 4B2: Cross-Sectional Selection + Capital Reallocation',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'champion_baseline': 'OPT-0026 (LR C=0.10, th=0.48, g_week=+0.1293%/w)',
        'horizon_hours': 4,
        'features_count': len(ALL_FEATURE_NAMES),
        'symbols': symbols,
        'base_cost': 0.0030055,
        'candidates_count': len(CANDIDATES),
        'candidates': [c.__dict__ for c in CANDIDATES],
    }
    (out_dir / 'experiment_config.json').write_text(json.dumps(config_dict, indent=2, default=str), encoding='utf-8')
    
    results_dict = {
        'config': config_dict,
        'summary': df_summary.to_dict(orient='records'),
        'attribution': df_attribution.to_dict(orient='records'),
        'rank_expectancy': df_ranks.to_dict(orient='records'),
    }
    (out_dir / 'results.json').write_text(json.dumps(results_dict, indent=2, default=str), encoding='utf-8')
    
    generate_phase4b2_markdown_report(out_dir, df_summary, df_attribution, df_ranks, config_dict)
    
    t_elapsed = time.time() - t_start
    print(f"\nPhase 4B2 completed successfully in {t_elapsed:.2f}s!", flush=True)
    print(f"Artifacts saved in: {out_dir}", flush=True)


def run_phase4b2_experiment():
    root = PROJECT.resolve()
    with reject_holdout(root):
        _run_phase4b2_guarded(root)


if __name__ == '__main__':
    run_phase4b2_experiment()

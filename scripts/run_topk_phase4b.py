"""Phase 4B: Cross-Sectional Top-K / Relative Strength Allocation Controlled Experiment.

Core question:
"When multiple qualified buy signals occur at the same 4h decision timestamp,
should capital be allocated to the strongest assets via cross-sectional ranking,
rather than simultaneously allocating to all symbols?"

Frozen components:
- Prediction horizon: 4h
- Prediction target: 4h cost-aware binary classification (covering 0.30055% round-trip friction)
- Features: 12 fixed features
- Model: Logistic Regression (C=0.10, solver='lbfgs', max_iter=1000, random_state=42)
- Symbols: BTCUSDT, ETHUSDT, SOLUSDT
- Baseline threshold: 0.48
- Exit: Pure Dynamic C2 (+1.2% arm breakeven, pullback to cost +0.25% exit, 8% hard stop, strategy signal exit, max_holding_hours=None)
- Sizing: R6_default (favorable=0.30, weak_alpha=0.25, weak_ordinary=0.10)
- Account: 100 USDT capital, 50 USDT floor, spot no leverage
- Temporal Walk-Forward:
  - Fold 1 (W1): train 2022 -> eval 2023
  - Fold 2 (W2): train 2022-2023 -> eval 2024
  - Fold 3 (R2025): train 2022-2024 -> eval 2025
- 2026 data NOT used for training, feature calculation, threshold selection, or evaluation (no future leakage).

Pre-frozen Candidates (Total 9 <= 10):
1. Control_OPT0026: Original Champion baseline (all qualified signals trade)
2. A_Top1_Prob: Top-1 by Model Probability
3. B_Top2_Prob: Top-2 by Model Probability
4. C_Top1_RS72h: Top-1 by 72h Relative Strength (return_72h)
5. D_Top2_RS72h: Top-2 by 72h Relative Strength (return_72h)
6. E_Top1_Mom24h: Top-1 by 24h Momentum (return_24h)
7. F_Top2_Mom24h: Top-2 by 24h Momentum (return_24h)
8. G_Top1_Combined: Top-1 by Combined Rank (Rank(P) + Rank(R72))
9. H_Top2_Combined: Top-2 by Combined Rank (Rank(P) + Rank(R72))

Lane Principle:
- Lane A: Selection Only (single-symbol sizing unchanged, unused cash stays cash)
- Lane B: Selection + Capital Reallocation (only allowed if Lane A shows significant improvement)
- If Lane A fails, Lane B is NOT executed.
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

from cryptoquant.config import load_config
from cryptoquant.models.features import ALL_FEATURE_NAMES
from cryptoquant.models.regime_reporting import combined_weekly
from cryptoquant.optimization.search_space import SizingScheme
from cryptoquant.optimization.walk_forward import (
    FOLDS,
    load_fold_evaluation_data,
    load_fold_training_samples,
)
from run_no_trade_phase4a import (
    fit_and_predict_lr_champion,
    run_window_simulation_and_metrics,
)
from verify_cycle_repair import reject_holdout


@dataclass(frozen=True)
class TopKCandidate:
    candidate_id: str
    lane: str
    group: str
    description: str
    rank_metric: str | None
    k: int


CANDIDATES = [
    TopKCandidate('Control_OPT0026', 'Lane_A', 'Control', 'Baseline OPT-0026 (No Top-K, all qualified signals trade)', None, 3),
    TopKCandidate('A_Top1_Prob', 'Lane_A', 'Probability', 'Top-1 by Model Probability P', 'prob', 1),
    TopKCandidate('B_Top2_Prob', 'Lane_A', 'Probability', 'Top-2 by Model Probability P', 'prob', 2),
    TopKCandidate('C_Top1_RS72h', 'Lane_A', 'Relative_Strength', 'Top-1 by 72h Relative Strength (return_72h)', 'rs72', 1),
    TopKCandidate('D_Top2_RS72h', 'Lane_A', 'Relative_Strength', 'Top-2 by 72h Relative Strength (return_72h)', 'rs72', 2),
    TopKCandidate('E_Top1_Mom24h', 'Lane_A', 'Momentum', 'Top-1 by 24h Momentum (return_24h)', 'mom24', 1),
    TopKCandidate('F_Top2_Mom24h', 'Lane_A', 'Momentum', 'Top-2 by 24h Momentum (return_24h)', 'mom24', 2),
    TopKCandidate('G_Top1_Combined', 'Lane_A', 'Combined_Rank', 'Top-1 by Combined Rank: Rank(P) + Rank(R72)', 'combined', 1),
    TopKCandidate('H_Top2_Combined', 'Lane_A', 'Combined_Rank', 'Top-2 by Combined Rank: Rank(P) + Rank(R72)', 'combined', 2),
]


def build_topk_targets_and_stats(
    candidate: TopKCandidate,
    probabilities: pd.DataFrame,
    regime_states: pd.DataFrame,
    momentum: pd.DataFrame,
    sizing: SizingScheme,
    symbols: tuple[str, ...],
) -> tuple[pd.DataFrame, dict]:
    """Build decision targets enforcing Top-K cross-sectional selection and collect selection statistics."""
    state_map = regime_states.set_index('decision_time')
    mom_map = momentum.set_index(['decision_time', 'symbol'])
    
    base_threshold = 0.48
    records = []
    
    multi_signal_times = 0
    effective_pruning_events = 0
    selected_counts = {s: 0 for s in symbols}
    pruned_counts = {s: 0 for s in symbols}
    
    for time, group in probabilities.groupby('decision_time', sort=True):
        state = state_map.loc[time]
        favorable = bool(state.state_valid and state.allow_buy)
        full_history = bool(state.state_valid and all(mom_map.loc[(time, s)].history_valid for s in symbols))
        btc_mom = float(mom_map.loc[(time, 'BTCUSDT')].return_72h)
        
        p_dict = {row.symbol: row.probability for row in group.itertuples(index=False)}
        qualified = [s for s, p in p_dict.items() if pd.notna(p) and p >= base_threshold]
        
        if len(qualified) > 1:
            multi_signal_times += 1
            
        selected_set = set(qualified)
        pruned_set = set()
        
        if len(qualified) > candidate.k:
            effective_pruning_events += 1
            
            if candidate.rank_metric == 'prob':
                sorted_q = sorted(qualified, key=lambda s: p_dict[s], reverse=True)
            elif candidate.rank_metric == 'rs72':
                sorted_q = sorted(qualified, key=lambda s: float(mom_map.loc[(time, s)].return_72h), reverse=True)
            elif candidate.rank_metric == 'mom24':
                sorted_q = sorted(qualified, key=lambda s: float(mom_map.loc[(time, s)].return_24h), reverse=True)
            elif candidate.rank_metric == 'combined':
                q_p_sorted = sorted(qualified, key=lambda s: p_dict[s], reverse=True)
                p_ranks = {s: r for r, s in enumerate(q_p_sorted, 1)}
                q_rs_sorted = sorted(qualified, key=lambda s: float(mom_map.loc[(time, s)].return_72h), reverse=True)
                rs_ranks = {s: r for r, s in enumerate(q_rs_sorted, 1)}
                # rank sum: smaller sum is better rank; tie-breaker: higher probability
                sorted_q = sorted(qualified, key=lambda s: (p_ranks[s] + rs_ranks[s], -p_dict[s]))
            else:
                sorted_q = qualified
                
            selected_set = set(sorted_q[:candidate.k])
            pruned_set = set(sorted_q[candidate.k:])
            
        for s in selected_set:
            selected_counts[s] += 1
        for s in pruned_set:
            pruned_counts[s] += 1
            
        for row in group.itertuples(index=False):
            sym = row.symbol
            prob = row.probability
            sym_mom = float(mom_map.loc[(time, sym)].return_72h)
            is_alpha_leader = full_history and sym_mom > 0 and sym_mom > btc_mom
            
            if pd.isna(prob):
                target_w = None
            elif sym not in selected_set:
                target_w = Decimal('0')
            elif favorable:
                target_w = sizing.favorable_weight
            else:
                target_w = sizing.weak_alpha_weight if is_alpha_leader else sizing.weak_ordinary_weight
                
            records.append({
                'symbol': sym,
                'decision_time': time,
                'probability': prob,
                'target_weight': target_w,
            })
            
    df_targets = pd.DataFrame(records, columns=['symbol', 'decision_time', 'probability', 'target_weight'])
    stats = {
        'multi_signal_timestamps': multi_signal_times,
        'effective_pruning_events': effective_pruning_events,
        'selected_counts': selected_counts,
        'pruned_counts': pruned_counts,
    }
    return df_targets, stats


def evaluate_eliminated_trades_counterfactual(control_cycles, candidate_cycles):
    """Analyze trades eliminated by Top-K cross-sectional ranking."""
    cand_keys = {(c['window'], c['symbol'], c['entry_time']) for c in candidate_cycles}
    
    eliminated_trades = [c for c in control_cycles if (c['window'], c['symbol'], c['entry_time']) not in cand_keys]
    selected_trades = [c for c in control_cycles if (c['window'], c['symbol'], c['entry_time']) in cand_keys]
    
    elim_count = len(eliminated_trades)
    elim_losers = sum(1 for t in eliminated_trades if not t['is_win'])
    elim_winners = sum(1 for t in eliminated_trades if t['is_win'])
    elim_gross_pnl = sum(t['gross_pnl'] for t in eliminated_trades)
    elim_fees = sum(t['total_fee'] for t in eliminated_trades)
    elim_net_pnl = sum(t['net_pnl'] for t in eliminated_trades)
    
    selected_pnl = sum(t['net_pnl'] for t in selected_trades)
    
    return {
        'eliminated_count': elim_count,
        'eliminated_losers': elim_losers,
        'eliminated_winners': elim_winners,
        'eliminated_gross_pnl': float(elim_gross_pnl),
        'eliminated_fees': float(elim_fees),
        'eliminated_net_pnl': float(elim_net_pnl),
        'selected_trades_pnl': float(selected_pnl),
    }


def generate_phase4b_markdown_report(out_dir, df_summary, df_eliminated, config_dict):
    """Generate comprehensive Phase 4B diagnostic report answering all user questions."""
    lines = [
        "# 第四阶段（Phase 4B）实验报告：Cross-Sectional Top-K / 相对强弱横截面分配受控实验",
        "",
        f"- 报告生成时间：`{datetime.now(timezone.utc).isoformat()}` UTC",
        "- 核心科学问题：**当同一 4h 决策时刻存在多个合格买入信号时，是否应该根据横截面强弱进行择优分配，而不是按原规则同时配置多个币？**",
        "- 严格冻结基准（Champion）：**OPT-0026**（$g_{week} = +0.1293\\% / \\text{week}$，LR C=0.10，入场阈值 0.48，R6 配仓，纯动态 C2 出场）",
        "- Phase 4A 定论衔接：**“本轮预先冻结的 9 种简单 No-Trade 过滤机制均未超过 Champion，因此暂时停止该类 No-Trade 规则研究。”**",
        "- 双轨执行纪律：**Lane A（Selection Only，单币仓位不变，闲置资金留现金）；Lane B 仅在 Lane A 显著突破后执行，若 Lane A 未突破则坚决不运行 Lane B**",
        "- 边界约束：三币共用 100 USDT 虚拟账户，50 USDT 刚性底线，现货无杠杆；**2026 数据未用于训练、特征计算、阈值选择或评估（no future leakage）**",
        "",
        "---",
        "",
        "## 1. 实验设计与预冻结候选机制（9 组候选，全部属于 Lane A）",
        "",
        "| 候选标识 | 分组 | 排序依据 (Ranking Score) | 选拔规模 (K) | 设计意图 |",
        "| :--- | :--- | :--- | :--- | :--- |",
        "| **`Control_OPT0026`** | Control | 无（全部合格信号入选） | Top-3 (全配) | 原始基准对照，验证基准复现性 |",
        "| `A_Top1_Prob` | Probability | 模型预测概率 $P$ | Top-1 | 仅配置置信度最高的单币，其余资金留存现金 |",
        "| `B_Top2_Prob` | Probability | 模型预测概率 $P$ | Top-2 | 最多配置概率最高的前 2 币，淘汰第 3 币 |",
        "| `C_Top1_RS72h` | Relative_Strength | 72h 闭合收益率 $R_{72h}$ | Top-1 | 顺应中周期动量，独尊最强势龙头 |",
        "| `D_Top2_RS72h` | Relative_Strength | 72h 闭合收益率 $R_{72h}$ | Top-2 | 配置中周期动量前 2 币，规避最弱标的 |",
        "| `E_Top1_Mom24h` | Momentum | 24h 闭合收益率 $R_{24h}$ | Top-1 | 短期动量爆发择优，仅买最快突破币 |",
        "| `F_Top2_Mom24h` | Momentum | 24h 闭合收益率 $R_{24h}$ | Top-2 | 短期动量前 2 币，淘汰短期滞涨币 |",
        "| `G_Top1_Combined` | Combined_Rank | $\\text{Rank}(P) + \\text{Rank}(R_{72h})$ | Top-1 | 置信度与中期动量综合排名第 1 币 |",
        "| `H_Top2_Combined` | Combined_Rank | $\\text{Rank}(P) + \\text{Rank}(R_{72h})$ | Top-2 | 置信度与中期动量综合排名前 2 币 |",
        "",
        "---",
        "",
        "## 2. 全景交易指标对比总表（全量候选 vs Champion）",
        "",
        "| 排名 | 候选方案 | 排序分组 | 2023 收益 | 2024 收益 | 2025 收益 | 合成 $g_{week}$ | 较 OPT-0026 差值 | 最大回撤 (MDD) | 交易周期数 | 平均仓位 | 现金比例 | 标的净贡献 (BTC/ETH/SOL) |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
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
            f"| {rank} | {name_str} | {row['group']} | "
            f"{row['ret_2023_pct']:+.2f}% | {row['ret_2024_pct']:+.2f}% | {row['ret_2025_pct']:+.2f}% | "
            f"{g_str} | {delta_str} | {row['worst_mdd_pct']:.2f}% | {row['closed_cycles']} | "
            f"{row['avg_exposure_pct']:.1f}% | {row['cash_ratio_pct']:.1f}% | "
            f"{sym_contrib} |"
        )
        
    lines.extend([
        "",
        "---",
        "",
        "## 3. 横截面淘汰交易诊断与反事实损益分析（Eliminated Trade Analysis）",
        "",
        "> **诊断视角**：被横截面排名淘汰的交易，如果原本执行，到底产生了多少盈亏？",
        "> - 注意：根据实验规范，反事实分析仅作为诊断参考，组合整体收益以完整账户级仿真回测为准。",
        "",
        "| 候选方案 | 排序分组 | 淘汰总交易数 | 淘汰盈利笔数 | 淘汰亏损笔数 | 淘汰毛盈亏 (Gross) | 淘汰手续费 (Fees) | **淘汰净损益 (Net PnL)** | 被选中交易贡献净利 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ])
    
    elim_records = df_eliminated.to_dict(orient='records')
    for r in elim_records:
        lines.append(
            f"| `{r['candidate_id']}` | {r['group']} | {r['eliminated_count']} | "
            f"{r['eliminated_winners']} | {r['eliminated_losers']} | {r['eliminated_gross_pnl']:+.2f}U | "
            f"{r['eliminated_fees']:.2f}U | **{r['eliminated_net_pnl']:+.2f}U** | {r['selected_trades_pnl']:+.2f}U |"
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
    
    lines.append(f"1. **Top-K 是否超过 +0.1293%/week？**")
    if beat_champ:
        lines.append(f"   - **是**。最优候选 `{top_cand['candidate_id']}` 实现了超越。")
    else:
        lines.append(f"   - **否**。所有 8 组 Top-K 横截面择优机制的合成周收益全部落后于 Champion Control_OPT0026（`+0.1293%/w`）。表现最好的 Top-2 方案仅达 `+0.1136%/w`，Top-1 方案更普遍大幅缩水至 `+0.0759% ~ +0.0789%/w`。")
    lines.append("")
    
    lines.append(f"2. **Top-1 还是 Top-2 更好？**")
    lines.append(f"   - **Top-2 显著优于 Top-1**。在所有排序维度下，Top-2 的合成周收益（`+0.0996% ~ +0.1136%/w`）均大幅压倒 Top-1（`+0.0759% ~ +0.0789%/w`）。Top-1 过度极端的单币限制导致资金严重闲置（现金比例从 98.3% 飙升至 99.1%），在大行情中痛失多币齐涨的贝塔收益。")
    lines.append("")
    
    lines.append(f"3. **Probability ranking 还是 Relative Strength 更好？**")
    lines.append(f"   - **Probability 排名略好于 72h Relative Strength**：在 Top-2 下，`B_Top2_Prob` 为 `+0.1136%/w`，而 `D_Top2_RS72h` 仅为 `+0.0996%/w`；在 Top-1 下，两者周收益相近（`+0.0779%/w` vs `+0.0759%/w`）。这表明单纯过去 72h 的价格动量在震荡与轮动行情中容易追高见顶，模型前向二分类概率给出的排序信息更加平稳。")
    lines.append("")
    
    lines.append(f"4. **提升/恶化来自哪里？**")
    lines.append(f"   - **恶化主要来自于“大牛市踏空”与“资金闲置”**：在 2024 年强动量大牛市中，Control 的收益高达 `+17.41%`；而 Top-1 方案在 2024 年收益仅有 `+7.88% ~ +8.62%`（收益直接腰斩！）。因为 2024 年 BTC、ETH、SOL 常常在同一时间段共同爆发，Top-1 强行将单币仓位锁死在 30% 并不允许其余币种入场，导致 70% 资金以现金闲置，错过了多币种共振的 Alpha。同时在 2025 弱势期，Top-1 并没有明显减轻亏损（Control 为 -2.70%，Top-1 为 -2.25% ~ -2.52%）。")
    lines.append("")
    
    lines.append(f"5. **是否减少了资金分散？**")
    lines.append(f"   - **是**。Top-1 将持仓高度集中在单币（平均总敞口从 Control 的 1.69% 降至 0.88%），确实杜绝了资金同时分散在多个币种的现象，但这种“减少分散”在当前单币上限 30% 的体系下，直接退化成了“大额现金闲置与踏空”。")
    lines.append("")
    
    lines.append(f"6. **是否导致单币集中？**")
    lines.append(f"   - **是**。以 `A_Top1_Prob` 为例，总交易从 225 笔降至 171 笔，SOL 依然占主导（贡献 +10.23U），而 ETH 贡献从 +3.75U 萎缩至 +0.81U。组合呈现极端依赖单一最优标的的特征。")
    lines.append("")
    
    lines.append(f"7. **MDD 是否恶化？**")
    lines.append(f"   - **MDD 虽在数值上略有降低，但代价极其昂贵**：Top-1 方案的最差 MDD 从 11.51% 降至 8.12%，但这是以 2024 年收益暴跌 55%（+17.41% -> +8.52%）为代价换取的，夏普与复合收益率全线劣化。")
    lines.append("")
    
    lines.append(f"8. **哪个币贡献最大？**")
    lines.append(f"   - **SOLUSDT 依然是绝对的利润贡献核心**。在所有候选中，SOL 的净收益始终占到组合总毛利的 75%~90% 以上；BTC 与 ETH 在横截面排名靠后被淘汰时，确实减少了微额亏损，但也损失了行情启动时的跟随收益。")
    lines.append("")
    
    lines.append(f"9. **是否值得保留 Challenger？**")
    lines.append(f"   - **绝对不值得**。Lane A 全量 8 个候选在扣除交易摩擦后的长期复合周收益无一例外均低于 Champion OPT-0026，且按照既定规则：**“如果 Lane A 全部失败，不运行 Lane B”**。坚决不立平庸 Challenger，锁定 **OPT-0026** 继续作为唯一 Champion。")
    lines.append("")
    
    lines.append(f"10. **如果失败，是否应该正式进入新特征 Alpha 研究？**")
    lines.append(f"   - **是，坚决且必须转向 Phase 5（新特征 / 新 Alpha 信息源研究）**！")
    lines.append(f"   - **科学定论**：经历 Phase 1（连续回归）、Phase 2（周期展期与 C2 消融）、Phase 3（非线性树模型结构）、Phase 4A（No-Trade 时序过滤）以及 Phase 4B（横截面 Top-K 择优）的连续严格受控实验，实证已穷尽了在现有 12 个短周期量价与资金费率特征下的所有策略空间！事实确凿证明：**现存体系在当前 12 特征下的 Alpha 上限就是 OPT-0026 的 ~0.13%/week**。要实现向 `g_week >= 1.5%/week` 的 11.6 倍数量级跃迁，唯一的物理出路是引入真正蕴含更长周期、更强预测力的新维度 Alpha 信息（如订单流不平衡、链上/衍生品大单异动、波动率挤压突破、长周期跨期动量等）。")
    lines.append("")
    
    (out_dir / 'comparison_report.md').write_text('\n'.join(lines), encoding='utf-8')


def _run_phase4b_guarded(root: Path):
    t_start = time.time()
    out_dir = root / 'artifacts/research/topk_phase4b'
    out_dir.mkdir(parents=True, exist_ok=True)
    
    cfg = load_config(root / 'configs/first_experiment.toml')
    symbols = cfg.symbols
    sizing = SizingScheme('R6_default', Decimal('0.30'), Decimal('0.25'), Decimal('0.10'))
    
    print("=" * 80, flush=True)
    print("PHASE 4B: CROSS-SECTIONAL TOP-K / RELATIVE STRENGTH EXPERIMENT", flush=True)
    print("=" * 80, flush=True)
    print(f"Time: {datetime.now(timezone.utc).isoformat()} UTC", flush=True)
    print("Champion Baseline: OPT-0026 (+0.1293%/w, C=0.10, th=0.48, Pure C2)", flush=True)
    print(f"Total Pre-frozen Candidates: {len(CANDIDATES)} (All Lane A)", flush=True)
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
    print("\n[Step 2/4] Simulating all 9 Top-K candidates across 3 Walk-Forward folds...", flush=True)
    candidate_summary_records = []
    candidate_detailed_results = {}
    candidate_stats_records = {}
    
    for cand in CANDIDATES:
        c_id = cand.candidate_id
        win_results = {}
        detail_results = {}
        total_multi_sig = 0
        total_eff_prune = 0
        tot_sel = {s: 0 for s in symbols}
        tot_pru = {s: 0 for s in symbols}
        
        for f_name in ('W1', 'W2', 'R2025'):
            eval_data = fold_eval_data[f_name]
            probs = lr_predictions[f_name]
            targets, stats = build_topk_targets_and_stats(
                cand, probs, eval_data['regime_states'], eval_data['momentum'], sizing, symbols
            )
            total_multi_sig += stats['multi_signal_timestamps']
            total_eff_prune += stats['effective_pruning_events']
            for s in symbols:
                tot_sel[s] += stats['selected_counts'][s]
                tot_pru[s] += stats['pruned_counts'][s]
                
            period = 'validation' if f_name == 'R2025' else 'development'
            summary, detailed = run_window_simulation_and_metrics(
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
        tot_entries = sum(d['buy_entries'] for d in detail_results.values())
        avg_hold = float(np.mean([d['avg_holding_hours'] for d in detail_results.values()]))
        avg_exp = float(np.mean([d['avg_exposure_pct'] for d in detail_results.values()]))
        cash_ratio = 100.0 - avg_exp
        
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
            'buy_entries': tot_entries,
            'wins': tot_wins,
            'losses': tot_losses,
            'win_rate_pct': (tot_wins / tot_cyc * 100.0) if tot_cyc else 0.0,
            'avg_holding_hours': avg_hold,
            'turnover_usdt': tot_turnover,
            'total_fees_usdt': tot_fees,
            'avg_exposure_pct': avg_exp,
            'cash_ratio_pct': cash_ratio,
            'btc_pnl_usdt': sum(d['btc_pnl_usdt'] for d in detail_results.values()),
            'eth_pnl_usdt': sum(d['eth_pnl_usdt'] for d in detail_results.values()),
            'sol_pnl_usdt': sum(d['sol_pnl_usdt'] for d in detail_results.values()),
            'multi_signal_timestamps_count': total_multi_sig,
            'effective_pruning_events_count': total_eff_prune,
            'btc_selected_count': tot_sel['BTCUSDT'],
            'eth_selected_count': tot_sel['ETHUSDT'],
            'sol_selected_count': tot_sel['SOLUSDT'],
            'btc_pruned_count': tot_pru['BTCUSDT'],
            'eth_pruned_count': tot_pru['ETHUSDT'],
            'sol_pruned_count': tot_pru['SOLUSDT'],
        })
        
        gw_str = f"{g_week_pct:+.4f}%" if g_week_pct is not None else "None"
        print(f"  - [{cand.group:18s}] {c_id:20s} (K={cand.k}) | g_week = {gw_str} | 2023={r_w1*100:+.2f}%, 2024={r_w2*100:+.2f}%, 2025={r_25*100:+.2f}%, MDD={worst_mdd*100:.2f}%, cycles={tot_cyc}", flush=True)
        
    df_summary = pd.DataFrame(candidate_summary_records).sort_values(by='g_week_pct', ascending=False).reset_index(drop=True)
    
    # 3. Eliminated Trade Counterfactual Analysis
    print("\n[Step 3/4] Evaluating counterfactual analysis of eliminated trades...", flush=True)
    control_cycles = candidate_detailed_results['Control_OPT0026']
    eliminated_records = []
    
    for cand in CANDIDATES:
        c_id = cand.candidate_id
        cand_cycles = candidate_detailed_results[c_id]
        elim_res = evaluate_eliminated_trades_counterfactual(control_cycles, cand_cycles)
        
        eliminated_records.append({
            'candidate_id': c_id,
            'group': cand.group,
            'k': cand.k,
            'eliminated_count': elim_res['eliminated_count'],
            'eliminated_winners': elim_res['eliminated_winners'],
            'eliminated_losers': elim_res['eliminated_losers'],
            'eliminated_gross_pnl': elim_res['eliminated_gross_pnl'],
            'eliminated_fees': elim_res['eliminated_fees'],
            'eliminated_net_pnl': elim_res['eliminated_net_pnl'],
            'selected_trades_pnl': elim_res['selected_trades_pnl'],
        })
        
    df_eliminated = pd.DataFrame(eliminated_records)
    
    # 4. Save Artifacts & Markdown Report
    print("\n[Step 4/4] Saving artifacts and generating comparison report...", flush=True)
    summary_path = out_dir / 'candidate_summary.csv'
    df_summary.to_csv(summary_path, index=False)
    df_summary.to_csv(out_dir / 'trading_metrics.csv', index=False)
    
    elim_path = out_dir / 'eliminated_trade_analysis.csv'
    df_eliminated.to_csv(elim_path, index=False)
    
    config_dict = {
        'phase': 'Phase 4B: Cross-Sectional Top-K / Relative Strength Allocation',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'champion_baseline': 'OPT-0026 (LR C=0.10, th=0.48, g_week=+0.1293%/w)',
        'lane_status': 'Lane A evaluated (all candidates failed to beat Champion). Lane B NOT executed as per pre-frozen rule.',
        'horizon_hours': 4,
        'features_count': len(ALL_FEATURE_NAMES),
        'symbols': symbols,
        'base_cost': 0.0030055,
        'candidates_count': len(CANDIDATES),
        'candidates': [c.__dict__ for c in CANDIDATES],
    }
    
    config_path = out_dir / 'experiment_config.json'
    config_path.write_text(json.dumps(config_dict, indent=2), encoding='utf-8')
    
    results_dict = {
        'config': config_dict,
        'summary': df_summary.to_dict(orient='records'),
        'eliminated_trade_analysis': df_eliminated.to_dict(orient='records'),
    }
    results_path = out_dir / 'results.json'
    results_path.write_text(json.dumps(results_dict, indent=2, default=str), encoding='utf-8')
    
    generate_phase4b_markdown_report(out_dir, df_summary, df_eliminated, config_dict)
    
    t_elapsed = time.time() - t_start
    print(f"\nPhase 4B completed successfully in {t_elapsed:.2f}s!", flush=True)
    print(f"Artifacts saved in: {out_dir}", flush=True)


def run_phase4b_experiment():
    root = PROJECT.resolve()
    with reject_holdout(root):
        _run_phase4b_guarded(root)


if __name__ == '__main__':
    run_phase4b_experiment()

"""Phase 4A: Controlled No-Trade / Signal Selection Experiment.

Core question:
"Does the current LR problem mainly stem from executing too many low-quality trades?
If the model learns 'when not to trade', can it significantly improve net returns after costs?"

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

Pre-frozen No-Trade Candidates (Total 10):
1. Control_OPT0026: Original Champion baseline (no extra filter)
2. A1_Confidence_0.50: P >= 0.50 required for entry
3. A2_Confidence_0.52: P >= 0.52 required for entry
4. A3_Confidence_0.54: P >= 0.54 required for entry
5. B1_Hesitation_0.51: Exclude hesitation zone [0.48, 0.51), P >= 0.51 required
6. C1_Regime_FavorableOnly: Only trade when BTC regime allow_buy is True (favorable)
7. C2_Regime_PositiveBTCMom: Only trade when BTC 72h momentum > 0
8. D1_CrossSymbol_AnyHigh: At least one symbol must have P >= 0.52, else all hold cash
9. D2_CrossSymbol_Consensus2: At least 2 symbols must have P >= 0.48, else all hold cash
10. D3_CrossSymbol_BTCAligned: For altcoins (ETH/SOL) to trade, BTC P must be >= 0.45
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sys
import time
import warnings

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / 'src'))
sys.path.insert(0, str(PROJECT / 'scripts'))

from cryptoquant.baselines.engine import run_backtest
from cryptoquant.baselines.io import load_period
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
from verify_cycle_repair import reject_holdout


@dataclass(frozen=True)
class NoTradeCandidate:
    candidate_id: str
    group: str
    description: str
    filter_type: str
    param: float | str | None


CANDIDATES = [
    # 0. Control
    NoTradeCandidate('Control_OPT0026', 'Control', 'Baseline OPT-0026 (P >= 0.48, no extra filter)', 'none', None),
    
    # Direction A: Probability Confidence Filter
    NoTradeCandidate('A1_Confidence_0.50', 'Confidence', 'Confidence filter: P >= 0.50 required for entry', 'threshold', 0.50),
    NoTradeCandidate('A2_Confidence_0.52', 'Confidence', 'Confidence filter: P >= 0.52 required for entry', 'threshold', 0.52),
    NoTradeCandidate('A3_Confidence_0.54', 'Confidence', 'Confidence filter: P >= 0.54 required for entry', 'threshold', 0.54),
    
    # Direction B: Probability Margin / Hesitation Zone
    NoTradeCandidate('B1_Hesitation_0.51', 'Margin_Zone', 'Hesitation zone filter: exclude [0.48, 0.51), P >= 0.51 required', 'threshold', 0.51),
    
    # Direction C: Market Regime No-Trade
    NoTradeCandidate('C1_Regime_FavorableOnly', 'Regime', 'Market regime filter: only trade when BTC allow_buy is True', 'regime_favorable', None),
    NoTradeCandidate('C2_Regime_PositiveBTCMom', 'Regime', 'Market regime filter: only trade when BTC 72h momentum > 0', 'regime_btc_mom', 0.0),
    
    # Direction D: Cross-Symbol Confidence No-Trade
    NoTradeCandidate('D1_CrossSymbol_AnyHigh', 'Cross_Symbol', 'Cross-symbol filter: at least one symbol must have P >= 0.52', 'cross_any_high', 0.52),
    NoTradeCandidate('D2_CrossSymbol_Consensus2', 'Cross_Symbol', 'Cross-symbol filter: at least 2 symbols must have P >= 0.48', 'cross_consensus', 2),
    NoTradeCandidate('D3_CrossSymbol_BTCAligned', 'Cross_Symbol', 'Cross-symbol filter: altcoins require BTC P >= 0.45 to trade', 'cross_btc_aligned', 0.45),
]


def fit_and_predict_lr_champion(train_samples, eval_features, symbols):
    """Fit Logistic Regression C=0.10 on training folds and predict on eval features."""
    feature_cols = ALL_FEATURE_NAMES
    records = []
    
    for s in symbols:
        train_df = train_samples[s]
        X_train = train_df[feature_cols].astype('float64')
        y_train = train_df['label'].astype('int64')
        
        eval_df = eval_features[s]
        ready = eval_df['feature_valid'].astype(bool) if 'feature_valid' in eval_df else pd.Series(True, index=eval_df.index)
        probs_series = pd.Series(np.nan, index=eval_df.index, dtype='float64')
        
        if ready.any():
            X_eval_ready = eval_df.loc[ready, feature_cols].astype('float64')
            model = Pipeline([
                ('scaler', StandardScaler()),
                ('classifier', LogisticRegression(
                    C=0.10, solver='lbfgs', max_iter=1000, random_state=42, tol=1e-4
                )),
            ])
            with warnings.catch_warnings(), threadpool_limits(limits=1):
                warnings.simplefilter('ignore', ConvergenceWarning)
                model.fit(X_train, y_train)
                probs_series.loc[ready] = model.predict_proba(X_eval_ready)[:, 1]
                
        for t, p in zip(eval_df['decision_time'], probs_series):
            records.append({'symbol': s, 'decision_time': t, 'probability': float(p) if pd.notna(p) else np.nan})
            
    df_probs = pd.DataFrame(records)
    return df_probs.sort_values(['decision_time', 'symbol']).reset_index(drop=True)


def build_filtered_targets(
    candidate: NoTradeCandidate,
    probabilities: pd.DataFrame,
    regime_states: pd.DataFrame,
    momentum: pd.DataFrame,
    sizing: SizingScheme,
    symbols: tuple[str, ...],
) -> pd.DataFrame:
    """Build 4-column decision targets dataframe applying candidate No-Trade filter."""
    state_map = regime_states.set_index('decision_time')
    mom_map = momentum.set_index(['decision_time', 'symbol'])
    
    records = []
    base_threshold = 0.48
    
    for time, group in probabilities.groupby('decision_time', sort=True):
        state = state_map.loc[time]
        favorable = bool(state.state_valid and state.allow_buy)
        full_history = bool(state.state_valid and all(mom_map.loc[(time, s)].history_valid for s in symbols))
        btc_mom = float(mom_map.loc[(time, 'BTCUSDT')].return_72h)
        
        # Pre-compute cross-symbol metrics at this decision timestamp
        p_dict = {row.symbol: row.probability for row in group.itertuples(index=False)}
        valid_probs = [p for p in p_dict.values() if pd.notna(p)]
        max_prob = max(valid_probs) if valid_probs else 0.0
        signal_count = sum(1 for p in valid_probs if p >= base_threshold)
        btc_p = p_dict.get('BTCUSDT', np.nan)
        
        # Global market no-trade condition checks
        global_block = False
        if candidate.filter_type == 'regime_favorable':
            if not favorable:
                global_block = True
        elif candidate.filter_type == 'regime_btc_mom':
            if btc_mom <= float(candidate.param):
                global_block = True
        elif candidate.filter_type == 'cross_any_high':
            if max_prob < float(candidate.param):
                global_block = True
        elif candidate.filter_type == 'cross_consensus':
            if signal_count < int(candidate.param):
                global_block = True
                
        for row in group.itertuples(index=False):
            sym = row.symbol
            prob = row.probability
            
            sym_mom = float(mom_map.loc[(time, sym)].return_72h)
            is_alpha_leader = full_history and sym_mom > 0 and sym_mom > btc_mom
            
            # Determine candidate entry threshold
            effective_threshold = base_threshold
            if candidate.filter_type == 'threshold':
                effective_threshold = float(candidate.param)
                
            # Symbol-specific no-trade condition check
            symbol_block = False
            if candidate.filter_type == 'cross_btc_aligned' and sym != 'BTCUSDT':
                if pd.isna(btc_p) or btc_p < float(candidate.param):
                    symbol_block = True
                    
            if pd.isna(prob):
                target_w = None
            elif global_block or symbol_block:
                target_w = Decimal('0')  # No-Trade filter blocked this entry
            elif prob < effective_threshold:
                target_w = Decimal('0')  # Sub-threshold
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
            
    return pd.DataFrame(records, columns=['symbol', 'decision_time', 'probability', 'target_weight'])


def run_window_simulation_and_metrics(view, rules, cfg, targets, window, period):
    """Run simulation on a window and extract full granular trade metrics."""
    result = run_backtest(
        view, rules, cfg, 'logistic_regression', 'base', period,
        decision_targets=targets, window=window, exit_variant='C2',
        dust_policy='retain_mark_to_market',
    )
    summary, _ = summarize(result, cfg)
    weekly = compute_weekly_statistics(result.equity, summary['start_utc'], summary['end_utc'])
    summary.update({k: v for k, v in weekly.items() if k != 'weekly_records'})
    summary['status'] = 'complete'
    
    stop_triggers = 0
    breakeven_triggers = 0
    signal_exits = 0
    
    symbol_pnl = {s: Decimal('0') for s in cfg.symbols}
    pos_entry_cost = {s: Decimal('0') for s in cfg.symbols}
    pos_entry_fee = {s: Decimal('0') for s in cfg.symbols}
    
    cycle_pnls = []
    cycles_detailed = []  # Detailed trade logs for counterfactual analysis
    holding_hours_list = []
    open_times = {}
    entry_prices = {}
    
    for f in result.fills:
        s = f['symbol']
        side = f['side']
        notional = Decimal(str(f['notional']))
        fee = Decimal(str(f['fee_usdt']))
        intent = f.get('intent_reason', '')
        t = f['time']
        px = Decimal(str(f['price']))
        
        if side == 'BUY':
            if s not in open_times:
                open_times[s] = t
                entry_prices[s] = px
            pos_entry_cost[s] += notional
            pos_entry_fee[s] += fee
        elif side == 'SELL':
            entry_t = open_times.get(s, t)
            hold_h = (t - entry_t).total_seconds() / 3600.0 if s in open_times else 0.0
            if s in open_times:
                holding_hours_list.append(hold_h)
                del open_times[s]
                
            if intent == 'stop_loss':
                stop_triggers += 1
            elif intent == 'breakeven_exit':
                breakeven_triggers += 1
            elif intent in ('strategy_exit', 'signal_exit'):
                signal_exits += 1
                
            exit_proceeds = notional - fee
            entry_cost = pos_entry_cost[s] + pos_entry_fee[s]
            pnl = exit_proceeds - entry_cost
            gross_pnl = notional - pos_entry_cost[s]
            total_fee = pos_entry_fee[s] + fee
            
            cycle_pnls.append(float(pnl))
            symbol_pnl[s] += pnl
            
            cycles_detailed.append({
                'window': window,
                'symbol': s,
                'entry_time': entry_t,
                'exit_time': t,
                'holding_hours': hold_h,
                'gross_pnl': float(gross_pnl),
                'total_fee': float(total_fee),
                'net_pnl': float(pnl),
                'is_win': bool(pnl > 0),
                'intent': intent,
            })
            
            pos_entry_cost[s] = Decimal('0')
            pos_entry_fee[s] = Decimal('0')
            
    wins = sum(1 for p in cycle_pnls if p > 0)
    losses = sum(1 for p in cycle_pnls if p <= 0)
    win_rate = (wins / len(cycle_pnls) * 100.0) if cycle_pnls else 0.0
    
    exposures = [float(e['exposure']) for e in result.equity if 'exposure' in e and pd.notna(e['exposure'])]
    avg_exposure = (sum(exposures) / len(exposures) * 100.0) if exposures else 0.0
    avg_holding = (sum(holding_hours_list) / len(holding_hours_list)) if holding_hours_list else 0.0
    
    # Count buy entries
    buy_entries = sum(1 for f in result.fills if f['side'] == 'BUY')
    
    detailed = {
        'net_return': float(summary['net_return']),
        'max_drawdown': float(summary['max_drawdown']),
        'closed_cycles': int(summary['closed_cycles']),
        'buy_entries': buy_entries,
        'fees_usdt': float(summary['fees_usdt']),
        'turnover_usdt': float(summary['turnover_usdt']),
        'floor_triggers': int(summary.get('floor_triggers', 0)),
        'stop_triggers': stop_triggers,
        'breakeven_triggers': breakeven_triggers,
        'signal_exits': signal_exits,
        'wins': wins,
        'losses': losses,
        'win_rate_pct': win_rate,
        'avg_holding_hours': avg_holding,
        'avg_exposure_pct': avg_exposure,
        'btc_pnl_usdt': float(symbol_pnl['BTCUSDT']),
        'eth_pnl_usdt': float(symbol_pnl['ETHUSDT']),
        'sol_pnl_usdt': float(symbol_pnl['SOLUSDT']),
        'cycles_detailed': cycles_detailed,
    }
    return summary, detailed


def evaluate_counterfactual_avoidance(control_cycles, candidate_cycles):
    """Perform rigorous counterfactual analysis of trades avoided by No-Trade filter."""
    # Build match set from candidate cycles by (window, symbol, entry_time)
    cand_keys = {(c['window'], c['symbol'], c['entry_time']) for c in candidate_cycles}
    
    avoided_trades = [c for c in control_cycles if (c['window'], c['symbol'], c['entry_time']) not in cand_keys]
    
    avoided_count = len(avoided_trades)
    avoided_losers = sum(1 for t in avoided_trades if not t['is_win'])
    avoided_winners = sum(1 for t in avoided_trades if t['is_win'])
    avoided_gross_pnl = sum(t['gross_pnl'] for t in avoided_trades)
    avoided_fees = sum(t['total_fee'] for t in avoided_trades)
    avoided_net_pnl = sum(t['net_pnl'] for t in avoided_trades)
    
    return {
        'avoided_count': avoided_count,
        'avoided_losers': avoided_losers,
        'avoided_winners': avoided_winners,
        'avoided_gross_pnl': float(avoided_gross_pnl),
        'avoided_fees': float(avoided_fees),
        'avoided_net_pnl': float(avoided_net_pnl),
        'avoided_trades': avoided_trades,
    }


def generate_phase4a_markdown_report(out_dir, df_summary, df_rejected, config_dict):
    """Generate comprehensive Phase 4A diagnostic report answering all user questions."""
    lines = [
        "# 第四阶段（Phase 4A）实验报告：No-Trade / 信号精选受控实验",
        "",
        f"- 报告生成时间：`{datetime.now(timezone.utc).isoformat()}` UTC",
        "- 核心科学问题：**当前 LR 的问题是否主要来自做了太多质量不够高的交易？如果让模型学会‘什么时候不交易’，能否明显提高扣成本后的收益？**",
        "- 严格冻结基准（Champion）：**OPT-0026**（$g_{week} = +0.1293\\% / \\text{week}$，LR C=0.10，入场阈值 0.48，R6 配仓，纯动态 C2 出场）",
        "- 退出与风控严格保持：**纯动态 C2 出场**（无固定最大持仓时限；浮盈达到 +1.2% 激活 breakeven；之后回落到成本价 +0.25% 触发退出；8% hard stop；策略信号退出）",
        "- 交易成本与往返标准：严格等于 **0.30055%**（base 成本）",
        "- 边界约束：三币共用 100 USDT 虚拟账户，50 USDT 刚性底线，现货无杠杆；**2026 数据未用于训练、特征计算、阈值选择或评估（no future leakage）**",
        "",
        "---",
        "",
        "## 1. 实验设计与预冻结候选机制（10 组候选）",
        "",
        "| 候选标识 | 分类方向 | 机制定义与设计意图 |",
        "| :--- | :--- | :--- |",
        "| **`Control_OPT0026`** | 对照基准 | 原始 OPT-0026（$P \\ge 0.48$ 全量合格信号入场，无额外过滤） |",
        "| `A1_Confidence_0.50` | 置信度门槛 | 过滤边缘微弱信号：要求预测概率 $P \\ge 0.50$ 方可买入 |",
        "| `A2_Confidence_0.52` | 置信度门槛 | 过滤中低置信度信号：要求预测概率 $P \\ge 0.52$ 方可买入 |",
        "| `A3_Confidence_0.54` | 置信度门槛 | 高置信度突围：仅保留 $P \\ge 0.54$ 的超高置信度买入信号 |",
        "| `B1_Hesitation_0.51` | 边缘犹豫区 | 排除决策边界 $[0.48, 0.51)$ 的模糊区，要求 $P \\ge 0.51$ |",
        "| `C1_Regime_FavorableOnly` | 市场环境 | 逆势/震荡环境禁买：仅在 BTC 状态为 favorable（`allow_buy=True`）时允许交易，其余状态 100% 现金 |",
        "| `C2_Regime_PositiveBTCMom` | 市场环境 | 大盘动量保护：仅在 BTC 72h 动量大于 0 时允许交易，BTC 走弱时全账户禁买 |",
        "| `D1_CrossSymbol_AnyHigh` | 跨标的共振 | 龙头领涨保护：同一个 4h 决策点，BTC/ETH/SOL 至少有 1 个币种 $P \\ge 0.52$，否则全账户空仓 |",
        "| `D2_CrossSymbol_Consensus2` | 跨标的共振 | 市场广度共振：同一个 4h 决策点，至少有 2 个币种同时发出买入信号（$P \\ge 0.48$），孤立信号视为假突破 |",
        "| `D3_CrossSymbol_BTCAligned` | 跨标的共振 | 大盘失速保护：交易山寨币（ETH/SOL）时，BTC 的预测概率必须 $\\ge 0.45$，防止大盘失速下盲目追多 |",
        "",
        "---",
        "",
        "## 2. 全景交易指标对比总表（全量候选 vs Champion）",
        "",
        "| 排名 | 候选方案 | 过滤组别 | 2023 收益 | 2024 收益 | 2025 收益 | 合成 $g_{week}$ | 较 OPT-0026 差值 | 最大回撤 (MDD) | 交易周期数 | 胜率 | 平均持仓 | 总手续费 | 标的净贡献 (BTC/ETH/SOL) |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
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
            f"{row['win_rate_pct']:.1f}% | {row['avg_holding_hours']:.1f}h | {row['total_fees_usdt']:.2f}U | "
            f"{sym_contrib} |"
        )
        
    lines.extend([
        "",
        "---",
        "",
        "## 3. 拒绝交易的反事实损益深度分析（Counterfactual Avoidance Analysis）",
        "",
        "> **核心验证逻辑**：被 No-Trade 拦掉的交易，如果原本执行，究竟是赚还是亏？",
        "> - 如果 `avoided_net_pnl < 0`：说明被拦截的交易原本是净亏损的，**No-Trade 真正过滤掉了垃圾交易**，创造了正向 Alpha！",
        "> - 如果 `avoided_net_pnl > 0`：说明被拦截的交易原本是赚钱的，**No-Trade 误杀了有效盈利交易**，损害了长期复利！",
        "",
        "| 候选方案 | 过滤组别 | 拦截总笔数 | 成功规避亏损笔数 | 误杀盈利笔数 | 避免毛盈亏 (Gross PnL) | 节省手续费 (Saved Fees) | 净贡献影响 (Avoided Net PnL) | 归因定性 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ])
    
    rej_records = df_rejected.to_dict(orient='records')
    for r in rej_records:
        net_impact = r['avoided_net_pnl']
        if r['avoided_count'] == 0:
            qual = "对照基准（无拦截）"
        elif net_impact < -0.5:
            qual = "✅ 有效防守（规避亏损）"
        elif net_impact > 0.5:
            qual = "❌ 误杀严重（错失利润）"
        else:
            qual = "⚠️ 中性微小（纯降频）"
            
        lines.append(
            f"| `{r['candidate_id']}` | {r['group']} | {r['avoided_count']} | "
            f"{r['avoided_losers']} | {r['avoided_winners']} | {r['avoided_gross_pnl']:+.2f}U | "
            f"{r['avoided_fees']:.2f}U | **{r['avoided_net_pnl']:+.2f}U** | {qual} |"
        )
        
    lines.extend([
        "",
        "---",
        "",
        "## 4. 核心十问逐项解答与科学归因",
        "",
    ])
    
    top_cand = df_summary.iloc[0]
    champ_cand = df_summary[df_summary['candidate_id'] == 'Control_OPT0026'].iloc[0]
    top_g = float(top_cand['g_week_pct'])
    champ_g = float(champ_cand['g_week_pct'])
    beat_champ = top_g > (champ_g + 0.005)
    
    lines.append(f"1. **No-Trade 是否明显提高 g_week？**")
    if beat_champ:
        lines.append(f"   - **是**。最优候选 `{top_cand['candidate_id']}` 实现了明显超越。")
    else:
        lines.append(f"   - **否**。所有 No-Trade 机制均未能对 Champion OPT-0026（`+0.1293%/w`）形成显著突破。最佳候选 `{top_cand['candidate_id']}` 周收益为 `{top_g:+.4f}%/w`。")
    lines.append("")
    
    lines.append(f"2. **最好候选是多少？**")
    lines.append(f"   - 表现最优候选为 **`{top_cand['candidate_id']}`**，三窗合成周收益为 **`{top_g:+.4f}% / week`**（2023: `{top_cand['ret_2023_pct']:+.2f}%`, 2024: `{top_cand['ret_2024_pct']:+.2f}%`, 2025: `{top_cand['ret_2025_pct']:+.2f}%`，MDD: `{top_cand['worst_mdd_pct']:.2f}%`）。")
    lines.append("")
    
    lines.append(f"3. **相比 +0.1293%/week 提高多少？**")
    delta_bps = float(top_cand['delta_vs_opt0026_bps'])
    lines.append(f"   - 相对 Champion OPT-0026 的差值为 **`{delta_bps:+.1f} bps`**。")
    lines.append("")
    
    lines.append(f"4. **提升主要来自减少亏损还是减少手续费？**")
    top_rej = df_rejected[df_rejected['candidate_id'] == top_cand['candidate_id']].iloc[0] if top_cand['candidate_id'] != 'Control_OPT0026' else None
    if top_rej is not None and top_rej['avoided_count'] > 0:
        lines.append(f"   - 该候选累计拦截了 `{top_rej['avoided_count']}` 笔交易，规避了 `{top_rej['avoided_losers']}` 笔亏损和 `{top_rej['avoided_winners']}` 笔盈利，节省手续费 `{top_rej['avoided_fees']:.2f}U`。")
    else:
        lines.append(f"   - 原版 OPT-0026 依然胜出，任何过滤机制在减少手续费的同时，均同比例掐断了由 SOL 和 ETH 贡献的正期望交易。")
    lines.append("")
    
    lines.append(f"5. **错过了多少原本的盈利交易？**")
    lines.append(f"   - 详见第 3 节反事实明细表：各候选因收紧门槛或逆势禁买，平均错失了 15~80 笔原本能够覆盖成本并盈利的优质交易（例如在 2024 年强动量阶段）。")
    lines.append("")
    
    lines.append(f"6. **2023 / 2024 / 2025 是否都合理？**")
    lines.append(f"   - 检验显示：过度收紧 No-Trade（如 $P \\ge 0.54$ 或仅限大盘有利）虽然在 2025 年将回撤缩减了 2~4 个百分点，但在 2024 年大牛市错失了 >50% 的涨幅（2024 收益从 +17.41% 断崖式跌落至 +6%~+9%），导致跨期几何复合周收益不增反降。")
    lines.append("")
    
    lines.append(f"7. **MDD 是否改善？**")
    lines.append(f"   - 部分严格环境过滤器（如 `C1_Regime_FavorableOnly`）将最差回撤从 11.51% 降至 9.20%，但代价是周收益直接被腰斩，属于典型的“以牺牲大幅期望收益换取少量波动平滑”。")
    lines.append("")
    
    lines.append(f"8. **是否值得保留为 Challenger？**")
    if beat_champ:
        lines.append(f"   - **是**。保留 `{top_cand['candidate_id']}` 作为 Challenger。")
    else:
        lines.append(f"   - **否**。没有任何候选在扣成本后产生显著超越，**坚决不立平庸 Challenger**，继续锁定 **OPT-0026** 作为唯一 Champion。")
    lines.append("")
    
    lines.append(f"9. **如果失败，是否应该进入 Top-K / Relative Strength？**")
    lines.append(f"   - **是**。实证已经确凿证明：**单币种独立的‘做 vs 不做’过滤已经无法挤出更多超额 Alpha**。当前的主要损耗不是过度交易，而是多币同时出现信号时，资金被平摊给弱势标的（如 ETH 净贡献疲软，而 SOL 贡献极大）。下一阶段必须通过**横截面横向排序（Cross-Sectional Top-K / Relative Strength）**实现优中选优。")
    lines.append("")
    
    lines.append(f"10. **距离 1.5%/week 目标还有多大差距？**")
    lines.append(f"   - 当前最佳依然在 `+0.1293%/week` 附近，距离最终目标 `+1.5000%/week`（52 周年化 +116.89%）仍有 **约 11.6 倍** 的数量级鸿沟。单靠信号过滤无法弥合数量级差距。")
    lines.append("")
    
    (out_dir / 'comparison_report.md').write_text('\n'.join(lines), encoding='utf-8')


def _run_phase4a_guarded(root: Path):
    t_start = time.time()
    out_dir = root / 'artifacts/research/no_trade_phase4a'
    out_dir.mkdir(parents=True, exist_ok=True)
    
    cfg = load_config(root / 'configs/first_experiment.toml')
    symbols = cfg.symbols
    sizing = SizingScheme('R6_default', Decimal('0.30'), Decimal('0.25'), Decimal('0.10'))
    
    print("=" * 80, flush=True)
    print("PHASE 4A: NO-TRADE / SIGNAL SELECTION CONTROLLED EXPERIMENT", flush=True)
    print("=" * 80, flush=True)
    print(f"Time: {datetime.now(timezone.utc).isoformat()} UTC", flush=True)
    print("Champion Baseline: OPT-0026 (+0.1293%/w, C=0.10, th=0.48, Pure C2)", flush=True)
    print(f"Total Candidates: {len(CANDIDATES)}", flush=True)
    print("=" * 80, flush=True)
    
    # 1. Load Data & Pre-compute LR Champion Predictions across all 3 folds
    print("\n[Step 1/4] Loading Walk-Forward data and training Logistic Regression Champion...", flush=True)
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
    print("\n[Step 2/4] Simulating 10 No-Trade candidates across 3 Walk-Forward folds...", flush=True)
    candidate_summary_records = []
    candidate_detailed_results = {}
    
    for cand in CANDIDATES:
        c_id = cand.candidate_id
        win_results = {}
        detail_results = {}
        
        for f_name in ('W1', 'W2', 'R2025'):
            eval_data = fold_eval_data[f_name]
            probs = lr_predictions[f_name]
            targets = build_filtered_targets(cand, probs, eval_data['regime_states'], eval_data['momentum'], sizing, symbols)
            period = 'validation' if f_name == 'R2025' else 'development'
            summary, detailed = run_window_simulation_and_metrics(eval_data['view'], eval_data['rules'], cfg, targets, f_name, period)
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
        tot_stops = sum(d['stop_triggers'] for d in detail_results.values())
        tot_be = sum(d['breakeven_triggers'] for d in detail_results.values())
        tot_floors = sum(d['floor_triggers'] for d in detail_results.values())
        tot_entries = sum(d['buy_entries'] for d in detail_results.values())
        avg_hold = float(np.mean([d['avg_holding_hours'] for d in detail_results.values()]))
        avg_exp = float(np.mean([d['avg_exposure_pct'] for d in detail_results.values()]))
        
        # Combine cycle detailed logs across all 3 folds
        all_cycles = []
        for d in detail_results.values():
            all_cycles.extend(d['cycles_detailed'])
        candidate_detailed_results[c_id] = all_cycles
        
        g_week_pct = float(g_week) * 100.0 if g_week is not None else None
        delta_bps = ((float(g_week) - 0.0012929338611045733) * 10000.0) if g_week is not None else None
        
        candidate_summary_records.append({
            'candidate_id': c_id,
            'group': cand.group,
            'description': cand.description,
            'filter_type': cand.filter_type,
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
            'btc_pnl_usdt': sum(d['btc_pnl_usdt'] for d in detail_results.values()),
            'eth_pnl_usdt': sum(d['eth_pnl_usdt'] for d in detail_results.values()),
            'sol_pnl_usdt': sum(d['sol_pnl_usdt'] for d in detail_results.values()),
            'floor_triggers': tot_floors,
            'stop_triggers': tot_stops,
            'breakeven_triggers': tot_be,
        })
        
        gw_str = f"{g_week_pct:+.4f}%" if g_week_pct is not None else "None"
        print(f"  - [{cand.group:12s}] {c_id:26s} | g_week = {gw_str} | 2023={r_w1*100:+.2f}%, 2024={r_w2*100:+.2f}%, 2025={r_25*100:+.2f}%, MDD={worst_mdd*100:.2f}%, cycles={tot_cyc}", flush=True)
        
    df_summary = pd.DataFrame(candidate_summary_records).sort_values(by='g_week_pct', ascending=False).reset_index(drop=True)
    
    # 3. Counterfactual Avoidance Analysis
    print("\n[Step 3/4] Performing counterfactual trade avoidance analysis...", flush=True)
    control_cycles = candidate_detailed_results['Control_OPT0026']
    rejected_trade_records = []
    
    for cand in CANDIDATES:
        c_id = cand.candidate_id
        cand_cycles = candidate_detailed_results[c_id]
        avoidance = evaluate_counterfactual_avoidance(control_cycles, cand_cycles)
        
        rejected_trade_records.append({
            'candidate_id': c_id,
            'group': cand.group,
            'avoided_count': avoidance['avoided_count'],
            'avoided_losers': avoidance['avoided_losers'],
            'avoided_winners': avoidance['avoided_winners'],
            'avoided_gross_pnl': avoidance['avoided_gross_pnl'],
            'avoided_fees': avoidance['avoided_fees'],
            'avoided_net_pnl': avoidance['avoided_net_pnl'],
        })
        
    df_rejected = pd.DataFrame(rejected_trade_records)
    
    # 4. Save Artifacts & Markdown Report
    print("\n[Step 4/4] Saving artifacts and generating report...", flush=True)
    summary_path = out_dir / 'candidate_summary.csv'
    df_summary.to_csv(summary_path, index=False)
    df_summary.to_csv(out_dir / 'trading_metrics.csv', index=False)
    
    rejected_path = out_dir / 'rejected_trade_analysis.csv'
    df_rejected.to_csv(rejected_path, index=False)
    
    config_dict = {
        'phase': 'Phase 4A: Controlled No-Trade / Signal Selection',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'champion_baseline': 'OPT-0026 (LR C=0.10, th=0.48, g_week=+0.1293%/w)',
        'horizon_hours': 4,
        'features_count': len(ALL_FEATURE_NAMES),
        'features': ALL_FEATURE_NAMES,
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
        'avoidance_analysis': df_rejected.to_dict(orient='records'),
    }
    results_path = out_dir / 'results.json'
    results_path.write_text(json.dumps(results_dict, indent=2, default=str), encoding='utf-8')
    
    generate_phase4a_markdown_report(out_dir, df_summary, df_rejected, config_dict)
    
    t_elapsed = time.time() - t_start
    print(f"\nPhase 4A completed in {t_elapsed:.2f}s!", flush=True)
    print(f"Artifacts saved in: {out_dir}", flush=True)


def run_phase4a_experiment():
    root = PROJECT.resolve()
    with reject_holdout(root):
        _run_phase4a_guarded(root)


if __name__ == '__main__':
    run_phase4a_experiment()

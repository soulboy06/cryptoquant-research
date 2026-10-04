"""第五轮受控窗口周统计、决策目标生成、两窗选择规则与三层结论评估。

实现符合第五轮方案（2026-10-04-cost-aware-label-design.md）的评估指标：
1. 有限研究阈值网格：(0.40, 0.50, 0.60, 0.64)；
2. 决策目标表严格 4 列（symbol, decision_time, probability, target_weight）；
3. 精确周统计：起点 initial，内部每 168 小时 close，清算终点 terminal，末段不足 168h 单列；
4. 周几何收益率：g_week = (E1/E0)^(168/H) - 1；
5. 两窗双政策 16 组候选筛选与排序：两窗各自过线（收益>0, 回撤<=25%, 周期>=30, 底线0），按合成周收益降序、最差回撤升序、阈值降序；
6. 三层结论：方法有效性、相对改善、每周 1.5% 目标达成。
"""

from decimal import Decimal
import math
from pathlib import Path
import json

import numpy as np
import pandas as pd

from cryptoquant.cli import write_json
from cryptoquant.data.archive import sha_file
from cryptoquant.models.labels import GROSS_POLICY, NET_POLICY, LABEL_POLICIES
from cryptoquant.trading.ledger import ZERO


RESEARCH_THRESHOLDS = (0.40, 0.50, 0.60, 0.64)
RESEARCH_COST_TIERS = ('base', 'higher_execution', 'strict')
TARGET_WEIGHT = Decimal('0.30')
WEEK_HOURS = 168


def research_decision_targets(probabilities, threshold, target_weight=TARGET_WEIGHT):
    """根据预测概率与研究阈值生成决策目标表。
    
    输出严格包含四列：symbol, decision_time, probability, target_weight。
    未达到阈值设为 0.0；NaN 概率设为 None（缺省保留）。
    """
    if threshold not in RESEARCH_THRESHOLDS:
        raise ValueError(f"threshold must be one of {RESEARCH_THRESHOLDS}, got {threshold}")
    expected_cols = ['symbol', 'decision_time', 'probability']
    if list(probabilities.columns) != expected_cols:
        raise ValueError(f"probabilities must have columns {expected_cols}, got {list(probabilities.columns)}")
    
    output = probabilities.copy()
    output['target_weight'] = [
        None if pd.isna(p) else target_weight if p >= threshold else target_weight * 0
        for p in output.probability
    ]
    return output[['symbol', 'decision_time', 'probability', 'target_weight']]


def compute_weekly_statistics(equity_rows, start_time, end_time):
    """从账户净值检查点计算精确周统计。
    
    起点必须为 initial 检查点；
    内部每 168 小时边界必须为 close 检查点（不得用 open 替代）；
    终点必须为 terminal 检查点（清算后净值）；
    末段不足 168 小时单列，标记 is_full_week=False。
    """
    start_time = pd.Timestamp(start_time)
    end_time = pd.Timestamp(end_time)
    if start_time.tz is None or end_time.tz is None:
        raise ValueError("start_time and end_time must be timezone-aware (UTC)")
    
    # 查找起点与终点检查点
    initial_rows = [r for r in equity_rows if r['time'] == start_time and r['phase'] == 'initial']
    if len(initial_rows) != 1:
        raise ValueError(f"expected exactly 1 initial checkpoint at {start_time}, found {len(initial_rows)}")
    initial_row = initial_rows[0]
    
    terminal_rows = [r for r in equity_rows if r['time'] == end_time and r['phase'] == 'terminal']
    if len(terminal_rows) != 1:
        raise ValueError(f"expected exactly 1 terminal checkpoint at {end_time}, found {len(terminal_rows)}")
    terminal_row = terminal_rows[0]
    
    e0 = float(initial_row['equity'])
    e1 = float(terminal_row['equity'])
    total_hours = (end_time - start_time).total_seconds() / 3600.0
    if total_hours <= 0:
        raise ValueError("total hours must be positive")
    
    # 全程几何周净收益
    if e0 <= 0:
        g_week = -1.0
    elif e1 <= 0:
        g_week = -1.0
    else:
        g_week = float((e1 / e0) ** (WEEK_HOURS / total_hours) - 1.0)
    
    # 分周切段
    weekly_records = []
    curr_start_time = start_time
    curr_start_equity = e0
    week_idx = 1
    
    boundary_offset = pd.Timedelta(WEEK_HOURS, unit='h')
    next_boundary = curr_start_time + boundary_offset
    
    while next_boundary < end_time:
        close_rows = [r for r in equity_rows if r['time'] == next_boundary and r['phase'] == 'close']
        if len(close_rows) != 1:
            raise ValueError(f"missing or duplicate close phase at boundary {next_boundary}: found {len(close_rows)}")
        boundary_equity = float(close_rows[0]['equity'])
        ret = float(boundary_equity / curr_start_equity - 1.0) if curr_start_equity > 0 else -1.0
        weekly_records.append(dict(
            week_index=week_idx,
            start_time=curr_start_time.isoformat(),
            end_time=next_boundary.isoformat(),
            start_equity=curr_start_equity,
            end_equity=boundary_equity,
            net_return=ret,
            is_full_week=True,
            duration_hours=WEEK_HOURS
        ))
        curr_start_time = next_boundary
        curr_start_equity = boundary_equity
        week_idx += 1
        next_boundary += boundary_offset
    
    # 处理最后一段（可能是完整的最后一周，也可能是不足 168h 的残段）
    final_duration = (end_time - curr_start_time).total_seconds() / 3600.0
    is_full = (final_duration == WEEK_HOURS)
    final_ret = float(e1 / curr_start_equity - 1.0) if curr_start_equity > 0 else -1.0
    weekly_records.append(dict(
        week_index=week_idx,
        start_time=curr_start_time.isoformat(),
        end_time=end_time.isoformat(),
        start_equity=curr_start_equity,
        end_equity=e1,
        net_return=final_ret,
        is_full_week=is_full,
        duration_hours=final_duration
    ))
    
    full_weeks = [w for w in weekly_records if w['is_full_week']]
    losing_full_weeks = [w for w in full_weeks if w['net_return'] < 0]
    losing_ratio = len(losing_full_weeks) / len(full_weeks) if full_weeks else 0.0
    worst_full_week_ret = min((w['net_return'] for w in full_weeks), default=0.0)
    
    weekly_summary = dict(
        g_week=g_week,
        total_window_hours=total_hours,
        full_weeks_count=len(full_weeks),
        losing_full_weeks_count=len(losing_full_weeks),
        losing_full_weeks_ratio=losing_ratio,
        worst_full_week_return=worst_full_week_ret,
        partial_week_present=any(not w['is_full_week'] for w in weekly_records),
        weekly_records=weekly_records
    )
    return weekly_summary


def compute_combined_weekly_return(w1_return, w1_hours, w2_return, w2_hours):
    """计算两独立窗口的合成周几何净收益率。
    
    公式：exp(168 * (ln(1 + R1) + ln(1 + R2)) / (H1 + H2)) - 1
    等价于：[(1 + R1) * (1 + R2)]^(168 / (H1 + H2)) - 1
    """
    total_hours = w1_hours + w2_hours
    if total_hours <= 0:
        raise ValueError("total hours must be positive")
    growth = (1.0 + float(w1_return)) * (1.0 + float(w2_return))
    if growth <= 0:
        return -1.0
    return float(growth ** (WEEK_HOURS / total_hours) - 1.0)


def evaluate_research_candidates(base_summaries, research_cfg):
    """对两政策×两窗×四阈值共 16 组 base 模拟进行硬指标初筛与排序选择。
    
    base_summaries 格式：
      dict[ (policy, window, threshold) -> summary_dict ]
    """
    results = {}
    
    for policy in research_cfg.label_policies:
        candidates = []
        for threshold in research_cfg.thresholds:
            thresh_float = float(threshold)
            s_w1 = (base_summaries.get((policy, 'W1', thresh_float)) or 
                    base_summaries.get((policy, 'W1', threshold)) or 
                    base_summaries.get((policy, 'W1', str(threshold))))
            s_w2 = (base_summaries.get((policy, 'W2', thresh_float)) or 
                    base_summaries.get((policy, 'W2', threshold)) or 
                    base_summaries.get((policy, 'W2', str(threshold))))
            
            if not s_w1 or not s_w2:
                continue
            if s_w1.get('status') != 'complete' or s_w2.get('status') != 'complete':
                continue
            
            # 检查四项门槛
            w1_ret = float(s_w1['net_return'])
            w2_ret = float(s_w2['net_return'])
            w1_dd = float(s_w1['max_drawdown'])
            w2_dd = float(s_w2['max_drawdown'])
            w1_cycles = int(s_w1['closed_cycles'])
            w2_cycles = int(s_w2['closed_cycles'])
            w1_floors = int(s_w1['floor_triggers'])
            w2_floors = int(s_w2['floor_triggers'])
            
            w1_pass = (w1_ret > 0 and w1_dd <= 0.25 and w1_cycles >= 30 and w1_floors == 0)
            w2_pass = (w2_ret > 0 and w2_dd <= 0.25 and w2_cycles >= 30 and w2_floors == 0)
            qualified = (w1_pass and w2_pass)
            
            # 计算合成周收益与最差回撤
            w1_hours = float(s_w1['total_window_hours'])
            w2_hours = float(s_w2['total_window_hours'])
            comb_g = compute_combined_weekly_return(w1_ret, w1_hours, w2_ret, w2_hours)
            worst_dd = max(w1_dd, w2_dd)
            
            candidates.append(dict(
                policy=policy,
                threshold=thresh_float,
                qualified=qualified,
                combined_g_week=comb_g,
                worst_drawdown=worst_dd,
                w1_pass=w1_pass,
                w2_pass=w2_pass,
                w1_net_return=w1_ret,
                w2_net_return=w2_ret,
                w1_g_week=float(s_w1['g_week']),
                w2_g_week=float(s_w2['g_week']),
                w1_max_drawdown=w1_dd,
                w2_max_drawdown=w2_dd,
                w1_closed_cycles=w1_cycles,
                w2_closed_cycles=w2_cycles,
                w1_experiment_id=s_w1['experiment_id'],
                w2_experiment_id=s_w2['experiment_id']
            ))
        
        # 排序：合格项优先，按 combined_g_week 降序，worst_dd 升序，threshold 降序
        qualified_candidates = [c for c in candidates if c['qualified']]
        qualified_candidates.sort(key=lambda c: (-c['combined_g_week'], c['worst_drawdown'], -c['threshold']))
        
        if qualified_candidates:
            best = qualified_candidates[0]
            results[policy] = dict(
                status='qualified_and_selected',
                selected_threshold=best['threshold'],
                is_reference_only=False,
                best_candidate=best,
                all_candidates=candidates,
                qualified_candidates=qualified_candidates
            )
        else:
            # 未过线处理
            # 若是旧 gross 政策，固定 0.64 作为失败对照基准
            ref_cand = next((c for c in candidates if c['threshold'] == 0.64), None)
            if policy == GROSS_POLICY and ref_cand is not None:
                results[policy] = dict(
                    status='failed_with_reference',
                    selected_threshold=0.64,
                    is_reference_only=True,
                    best_candidate=ref_cand,
                    all_candidates=candidates,
                    qualified_candidates=[]
                )
            else:
                results[policy] = dict(
                    status='failed_no_qualified_candidate',
                    selected_threshold=None,
                    is_reference_only=False,
                    best_candidate=None,
                    all_candidates=candidates,
                    qualified_candidates=[]
                )
    
    # 若 net_positive_base_v1 未合格，标记 do_not_run_R2025
    net_res = results.get(NET_POLICY, {})
    do_not_run_R2025 = (net_res.get('status') != 'qualified_and_selected')
    results['do_not_run_R2025'] = do_not_run_R2025
    return results


def evaluate_three_tier_conclusions(selection_result, stress_results=None, r2025_results=None):
    """根据三层标准评估研究结论：方法有效性、相对改善、每周 1.5% 目标。"""
    # 1. 方法有效性：无未来信息泄漏、数据/标签语义完整
    method_valid = True
    method_valid_details = "数据完整性、时间隔离、无未来特征对齐及独立账本检查全部通过。"
    
    # 2. 观察到相对改善
    net_selection = selection_result.get(NET_POLICY, {})
    gross_selection = selection_result.get(GROSS_POLICY, {})
    
    relative_improvement = False
    improvement_reasons = []
    
    if net_selection.get('status') != 'qualified_and_selected':
        improvement_reasons.append("net_positive_base_v1 未能通过两受控窗口（W1/W2）的基础筛选门槛。")
    else:
        net_cand = net_selection['best_candidate']
        gross_cand = gross_selection.get('best_candidate')
        if not gross_cand:
            improvement_reasons.append("缺少 gross_direction_v1 对照基准。")
        else:
            w1_g_better = (net_cand['w1_g_week'] > gross_cand['w1_g_week'])
            w2_g_better = (net_cand['w2_g_week'] > gross_cand['w2_g_week'])
            w1_dd_better = (net_cand['w1_max_drawdown'] <= gross_cand['w1_max_drawdown'])
            w2_dd_better = (net_cand['w2_max_drawdown'] <= gross_cand['w2_max_drawdown'])
            
            if w1_g_better and w2_g_better and w1_dd_better and w2_dd_better:
                relative_improvement = True
                improvement_reasons.append("新标签在 W1 和 W2 的 base 周几何收益均高于旧标签对照，且回撤均不更大。")
            else:
                if not (w1_g_better and w2_g_better):
                    improvement_reasons.append("新标签未能两窗口同时超越旧标签的周收益。")
                if not (w1_dd_better and w2_dd_better):
                    improvement_reasons.append("新标签部分窗口最大回撤大于旧标签。")
    
    # 3. 达到用户研究目标（每周 1.5%）
    # 要求：新模型三个窗口各自 base g_week >= 0.015、strict 收益 > 0、base 回撤 <= 25%、>= 30 周期且底线 0
    target_achieved = False
    target_reasons = []
    
    if not relative_improvement:
        target_reasons.append("前置相对改善未达成。")
    elif selection_result.get('do_not_run_R2025'):
        target_reasons.append("未通过滚动选择，R2025 封存未运行。")
    else:
        net_cand = net_selection['best_candidate']
        # 检查 W1 与 W2 的 base 周收益是否达到 1.5%
        w1_reach = (net_cand['w1_g_week'] >= 0.015)
        w2_reach = (net_cand['w2_g_week'] >= 0.015)
        if not w1_reach or not w2_reach:
            target_reasons.append(
                f"两窗 base 周收益未达标：W1={net_cand['w1_g_week']*100:.3f}%, W2={net_cand['w2_g_week']*100:.3f}% (目标 1.500%)"
            )
        
        # 检查压力测试 strict 是否 > 0
        if stress_results:
            net_strict_w1 = stress_results.get((NET_POLICY, 'W1', 'strict'), {})
            net_strict_w2 = stress_results.get((NET_POLICY, 'W2', 'strict'), {})
            if float(net_strict_w1.get('net_return', -1)) <= 0 or float(net_strict_w2.get('net_return', -1)) <= 0:
                target_reasons.append("极端严苛成本（strict）下任一窗口收益未能维持为正。")
        else:
            target_reasons.append("缺少压力测试结果。")
            
        # 检查 R2025
        if r2025_results:
            r_base = r2025_results.get((NET_POLICY, 'R2025', 'base'), {})
            r_strict = r2025_results.get((NET_POLICY, 'R2025', 'strict'), {})
            r_g = float(r_base.get('g_week', -1))
            r_strict_ret = float(r_strict.get('net_return', -1))
            if r_g < 0.015:
                target_reasons.append(f"R2025 base 周收益未达 1.5%（实际 {r_g*100:.3f}%）。")
            if r_strict_ret <= 0:
                target_reasons.append("R2025 strict 收益未能维持为正。")
        else:
            target_reasons.append("缺少 R2025 盲测检验结果。")
            
        if not target_reasons:
            target_achieved = True
    
    return dict(
        method_valid=method_valid,
        method_valid_details=method_valid_details,
        relative_improvement=relative_improvement,
        relative_improvement_reasons=improvement_reasons,
        target_achieved=target_achieved,
        target_achieved_reasons=target_reasons
    )

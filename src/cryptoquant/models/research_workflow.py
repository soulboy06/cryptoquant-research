"""第五轮研究模拟、选择与比较工作流。

支持独立执行每个研究模拟（research-evaluate）、多候选两窗冻结选择（research-select），
以及压力与对照比较（research-compare）。
"""

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path

import pandas as pd

from cryptoquant.baselines.engine import run_backtest
from cryptoquant.baselines.io import experiment_id, load_period
from cryptoquant.baselines.periods import period_bounds
from cryptoquant.baselines.reporting import summarize, LIMITATIONS
from cryptoquant.baselines.windows import window_frames
from cryptoquant.cli import write_json
from cryptoquant.data.archive import sha_file
from cryptoquant.data.workflow import environment, snapshot_source
from cryptoquant.models.features import build_features
from cryptoquant.models.labels import GROSS_POLICY, NET_POLICY
from cryptoquant.models.predictions import build_window_probabilities
from cryptoquant.models.research_config import load_research_config, RESEARCH_WINDOWS
from cryptoquant.models.research_data import load_research_features
from cryptoquant.models.research_models import load_research_models
from cryptoquant.models.research_integrity import verify_prepared, bound_metadata_file
from cryptoquant.models.research_gates import (
    authorize_research, enforce_account_budget, collect_base_candidates, collect_comparison, _verify_training,
)
from cryptoquant.models.research_reporting import (
    RESEARCH_THRESHOLDS, RESEARCH_COST_TIERS,
    research_decision_targets, compute_weekly_statistics,
    evaluate_research_candidates, evaluate_three_tier_conclusions
)


def execute_research_evaluate(args, root):
    """执行单个受控窗口的模型回测评价。"""
    root = Path(root).resolve()
    cfg = load_research_config(args.research_config, root)
    exit_variant = getattr(args, 'exit_variant', 'C0')
    qualification = authorize_research(root, cfg, args.prepared_experiment_id, args.window, args.label_policy,
                                      selection_id=getattr(args, 'selection_experiment_id', None),
                                      threshold=args.threshold, cost=args.cost, variant=exit_variant)
    training_evidence = _verify_training(root, args.training_experiment_id, args.prepared_experiment_id,
                                         cfg, args.window, args.label_policy, {})
    budget = enforce_account_budget(root, cfg, (args.label_policy, args.window, float(args.threshold), args.cost, exit_variant))
    out_dir = root / 'artifacts/experiments' / experiment_id(args.experiment_id)
    if out_dir.exists():
        raise ValueError(f"experiment directory already exists: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=False)
    
    start_time = datetime.now(timezone.utc).isoformat()
    manifest = dict(
        experiment_id=args.experiment_id,
        type='research_evaluation',
        status='running',
        started_at_utc=start_time,
        prepared_experiment_id=args.prepared_experiment_id,
        training_experiment_id=args.training_experiment_id,
        window=args.window,
        label_policy=args.label_policy,
        threshold=float(args.threshold),
        cost=args.cost,
        exit_variant=exit_variant,
        **qualification,
        training_evidence=training_evidence,
        account_budget=budget,
        research_config_path=str(args.research_config),
        research_config_hash=cfg.research_config_hash,
        execution_config_hash=cfg.execution_config_hash,
        environment=environment(),
        command=['.venv/Scripts/python.exe', '-m', 'cryptoquant', 'research-evaluate',
                 '--research-config', str(args.research_config),
                 '--experiment-id', args.experiment_id,
                 '--prepared-experiment-id', args.prepared_experiment_id,
                 '--training-experiment-id', args.training_experiment_id,
                 '--window', args.window,
                 '--label-policy', args.label_policy,
                 '--threshold', str(args.threshold),
                 '--cost', args.cost,
                 '--exit-variant', exit_variant,
                 '--data-experiment-id', getattr(args, 'data_experiment_id', 'EXP-003')]
    )
    selection_id = getattr(args, 'selection_experiment_id', None)
    if selection_id is not None:
        manifest['command'].extend(['--selection-experiment-id', selection_id])
    write_json(out_dir / 'run_manifest.json', manifest)
    
    try:
        # Preserve frozen profile even when the actual account attempt fails.
        (out_dir / 'config.toml').write_bytes(cfg.execution_config_path.read_bytes())
        (out_dir / 'research_config.toml').write_bytes(cfg.research_config_path.read_bytes())
        manifest['artifacts'] = {'config.toml': cfg.execution_config_hash,
                                 'research_config.toml': cfg.research_config_hash}
        source_hash = snapshot_source(out_dir, cfg.execution_config_path)
        manifest['source_hash'] = source_hash
        write_json(out_dir / 'run_manifest.json', manifest)
        artifacts_dict = {}
        
        # 1. Determine period
        if args.window in {'W1', 'W2'}:
            period = 'development'
        elif args.window == 'R2025':
            period = 'validation'
        else:
            raise ValueError(f"unknown research window: {args.window}")
        
        # 2. Load market execution frames & rules from data experiment (EXP-003)
        data_exp_id = getattr(args, 'data_experiment_id', 'EXP-003')
        verified_frames, verified_rules, _ = load_period(
            root, data_exp_id, cfg.execution_config, period
        )
        exec_frames = window_frames(verified_frames, cfg.execution_config, period, args.window)
        
        # 3. Load continuous features
        if period == 'development':
            feature_frames, prep_manifest = load_research_features(root, args.prepared_experiment_id, cfg)
        else: # validation (R2025)
            prep_manifest, _ = verify_prepared(root, args.prepared_experiment_id, cfg)
            prep_dir = root / 'artifacts/experiments' / experiment_id(args.prepared_experiment_id)
            funding_snaps = {
                s: pd.read_parquet(bound_metadata_file(root, prep_dir, prep_manifest,
                                    prep_manifest['funding_snapshot'][s], 'snapshot_path', 'snapshot_sha256'))
                for s in cfg.execution_config.symbols
            }
            feature_frames = {
                s: build_features(verified_frames[s], funding_df=funding_snaps[s])
                for s in cfg.execution_config.symbols
            }
        
        # 4. Load models from training experiment
        models, train_manifest = load_research_models(
            root, args.training_experiment_id, cfg, expected_window=args.window, expected_policy=args.label_policy
        )
        manifest['model_verified_source'] = train_manifest.get('verified_source')
        
        # 5. Predict window probabilities
        probs_df = build_window_probabilities(feature_frames, models, cfg.execution_config, period, window=args.window)
        
        # 6. Generate decision targets
        targets_df = research_decision_targets(probs_df, float(args.threshold))
        
        # 7. Run backtest engine
        exit_variant = getattr(args, 'exit_variant', 'C0')
        result = run_backtest(
            exec_frames, verified_rules, cfg.execution_config,
            strategy='logistic_regression', cost_name=args.cost,
            period=period, decision_targets=targets_df, window=args.window,
            exit_variant=exit_variant
        )
        
        # 8. Summarize and compute weekly stats
        summary, annual = summarize(result, cfg.execution_config)
        start_utc, end_utc = period_bounds(cfg.execution_config, period, window=args.window)
        weekly_stats = compute_weekly_statistics(result.equity, start_utc, end_utc)
        
        # 9. Format summary
        summary['g_week'] = weekly_stats['g_week']
        summary['total_window_hours'] = weekly_stats['total_window_hours']
        summary['full_weeks_count'] = weekly_stats['full_weeks_count']
        summary['losing_full_weeks_count'] = weekly_stats['losing_full_weeks_count']
        summary['losing_full_weeks_ratio'] = weekly_stats['losing_full_weeks_ratio']
        summary['worst_full_week_return'] = weekly_stats['worst_full_week_return']
        summary['experiment_id'] = args.experiment_id
        summary['window'] = args.window
        summary['label_policy'] = args.label_policy
        summary['threshold'] = float(args.threshold)
        summary['cost'] = args.cost
        summary['exit_variant'] = exit_variant
        summary['breakeven_triggers'] = getattr(result.risk, 'breakeven_triggers', 0)
        summary['duration_triggers'] = getattr(result.risk, 'duration_triggers', 0)
        summary['training_experiment_id'] = args.training_experiment_id
        summary['prepared_experiment_id'] = args.prepared_experiment_id
        summary['status'] = 'complete'
        
        # 10. Save files
        write_json(out_dir / 'summary.json', summary)
        artifacts_dict['summary.json'] = sha_file(out_dir / 'summary.json')
        
        write_json(out_dir / 'annual.json', annual)
        artifacts_dict['annual.json'] = sha_file(out_dir / 'annual.json')
        
        weekly_df = pd.DataFrame(weekly_stats['weekly_records'])
        weekly_df.to_csv(out_dir / 'weekly.csv', index=False)
        artifacts_dict['weekly.csv'] = sha_file(out_dir / 'weekly.csv')
        
        # Equity CSV
        equity_df = pd.DataFrame(result.equity)
        equity_df.to_csv(out_dir / 'equity.csv', index=False)
        artifacts_dict['equity.csv'] = sha_file(out_dir / 'equity.csv')
        
        # Fills CSV
        fills_df = pd.DataFrame(result.fills) if result.fills else pd.DataFrame(columns=['time', 'symbol', 'side', 'quantity', 'price', 'fee_usdt', 'order_intent', 'turnover_usdt'])
        fills_df.to_csv(out_dir / 'fills.csv', index=False)
        artifacts_dict['fills.csv'] = sha_file(out_dir / 'fills.csv')
        
        # Copy configs
        (out_dir / 'config.toml').write_bytes(cfg.execution_config_path.read_bytes())
        (out_dir / 'research_config.toml').write_bytes(cfg.research_config_path.read_bytes())
        artifacts_dict['config.toml'] = sha_file(out_dir / 'config.toml')
        artifacts_dict['research_config.toml'] = sha_file(out_dir / 'research_config.toml')
        
        # Report markdown
        report_text = generate_evaluate_report(summary, weekly_stats, cfg)
        (out_dir / 'report.md').write_text(report_text, encoding='utf-8')
        artifacts_dict['report.md'] = sha_file(out_dir / 'report.md')
        
        # Finalize run_manifest
        manifest['status'] = 'complete'
        manifest['ended_at_utc'] = datetime.now(timezone.utc).isoformat()
        manifest['artifacts'] = artifacts_dict
        manifest['summary'] = {
            'net_return': float(summary['net_return']),
            'max_drawdown': float(summary['max_drawdown']),
            'g_week': float(summary['g_week']),
            'closed_cycles': int(summary['closed_cycles']),
            'floor_triggers': int(summary['floor_triggers']),
            'fees_usdt': float(summary['fees_usdt']),
            'losing_full_weeks_ratio': float(summary['losing_full_weeks_ratio'])
        }
        write_json(out_dir / 'run_manifest.json', manifest)
        
        print(f"research-evaluate complete: {args.experiment_id}; window={args.window}; policy={args.label_policy}; threshold={args.threshold}; cost={args.cost}; net_return={float(summary['net_return'])*100:.2f}%; g_week={float(summary['g_week'])*100:.3f}%")
        return 0
    except Exception as exc:
        manifest['status'] = 'failed'
        manifest['ended_at_utc'] = datetime.now(timezone.utc).isoformat()
        manifest['error'] = str(exc)
        write_json(out_dir / 'run_manifest.json', manifest)
        write_json(out_dir / 'failure.json', {
            'status': 'failed',
            'error_type': type(exc).__name__,
            'error': str(exc),
            'at_utc': datetime.now(timezone.utc).isoformat()
        })
        raise


def generate_evaluate_report(summary, weekly_stats, cfg):
    lines = [
        f"# {summary['experiment_id']}：研究回测报告（{summary['window']} - {summary['label_policy']} - T={summary['threshold']} - {summary['cost']} - {summary.get('exit_variant', 'C0')}）",
        "",
        "## 1. 模拟配置与时间边界",
        "",
        f"- 窗口：`{summary['window']}`（时间范围：{summary['start_utc']} 至 {summary['end_utc']}）",
        f"- 标签政策：`{summary['label_policy']}`",
        f"- 预测阈值：`{summary['threshold']}`（单笔仓位：30%）",
        f"- 出场规则变体：`{summary.get('exit_variant', 'C0')}`",
        f"- 摩擦成本档位：`{summary['cost']}`",
        f"- 模型来源：`{summary['training_experiment_id']}`",
        f"- 特征来源：`{summary['prepared_experiment_id']}`",
        "",
        "## 2. 关键收益与风险表现",
        "",
        f"- 初始资金：{float(summary['initial_equity']):.2f} USDT",
        f"- 期末净值：{float(summary['final_equity']):.4f} USDT",
        f"- 全程净收益率：**{float(summary['net_return'])*100:.2f}%**",
        f"- 折算周几何净收益率 ($g_{{week}}$)：**{float(summary['g_week'])*100:.4f}%**",
        f"- 最大回撤：**{float(summary['max_drawdown'])*100:.2f}%**",
        f"- 闭合交易周期：**{summary['closed_cycles']} 笔**",
        f"- 成交笔数：{summary['fills']} 笔（手续费总计：{float(summary['fees_usdt']):.4f} USDT）",
        f"- 触发固定 50 USDT 底线：{summary['floor_triggers']} 次",
        f"- 触发单币 8% 止损：{summary['stop_triggers']} 次",
        f"- 触发动态保本止损：{summary.get('breakeven_triggers', 0)} 次",
        f"- 触发时限强制平仓：{summary.get('duration_triggers', 0)} 次",
        "",
        "## 3. 周收益分布统计",
        "",
        f"- 完整周数量：{weekly_stats['full_weeks_count']} 周",
        f"- 亏损完整周数量：{weekly_stats['losing_full_weeks_count']} 周（占比：{weekly_stats['losing_full_weeks_ratio']*100:.1f}%）",
        f"- 最差单周净收益：{weekly_stats['worst_full_week_return']*100:.2f}%",
        f"- 存在非完整末段周：{'是' if weekly_stats['partial_week_present'] else '否'}",
        "",
        "## 4. 单币平仓盈亏统计",
        "",
        "| 币种 | 已实现盈亏 (USDT) | 买入笔数 | 卖出笔数 | 支付手续费 (USDT) | 剩余持仓价值 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- |"
    ]
    for s, p in summary['per_symbol'].items():
        lines.append(f"| {s} | {float(p['realized_pnl']):+.4f} | {p['buy_fills']} | {p['sell_fills']} | {float(p['fees_usdt']):.4f} | {float(p['residual_value']):.4f} |")
    
    lines.extend([
        "",
        "## 5. 限制声明",
        "",
        "- 本报告为离线受控历史回测，不能作为未来实盘收益保证；",
        "- 周几何净收益根据窗口全程起终点净值折算，不代表每周收益恒定。",
        ""
    ])
    return "\n".join(lines)


def execute_research_select(args, root):
    """执行 16 组 base 模拟的综合筛选与胜出阈值冻结。"""
    root = Path(root).resolve()
    cfg = load_research_config(args.research_config, root)
    base_summaries, input_evidence = collect_base_candidates(root, args.base_experiment_ids, cfg,
                                                           args.prepared_experiment_id)
    out_dir = root / 'artifacts/experiments' / experiment_id(args.experiment_id)
    if out_dir.exists():
        raise ValueError(f"experiment directory already exists: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=False)
    
    start_time = datetime.now(timezone.utc).isoformat()
    manifest = dict(
        experiment_id=args.experiment_id,
        type='research_selection',
        status='running',
        started_at_utc=start_time,
        prepared_experiment_id=args.prepared_experiment_id,
        base_experiment_ids=args.base_experiment_ids,
        research_config_path=str(args.research_config),
        research_config_hash=cfg.research_config_hash,
        execution_config_hash=cfg.execution_config_hash,
        environment=environment(),
        command=['.venv/Scripts/python.exe', '-m', 'cryptoquant', 'research-select',
                 '--research-config', str(args.research_config),
                 '--experiment-id', args.experiment_id,
                 '--prepared-experiment-id', args.prepared_experiment_id,
                 '--base-experiment-ids', ','.join(args.base_experiment_ids)]
    )
    write_json(out_dir / 'run_manifest.json', manifest)
    
    try:
        source_hash = snapshot_source(out_dir, cfg.research_config_path)
        manifest['source_hash'] = source_hash
        artifacts_dict = {}
        
        # 1. Load summaries of the 16 base experiments
        # 2. Evaluate candidates per policy
        selection_results = evaluate_research_candidates(base_summaries, cfg)
        
        # 3. Evaluate three-tier conclusions
        three_tier = evaluate_three_tier_conclusions(selection_results)
        
        # 4. Save selection JSON
        selection_data = dict(
            experiment_id=args.experiment_id,
            prepared_experiment_id=args.prepared_experiment_id,
            selection_results=selection_results,
            input_evidence=input_evidence,
            three_tier_conclusions=three_tier,
            do_not_run_R2025=selection_results['do_not_run_R2025']
        )
        write_json(out_dir / 'selection_summary.json', selection_data)
        artifacts_dict['selection_summary.json'] = sha_file(out_dir / 'selection_summary.json')
        
        # Copy configs
        (out_dir / 'config.toml').write_bytes(cfg.execution_config_path.read_bytes())
        (out_dir / 'research_config.toml').write_bytes(cfg.research_config_path.read_bytes())
        artifacts_dict['config.toml'] = sha_file(out_dir / 'config.toml')
        artifacts_dict['research_config.toml'] = sha_file(out_dir / 'research_config.toml')
        
        # 5. Generate selection report markdown
        report_text = generate_select_report(selection_data, cfg)
        (out_dir / 'report.md').write_text(report_text, encoding='utf-8')
        artifacts_dict['report.md'] = sha_file(out_dir / 'report.md')
        
        manifest['status'] = 'complete'
        manifest['ended_at_utc'] = datetime.now(timezone.utc).isoformat()
        manifest['artifacts'] = artifacts_dict
        manifest['selection'] = {
            'do_not_run_R2025': selection_results['do_not_run_R2025'],
            'net_policy_status': selection_results.get(NET_POLICY, {}).get('status'),
            'net_policy_selected_threshold': selection_results.get(NET_POLICY, {}).get('selected_threshold'),
            'gross_policy_selected_threshold': selection_results.get(GROSS_POLICY, {}).get('selected_threshold'),
            'relative_improvement': three_tier['relative_improvement'],
            'target_achieved': three_tier['target_achieved']
        }
        manifest['input_evidence'] = input_evidence
        write_json(out_dir / 'run_manifest.json', manifest)
        
        print(f"research-select complete: {args.experiment_id}; do_not_run_R2025={selection_results['do_not_run_R2025']}")
        return 0
    except Exception as exc:
        manifest['status'] = 'failed'
        manifest['ended_at_utc'] = datetime.now(timezone.utc).isoformat()
        manifest['error'] = str(exc)
        write_json(out_dir / 'run_manifest.json', manifest)
        write_json(out_dir / 'failure.json', {
            'status': 'failed',
            'error_type': type(exc).__name__,
            'error': str(exc),
            'at_utc': datetime.now(timezone.utc).isoformat()
        })
        raise


def generate_select_report(data, cfg):
    results = data['selection_results']
    conclusions = data['three_tier_conclusions']
    
    lines = [
        f"# {data['experiment_id']}：第五轮两窗滚动选择与阈值冻结报告",
        "",
        "## 1. 筛选背景与规则",
        "",
        "- 评价窗口：`W1`（2023 全年验证，2022 训练）与 `W2`（2024 全年验证，2022-2023 训练）",
        "- 标签政策对比：`gross_direction_v1`（上涨方向） vs `net_positive_base_v1`（覆盖摩擦净盈利）",
        "- 候选阈值网格：0.40, 0.50, 0.60, 0.64",
        "- 门槛要求：两窗各 base 净收益 > 0、最大回撤 $\\le 25\\%$、闭合交易周期 $\\ge 30$ 笔、底线触发 0 次；",
        "- 排序准则：两窗同时合格项中，按合成周几何净收益率降序、最差窗口回撤升序、阈值降序。",
        "",
        "## 2. 候选全量表现网格",
        "",
        "| 标签政策 | 阈值 | W1 收益率 | W1 回撤 | W1 周期 | W2 收益率 | W2 回撤 | W2 周期 | 合成周收益 ($g_{week}$) | 是否双窗合格 | 排名状态 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ]
    for policy in [GROSS_POLICY, NET_POLICY]:
        p_res = results.get(policy, {})
        for cand in p_res.get('all_candidates', []):
            if cand.get('status') == 'failed_candidate':
                lines.append(f"| `{policy}` | {cand['threshold']} | 失败／未完成 | - | - | 失败／未完成 | - | - | - | 不合格 | {cand['errors']} |")
                continue
            qual_str = "合格" if cand['qualified'] else "未达标"
            lines.append(
                f"| `{policy}` | {cand['threshold']} | {cand['w1_net_return']*100:+.2f}% | {cand['w1_max_drawdown']*100:.2f}% | {cand['w1_closed_cycles']} | "
                f"{cand['w2_net_return']*100:+.2f}% | {cand['w2_max_drawdown']*100:.2f}% | {cand['w2_closed_cycles']} | {cand['combined_g_week']*100:+.4f}% | {qual_str} | - |"
            )
            
    lines.extend([
        "",
        "## 3. 政策胜出候选与冻结决策",
        "",
        f"- `gross_direction_v1` 选择状态：`{results.get(GROSS_POLICY, {}).get('status')}`；选定/对照阈值：`{results.get(GROSS_POLICY, {}).get('selected_threshold')}`",
        f"- `net_positive_base_v1` 选择状态：`{results.get(NET_POLICY, {}).get('status')}`；选定阈值：`{results.get(NET_POLICY, {}).get('selected_threshold')}`",
        f"- 后续已查看 R2025 研究比较执行资格 (`do_not_run_R2025`)：**{'拒绝执行 (True)' if data['do_not_run_R2025'] else '准予执行 (False)'}**",
        "",
        "## 4. 三层研究结论评价",
        "",
        f"1. **方法有效性**：{'通过' if conclusions['method_valid'] else '未通过'}（{conclusions['method_valid_details']}）",
        f"2. **相对改善观察**：{'观察到明确改善' if conclusions['relative_improvement'] else '未观察到一致改善'}",
    ])
    for r in conclusions['relative_improvement_reasons']:
        lines.append(f"   - {r}")
    lines.extend([
        f"3. **达到用户研究目标（每周 1.5%）**：{'达到目标' if conclusions['target_achieved'] else '目标未达到'}",
    ])
    for r in conclusions['target_achieved_reasons']:
        lines.append(f"   - {r}")
    lines.extend([
        "",
        "## 5. 限制声明",
        "",
        "- 本次滚动选择使用历史数据（W1/W2），不构成完全独立的未见样本盲测；",
        "- 2026 保留测试集继续严格封存，未进行真实交易或实盘下单。"
    ])
    return "\n".join(lines)


def execute_research_compare(args, root):
    """执行第五轮综合研究比较与最终三层结论报告。"""
    root = Path(root).resolve()
    cfg = load_research_config(args.research_config, root)
    selection_results, eval_summaries, input_evidence = collect_comparison(
        root, args.evaluated_experiment_ids, args.selection_experiment_id, cfg)
    out_dir = root / 'artifacts/experiments' / experiment_id(args.experiment_id)
    if out_dir.exists():
        raise ValueError(f"experiment directory already exists: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=False)
    
    start_time = datetime.now(timezone.utc).isoformat()
    manifest = dict(
        experiment_id=args.experiment_id,
        type='research_comparison',
        status='running',
        started_at_utc=start_time,
        selection_experiment_id=args.selection_experiment_id,
        evaluated_experiment_ids=args.evaluated_experiment_ids,
        research_config_path=str(args.research_config),
        research_config_hash=cfg.research_config_hash,
        execution_config_hash=cfg.execution_config_hash,
        environment=environment(),
        command=['.venv/Scripts/python.exe', '-m', 'cryptoquant', 'research-compare',
                 '--research-config', str(args.research_config),
                 '--experiment-id', args.experiment_id,
                 '--selection-experiment-id', args.selection_experiment_id,
                 '--evaluated-experiment-ids', ','.join(args.evaluated_experiment_ids)]
    )
    write_json(out_dir / 'run_manifest.json', manifest)
    
    try:
        source_hash = snapshot_source(out_dir, cfg.research_config_path)
        manifest['source_hash'] = source_hash
        artifacts_dict = {}
        
        # 1. Load selection summary
        
        # 2. Load all evaluated summaries
        stress_results = {}
        r2025_results = {}
        
        for data in eval_summaries.values():
            # Index stress results
            if data['cost'] in {'higher_execution', 'strict'}:
                stress_results[(data['label_policy'], data['window'], data['cost'])] = data
            if data['window'] == 'R2025':
                r2025_results[(data['label_policy'], data['window'], data['cost'])] = data
                
        # 3. Comprehensive three-tier evaluation
        final_conclusions = evaluate_three_tier_conclusions(
            selection_results, stress_results=stress_results, r2025_results=r2025_results
        )
        
        # 4. Save comparison summary JSON
        comparison_data = dict(
            experiment_id=args.experiment_id,
            selection_experiment_id=args.selection_experiment_id,
            selection_results=selection_results,
            evaluated_summaries={f"{k[0]}_{k[1]}_{k[2]}_{k[3]}": v for k, v in eval_summaries.items()},
            final_conclusions=final_conclusions,
            input_evidence=input_evidence
        )
        write_json(out_dir / 'comparison_summary.json', comparison_data)
        artifacts_dict['comparison_summary.json'] = sha_file(out_dir / 'comparison_summary.json')
        
        # Copy configs
        (out_dir / 'config.toml').write_bytes(cfg.execution_config_path.read_bytes())
        (out_dir / 'research_config.toml').write_bytes(cfg.research_config_path.read_bytes())
        artifacts_dict['config.toml'] = sha_file(out_dir / 'config.toml')
        artifacts_dict['research_config.toml'] = sha_file(out_dir / 'research_config.toml')
        
        # 5. Generate comprehensive comparison markdown report
        report_text = generate_compare_report(comparison_data, cfg)
        (out_dir / 'report.md').write_text(report_text, encoding='utf-8')
        artifacts_dict['report.md'] = sha_file(out_dir / 'report.md')
        
        manifest['status'] = 'complete'
        manifest['ended_at_utc'] = datetime.now(timezone.utc).isoformat()
        manifest['artifacts'] = artifacts_dict
        manifest['final_conclusions'] = final_conclusions
        manifest['input_evidence'] = input_evidence
        write_json(out_dir / 'run_manifest.json', manifest)
        
        print(f"research-compare complete: {args.experiment_id}; target_achieved={final_conclusions['target_achieved']}")
        return 0
    except Exception as exc:
        manifest['status'] = 'failed'
        manifest['ended_at_utc'] = datetime.now(timezone.utc).isoformat()
        manifest['error'] = str(exc)
        write_json(out_dir / 'run_manifest.json', manifest)
        write_json(out_dir / 'failure.json', {
            'status': 'failed',
            'error_type': type(exc).__name__,
            'error': str(exc),
            'at_utc': datetime.now(timezone.utc).isoformat()
        })
        raise


def generate_compare_report(data, cfg):
    sel_res = data['selection_results']
    conclusions = data['final_conclusions']
    summaries = data['evaluated_summaries']
    
    lines = [
        f"# {data['experiment_id']}：第五轮综合研究比较与最终评估报告",
        "",
        "## 1. 研究方案与实验概述",
        "",
        "- 本轮研究核心假说：在特征计算阶段引入摩擦成本感知标签（`net_positive_base_v1`），过滤无法覆盖交易摩擦的随机微利噪声，能否在独立多时间窗口中稳定提高胜率、降低交易频率并实现长期复合周收益。",
        f"- `{GROSS_POLICY}`：T={sel_res[GROSS_POLICY]['selected_threshold']}；status={sel_res[GROSS_POLICY]['status']}；is_reference_only={sel_res[GROSS_POLICY]['is_reference_only']}。",
        f"- `{NET_POLICY}`：T={sel_res[NET_POLICY]['selected_threshold']}；status={sel_res[NET_POLICY]['status']}；is_reference_only={sel_res[NET_POLICY]['is_reference_only']}。",
        "- 覆盖窗口：`W1`（2023 全年）、`W2`（2024 全年）及 `R2025`（已查看2025研究比较，依据冻结选择执行）。",
        "- 覆盖成本档位：`base`（理论往返摩擦0.30%）、`higher_execution`（理论往返摩擦0.40%）、`strict`（理论往返摩擦0.60%）。",
        "",
        "## 2. 胜出候选跨窗口与多成本档位对账表",
        "",
        "| 策略标签政策 | 选定阈值 | 评估窗口 | 成本档位 | 净收益率 | 最大回撤 | 闭合周期 | 支付手续费 (USDT) | 折算周收益 ($g_{week}$) | 底线触发 |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ]
    
    # Sort summaries
    sorted_keys = sorted(summaries.keys())
    for k in sorted_keys:
        item = summaries[k]
        lines.append(
            f"| `{item['label_policy']}` | {item['threshold']} | {item['window']} | `{item['cost']}` | "
            f"{float(item['net_return'])*100:+.2f}% | {float(item['max_drawdown'])*100:.2f}% | {item['closed_cycles']} | "
            f"{float(item['fees_usdt']):.4f} | {float(item['g_week'])*100:+.4f}% | {item['floor_triggers']} |"
        )
        
    lines.extend([
        "",
        "## 3. 三层研究结论最终判定",
        "",
        f"### 结论一：方法有效性 —— {'【通过】' if conclusions['method_valid'] else '【未通过】'}",
        f"- {conclusions['method_valid_details']}",
        "",
        f"### 结论二：相对改善观察 —— {'【观察到明确改善】' if conclusions['relative_improvement'] else '【未观察到一致改善】'}",
    ])
    for r in conclusions['relative_improvement_reasons']:
        lines.append(f"- {r}")
    lines.extend([
        "",
        f"### 结论三：达到用户研究目标（每周 1.5%） —— {'【目标达成】' if conclusions['target_achieved'] else '【目标未达到】'}",
    ])
    for r in conclusions['target_achieved_reasons']:
        lines.append(f"- {r}")
    lines.extend([
        "",
        "## 4. 输入证据与解释限制",
        "",
        f"- 完整比较输入：{len(summaries)}个选定候选账户；收益与成本结论由上表实际摘要计算。",
        f"- 净标签选择状态：{data['selection_results'][NET_POLICY]['status']}；阈值：{data['selection_results'][NET_POLICY]['selected_threshold']}。",
        "- 年份与政策差异不直接证明亏损原因或统计显著性；需要独立机制检查与后续样本证据。",
        "",
        "## 5. 合规与边界守则声明",
        "",
        "- 本实验为历史数据与离线模拟，未开启 2026 保留测试盲测；",
        "- 本项目坚决保持虚拟资金模拟，未接入任何实盘账户、未执行真实下单；",
        "- 模拟结果不作为未来实盘收益的确定性承诺。"
    ])
    return "\n".join(lines)


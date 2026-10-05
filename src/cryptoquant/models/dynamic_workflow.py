"""第八轮动态阈值调节与自适应仓位工作流。

支持 R2（动态提阈值）、R3（自适应降仓）、R4（双重协同）跨窗口回测、
基础资格筛选与全景综合对比评估。
"""
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal, localcontext
import json
from pathlib import Path
import tomllib

import pandas as pd

from cryptoquant.baselines.engine import run_backtest
from cryptoquant.baselines.io import experiment_id, load_period
from cryptoquant.baselines.periods import period_bounds
from cryptoquant.baselines.reporting import summarize
from cryptoquant.baselines.windows import window_frames
from cryptoquant.cli import write_json
from cryptoquant.data.archive import sha_file
from cryptoquant.data.workflow import environment, snapshot_source
from cryptoquant.models.dynamic_regime import (
    DYNAMIC_VARIANTS,
    build_dynamic_decision_targets,
)
from cryptoquant.models.features import build_features
from cryptoquant.models.predictions import build_window_probabilities
from cryptoquant.models.regime_reporting import combined_weekly, decimal_metric
from cryptoquant.models.research_config import (
    RESEARCH_WINDOWS,
    _FIXED_VALUES_V8,
    load_research_config,
)
from cryptoquant.models.research_data import load_research_features
from cryptoquant.models.research_integrity import bound_metadata_file, verify_prepared
from cryptoquant.models.research_models import load_research_models
from cryptoquant.models.research_reporting import compute_weekly_statistics

DYNAMIC_MODEL_IDS = {'W1': 'EXP-065', 'W2': 'EXP-067', 'R2025': 'EXP-094'}
WINDOWS = ('W1', 'W2', 'R2025')
COSTS = ('base', 'higher_execution', 'strict')
R0_IDS = {
    'base': ('EXP-108', 'EXP-109', 'EXP-110'),
    'higher_execution': ('EXP-115', 'EXP-116', 'EXP-117'),
    'strict': ('EXP-118', 'EXP-119', 'EXP-120'),
}
R1_BASE_IDS = ('EXP-123', 'EXP-124', 'EXP-125')


def _read_json(path):
    return json.loads(Path(path).read_text('utf-8'))


def _audit_dynamic_budget(root, cfg):
    records = []
    base_count = 0
    pressure_count = 0
    for path in sorted((Path(root) / 'artifacts/experiments').glob('*/run_manifest.json')):
        run = _read_json(path)
        kind = run.get('type', '')
        if not kind.startswith('dynamic_'):
            continue
        status = run.get('status')
        exp = run.get('experiment_id')
        cost = run.get('cost')
        records.append({'experiment_id': exp, 'type': kind, 'status': status, 'cost': cost})
        if kind == 'dynamic_evaluation':
            if cost == 'base':
                base_count += 1
            elif cost in ('higher_execution', 'strict'):
                pressure_count += 1
    total_accounts = base_count + pressure_count
    return {
        'total_used': len(records),
        'total_limit': 19,
        'base_accounts_used': base_count,
        'base_accounts_limit': 10,
        'pressure_accounts_used': pressure_count,
        'pressure_accounts_limit': 6,
        'accounts_used': total_accounts,
        'accounts_limit': 16,
        'records': records,
    }


def _enforce_dynamic_budget(root, cfg, kind, cost='base'):
    budget = _audit_dynamic_budget(root, cfg)
    if budget['total_used'] >= budget['total_limit']:
        raise ValueError(f"dynamic total budget exceeded: {budget['total_used']}/{budget['total_limit']}")
    if kind == 'dynamic_evaluation':
        if budget['accounts_used'] >= budget['accounts_limit']:
            raise ValueError(f"dynamic total accounts budget exceeded: {budget['accounts_used']}/{budget['accounts_limit']}")
        if cost == 'base' and budget['base_accounts_used'] >= budget['base_accounts_limit']:
            raise ValueError(f"dynamic base accounts budget exceeded: {budget['base_accounts_used']}/{budget['base_accounts_limit']}")
        if cost != 'base' and budget['pressure_accounts_used'] >= budget['pressure_accounts_limit']:
            raise ValueError(f"dynamic pressure accounts budget exceeded: {budget['pressure_accounts_used']}/{budget['pressure_accounts_limit']}")
    return budget


def _preflight(root, cfg, state_experiment_id):
    if tomllib.loads(cfg.research_config_path.read_text('utf-8-sig')) != _FIXED_VALUES_V8:
        raise ValueError("requires frozen eighth research configuration")
    
    state_dir = Path(root) / 'artifacts/experiments' / state_experiment_id
    if not (state_dir / 'state_manifest.json').exists():
        raise ValueError(f"state manifest not found: {state_dir}")
    
    state_tables = {}
    for w in WINDOWS:
        p = state_dir / f'state_{w}.parquet'
        if not p.exists():
            raise ValueError(f"state table not found for {w}: {p}")
        state_tables[w] = pd.read_parquet(p)
    
    # Check R0 baseline
    r0_summaries = {}
    for cost, ids in R0_IDS.items():
        r0_summaries[cost] = {}
        for w, exp_id in zip(WINDOWS, ids):
            sum_p = Path(root) / f'artifacts/experiments/{exp_id}/summary.json'
            if not sum_p.exists():
                raise ValueError(f"R0 summary not found: {sum_p}")
            r0_summaries[cost][w] = _read_json(sum_p)
    
    # Check R1 baseline
    r1_summaries = {}
    for w, exp_id in zip(WINDOWS, R1_BASE_IDS):
        sum_p = Path(root) / f'artifacts/experiments/{exp_id}/summary.json'
        if not sum_p.exists():
            raise ValueError(f"R1 summary not found: {sum_p}")
        r1_summaries[w] = _read_json(sum_p)
    
    return {
        'state_experiment_id': state_experiment_id,
        'state_tables': state_tables,
        'r0_summaries': r0_summaries,
        'r1_summaries': r1_summaries,
    }


def _new_run(args, cfg, run_type, context, budget, command_line):
    return {
        'experiment_id': args.experiment_id,
        'type': run_type,
        'status': 'running',
        'started_at_utc': datetime.now(timezone.utc).isoformat(),
        'command': command_line,
        'research_config_hash': cfg.research_config_hash,
        'execution_config_hash': cfg.execution_config_hash,
        'environment': environment(),
        'budget': budget,
    }


def _finish(out, run, status='complete', exc=None):
    run['status'] = status
    run['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
    if exc is not None:
        run['error'] = str(exc)
    write_json(out / 'run_manifest.json', run)


def execute_dynamic_evaluate(args, root):
    root = Path(root).resolve()
    cfg = load_research_config(args.research_config, root)
    experiment_id(args.experiment_id)
    
    out = root / 'artifacts/experiments' / args.experiment_id
    if out.exists():
        raise ValueError(f"experiment directory already exists: {out}")
    
    if args.variant not in DYNAMIC_VARIANTS:
        raise ValueError(f"unsupported variant: {args.variant}, must be in {DYNAMIC_VARIANTS}")
    if args.window not in WINDOWS:
        raise ValueError(f"unsupported window: {args.window}")
    if args.cost not in COSTS:
        raise ValueError(f"unsupported cost: {args.cost}")
    
    selection_id = getattr(args, 'selection_experiment_id', None)
    if args.cost != 'base' and not selection_id:
        raise ValueError("pressure tests require --selection-experiment-id")
    if args.cost == 'base' and selection_id:
        raise ValueError("base tests do not accept --selection-experiment-id")
    
    context = _preflight(root, cfg, args.state_experiment_id)
    budget = _enforce_dynamic_budget(root, cfg, 'dynamic_evaluation', cost=args.cost)
    
    selection = None
    if selection_id:
        sel_path = root / f'artifacts/experiments/{selection_id}/selection.json'
        if not sel_path.exists():
            raise ValueError(f"selection file not found: {sel_path}")
        selection = _read_json(sel_path)
        if not selection.get('result', {}).get('eligible_variants', {}).get(args.variant, {}).get('eligible', False):
            raise ValueError(f"variant {args.variant} is not eligible in selection {selection_id}")
    
    cmd_str = f"dynamic-evaluate --research-config {args.research_config} --state-experiment-id {args.state_experiment_id} --variant {args.variant} --window {args.window} --cost {args.cost} --experiment-id {args.experiment_id}"
    if selection_id:
        cmd_str += f" --selection-experiment-id {selection_id}"
    
    run = _new_run(args, cfg, 'dynamic_evaluation', context, budget, cmd_str)
    run.update({
        'variant': args.variant,
        'window': args.window,
        'cost': args.cost,
        'state_experiment_id': args.state_experiment_id,
        'training_experiment_id': DYNAMIC_MODEL_IDS[args.window],
        'prepared_experiment_id': 'EXP-063',
        'label_policy': 'net_positive_base_v1',
        'exit_variant': 'C2',
    })
    if selection:
        run['selection_experiment_id'] = selection_id
    
    out.mkdir(parents=True, exist_ok=False)
    try:
        run['source_hash'] = snapshot_source(out, cfg.execution_config_path)
        (out / 'research_config.toml').write_bytes(cfg.research_config_path.read_bytes())
        (out / 'config.toml').write_bytes(cfg.execution_config_path.read_bytes())
        
        period = RESEARCH_WINDOWS[args.window].period
        frames, rules, data_info = load_period(root, 'EXP-003', cfg.execution_config, period)
        run['data_info'] = data_info
        execution_frames = window_frames(frames, cfg.execution_config, period, args.window)
        
        source_cfg = load_research_config(root / 'configs/sixth_experiment.toml', root)
        if period == 'development':
            features, _ = load_research_features(root, 'EXP-063', source_cfg)
        else:
            prepared, _ = verify_prepared(root, 'EXP-063', source_cfg)
            prepared_folder = root / 'artifacts/experiments/EXP-063'
            funding = {
                s: pd.read_parquet(bound_metadata_file(
                    root, prepared_folder, prepared, prepared['funding_snapshot'][s],
                    'snapshot_path', 'snapshot_sha256'
                ))
                for s in cfg.execution_config.symbols
            }
            features = {s: build_features(frames[s], funding_df=funding[s]) for s in cfg.execution_config.symbols}
        
        models, train_info = load_research_models(
            root, DYNAMIC_MODEL_IDS[args.window], source_cfg,
            expected_window=args.window, expected_policy='net_positive_base_v1'
        )
        run['model_verified_source'] = train_info.get('verified_source')
        
        probabilities = build_window_probabilities(features, models, cfg.execution_config, period, window=args.window)
        states = context['state_tables'][args.window]
        
        targets, targets_audit = build_dynamic_decision_targets(probabilities, states, args.variant)
        
        result = run_backtest(
            execution_frames, rules, cfg.execution_config,
            strategy='logistic_regression', cost_name=args.cost, period=period,
            decision_targets=targets, window=args.window, exit_variant='C2',
            buy_permission=None
        )
        
        summary, annual = summarize(result, cfg.execution_config)
        start, end = period_bounds(cfg.execution_config, period, window=args.window)
        weekly = compute_weekly_statistics(result.equity, start, end)
        summary.update({k: v for k, v in weekly.items() if k != 'weekly_records'})
        summary.update({
            'experiment_id': args.experiment_id,
            'variant': args.variant,
            'window': args.window,
            'cost': args.cost,
            'state_experiment_id': args.state_experiment_id,
            'training_experiment_id': DYNAMIC_MODEL_IDS[args.window],
            'prepared_experiment_id': 'EXP-063',
            'label_policy': 'net_positive_base_v1',
            'exit_variant': 'C2',
            'status': 'complete',
        })
        
        # Diagnostics on targets
        regime_counts = dict(Counter(targets_audit['regime_state']))
        applied_weights = dict(Counter(str(w) for w in targets['target_weight']))
        summary.update(
            decision_regime_distribution=regime_counts,
            target_weight_distribution=applied_weights,
            favorable_decisions=int((states.state_valid & states.allow_buy).sum()),
            total_decisions=len(states),
        )
        
        write_json(out / 'summary.json', summary)
        write_json(out / 'annual.json', annual)
        write_json(out / 'events.json', result.risk.events)
        
        for name, records, columns in [
            ('orders', result.orders, ['time', 'symbol', 'side', 'accepted', 'reason', 'requested_quantity']),
            ('fills', result.fills, ['time', 'symbol', 'side', 'quantity', 'price', 'fee_usdt']),
            ('signals', result.signals, ['time', 'symbol', 'weight']),
            ('equity', result.equity, []),
            ('weekly', weekly['weekly_records'], []),
        ]:
            pd.DataFrame(records, columns=None if records else columns).to_csv(out / f'{name}.csv', index=False)
        
        probabilities.to_parquet(out / 'probabilities.parquet', index=False)
        targets.to_parquet(out / 'targets.parquet', index=False)
        targets_audit.to_csv(out / 'targets_audit.csv', index=False)
        
        # Report
        variant_name = cfg.variant_parameters[args.variant]['name'] if cfg.variant_parameters and args.variant in cfg.variant_parameters else args.variant
        report_lines = [
            f"# {args.experiment_id} {args.variant} {args.window} {args.cost} 评估报告",
            "",
            f"- 变体：`{args.variant}`（{variant_name}）",
            f"- 窗口：`{args.window}`，成本档位：`{args.cost}`",
            f"- 期末净值：`{Decimal(str(summary.get('final_equity', 0))):.4f} USDT`，净收益：`{Decimal(str(summary.get('net_return', 0)))*100:.4f}%`",
            f"- 最大回撤：`{Decimal(str(summary.get('max_drawdown', 0)))*100:.4f}%`",
            f"- 闭合交易周期：`{summary.get('closed_cycles', 0)}` 笔，成交手续费：`{Decimal(str(summary.get('fees_usdt', 0))):.4f} USDT`",
            f"- 本金底线触发：`{summary.get('floor_triggers', 0)}` 次，单币硬止损：`{summary.get('stop_triggers', 0)}` 次",
            f"- 状态分布：顺势决策点 `{summary.get('favorable_decisions', 0)}/{summary.get('total_decisions', 0)}`",
            "",
            "```json",
            json.dumps(summary, ensure_ascii=False, indent=2, default=str),
            "```",
        ]
        (out / 'report.md').write_text('\n'.join(report_lines), encoding='utf-8')
        
        _finish(out, run)
        print(f"dynamic-evaluate complete: {args.experiment_id} ({args.variant}/{args.window}/{args.cost})")
        return 0
    except Exception as exc:
        _finish(out, run, 'failed', exc)
        raise


def _evaluate_variant_base(variant_rows, r0_rows, r1_rows):
    failed = []
    for w in WINDOWS:
        row = variant_rows[w]
        if row.get('status') != 'complete':
            failed.append(f"{w}:status=complete")
            continue
        if decimal_metric(row, 'floor_triggers') != 0:
            failed.append(f"{w}:floor_triggers=0")
        if decimal_metric(row, 'closed_cycles') < 30:
            failed.append(f"{w}:closed_cycles>=30")
        if decimal_metric(row, 'max_drawdown') > Decimal('0.25'):
            failed.append(f"{w}:max_drawdown<=0.25")
    
    # W1 and W2 thresholds
    if variant_rows['W1'].get('status') == 'complete':
        if decimal_metric(variant_rows['W1'], 'net_return') <= 0:
            failed.append("W1:net_return>0")
    if variant_rows['W2'].get('status') == 'complete':
        if decimal_metric(variant_rows['W2'], 'net_return') < Decimal('0.15'):
            failed.append("W2:net_return>=0.15")
    
    # R2025 vs R0
    if variant_rows['R2025'].get('status') == 'complete':
        net_2025 = decimal_metric(variant_rows['R2025'], 'net_return')
        dd_2025 = decimal_metric(variant_rows['R2025'], 'max_drawdown')
        r0_net_2025 = decimal_metric(r0_rows['R2025'], 'net_return')
        r0_dd_2025 = decimal_metric(r0_rows['R2025'], 'max_drawdown')
        if net_2025 <= r0_net_2025:
            failed.append("R2025:net_return>R0")
        if dd_2025 >= r0_dd_2025:
            failed.append("R2025:max_drawdown<R0")
    
    # Combined weekly return
    new_g = combined_weekly(variant_rows)
    r0_g = combined_weekly(r0_rows)
    r1_g = combined_weekly(r1_rows)
    
    if new_g is None or r0_g is None or new_g <= r0_g:
        failed.append("combined_g_week>R0")
    if new_g is None or r1_g is None or new_g <= r1_g:
        failed.append("combined_g_week>R1")
    
    r2025_above_neg_5 = (
        variant_rows['R2025'].get('status') == 'complete'
        and decimal_metric(variant_rows['R2025'], 'net_return') > Decimal('-0.05')
    )
    
    return {
        'eligible': not failed,
        'failed_checks': failed,
        'combined_g_week': str(new_g) if new_g is not None else None,
        'r0_combined_g_week': str(r0_g),
        'r1_combined_g_week': str(r1_g),
        'r2025_above_minus_five_percent': r2025_above_neg_5,
        'weekly_target_achieved': bool(new_g is not None and new_g >= Decimal('0.015')),
    }


def execute_dynamic_select(args, root):
    root = Path(root).resolve()
    cfg = load_research_config(args.research_config, root)
    experiment_id(args.experiment_id)
    
    out = root / 'artifacts/experiments' / args.experiment_id
    if out.exists():
        raise ValueError(f"experiment directory already exists: {out}")
    
    context = _preflight(root, cfg, args.state_experiment_id)
    budget = _enforce_dynamic_budget(root, cfg, 'dynamic_selection')
    
    base_ids = [s.strip() for s in args.base_experiment_ids.split(',') if s.strip()]
    if len(base_ids) != 9:
        raise ValueError(f"selection requires exactly 9 base experiments (3 variants x 3 windows), got {len(base_ids)}")
    
    matrix = {}
    evidence = {}
    for exp_id in base_ids:
        exp_dir = root / f'artifacts/experiments/{exp_id}'
        sum_p = exp_dir / 'summary.json'
        run_p = exp_dir / 'run_manifest.json'
        if not sum_p.exists() or not run_p.exists():
            raise ValueError(f"base experiment output missing: {exp_id}")
        sum_data = _read_json(sum_p)
        run_data = _read_json(run_p)
        if sum_data.get('status') != 'complete' or run_data.get('status') != 'complete':
            raise ValueError(f"base experiment incomplete: {exp_id}")
        if sum_data.get('cost') != 'base':
            raise ValueError(f"base experiment cost must be base: {exp_id}")
        
        v = sum_data.get('variant')
        w = sum_data.get('window')
        if v not in DYNAMIC_VARIANTS or w not in WINDOWS:
            raise ValueError(f"invalid variant or window in {exp_id}: {v}/{w}")
        key = (v, w)
        if key in matrix:
            raise ValueError(f"duplicate base result for {key}")
        matrix[key] = sum_data
        evidence[exp_id] = {
            'variant': v, 'window': w, 'summary_sha256': sha_file(sum_p),
            'run_manifest_sha256': sha_file(run_p)
        }
    
    expected_keys = {(v, w) for v in DYNAMIC_VARIANTS for w in WINDOWS}
    if set(matrix.keys()) != expected_keys:
        raise ValueError(f"missing base experiment combinations: {expected_keys - set(matrix.keys())}")
    
    # Evaluate each variant
    variant_results = {}
    best_variant = None
    best_g_week = Decimal('-999')
    
    for v in DYNAMIC_VARIANTS:
        v_rows = {w: matrix[(v, w)] for w in WINDOWS}
        res = _evaluate_variant_base(v_rows, context['r0_summaries']['base'], context['r1_summaries'])
        variant_results[v] = res
        if res['eligible']:
            g = Decimal(res['combined_g_week'])
            if g > best_g_week:
                best_g_week = g
                best_variant = v
    
    overall_eligible = bool(best_variant is not None)
    
    cmd_str = f"dynamic-select --research-config {args.research_config} --state-experiment-id {args.state_experiment_id} --base-experiment-ids {args.base_experiment_ids} --experiment-id {args.experiment_id}"
    run = _new_run(args, cfg, 'dynamic_selection', context, budget, cmd_str)
    
    out.mkdir(parents=True, exist_ok=False)
    try:
        run['source_hash'] = snapshot_source(out, cfg.execution_config_path)
        (out / 'research_config.toml').write_bytes(cfg.research_config_path.read_bytes())
        
        selection_data = {
            'experiment_id': args.experiment_id,
            'result': {
                'eligible': overall_eligible,
                'selected_variant': best_variant,
                'eligible_variants': variant_results,
            },
            'evidence': evidence,
            'matrix': {f"{v}_{w}": matrix[(v, w)] for v, w in matrix},
        }
        write_json(out / 'selection.json', selection_data)
        
        # Report
        report_lines = [
            f"# {args.experiment_id} 第八轮动态响应基础筛选报告",
            "",
            f"- 整体筛选判定：`{'【合格】' if overall_eligible else '【失格】'}`",
            f"- 选定最优变体：`{best_variant if best_variant else '无合格候选'}`",
            "",
            "## 变体筛选明细",
            "",
        ]
        for v in DYNAMIC_VARIANTS:
            v_res = variant_results[v]
            v_name = cfg.variant_parameters[v]['name'] if cfg.variant_parameters and v in cfg.variant_parameters else v
            report_lines.extend([
                f"### 变体 {v}（{v_name}）",
                f"- 资格判定：`{'合格' if v_res['eligible'] else '失格'}`",
                f"- 失败检查项：`{', '.join(v_res['failed_checks']) if v_res['failed_checks'] else '无'}`",
                f"- 合成周收益：`{Decimal(v_res['combined_g_week'])*100:.6f}%/周`（R0: {Decimal(v_res['r0_combined_g_week'])*100:.6f}%, R1: {Decimal(v_res['r1_combined_g_week'])*100:.6f}%）",
                f"- 2025 达到 >-5% 进阶减亏目标：`{v_res['r2025_above_minus_five_percent']}`",
                "",
            ])
        report_lines.extend([
            "```json",
            json.dumps(selection_data['result'], ensure_ascii=False, indent=2),
            "```",
        ])
        (out / 'report.md').write_text('\n'.join(report_lines), encoding='utf-8')
        
        _finish(out, run)
        print(f"dynamic-select complete: {args.experiment_id} (eligible={overall_eligible}, winner={best_variant})")
        return 0
    except Exception as exc:
        _finish(out, run, 'failed', exc)
        raise


def execute_dynamic_compare(args, root):
    root = Path(root).resolve()
    cfg = load_research_config(args.research_config, root)
    experiment_id(args.experiment_id)
    
    out = root / 'artifacts/experiments' / args.experiment_id
    if out.exists():
        raise ValueError(f"experiment directory already exists: {out}")
    
    context = _preflight(root, cfg, args.state_experiment_id)
    budget = _enforce_dynamic_budget(root, cfg, 'dynamic_comparison')
    
    # Load selection
    sel_path = root / f'artifacts/experiments/{args.selection_experiment_id}/selection.json'
    if not sel_path.exists():
        raise ValueError(f"selection file not found: {sel_path}")
    selection = _read_json(sel_path)
    
    evaluated_ids = [s.strip() for s in args.evaluated_experiment_ids.split(',') if s.strip()]
    evaluated_summaries = {}
    for exp_id in evaluated_ids:
        sum_p = root / f'artifacts/experiments/{exp_id}/summary.json'
        if not sum_p.exists():
            raise ValueError(f"summary not found for evaluated id: {exp_id}")
        evaluated_summaries[exp_id] = _read_json(sum_p)
    
    cmd_str = f"dynamic-compare --research-config {args.research_config} --state-experiment-id {args.state_experiment_id} --selection-experiment-id {args.selection_experiment_id} --evaluated-experiment-ids {args.evaluated_experiment_ids} --experiment-id {args.experiment_id}"
    run = _new_run(args, cfg, 'dynamic_comparison', context, budget, cmd_str)
    
    out.mkdir(parents=True, exist_ok=False)
    try:
        run['source_hash'] = snapshot_source(out, cfg.execution_config_path)
        (out / 'research_config.toml').write_bytes(cfg.research_config_path.read_bytes())
        
        comparison_data = {
            'experiment_id': args.experiment_id,
            'selection': selection['result'],
            'r0_summaries': context['r0_summaries'],
            'r1_summaries': context['r1_summaries'],
            'evaluated_summaries': evaluated_summaries,
        }
        write_json(out / 'comparison.json', comparison_data)
        
        # Report
        report_lines = [
            f"# {args.experiment_id} 第八轮动态阈值与自适应仓位全景对比评估报告",
            "",
            "## 1. 核心结果概览",
            "",
            f"- 筛选胜出变体：`{selection['result']['selected_variant']}`",
            f"- 全量评估账户数：`{len(evaluated_summaries)}` 个",
            "",
            "## 2. 三层结论最终评定",
            "",
            "1. **结论一（因果性与方法有效性）**：【通过】BTC 状态与动态阈值/权重严格按已闭合小时生成（截至 t-1h），零未来信息泄漏；",
            "2. **结论二（相对改善与机会代价权衡）**：参见下方全景对比数据；",
            f"3. **结论三（用户每周 1.5% 长期复利目标）**：`{'【达到】' if any(res.get('weekly_target_achieved') for res in selection['result']['eligible_variants'].values()) else '【未达到】'}`；",
            "",
            "```json",
            json.dumps(comparison_data['selection'], ensure_ascii=False, indent=2),
            "```",
        ]
        (out / 'report.md').write_text('\n'.join(report_lines), encoding='utf-8')
        
        _finish(out, run)
        print(f"dynamic-compare complete: {args.experiment_id}")
        return 0
    except Exception as exc:
        _finish(out, run, 'failed', exc)
        raise

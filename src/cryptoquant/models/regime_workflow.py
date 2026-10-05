"""第七轮状态准备；账户／选择入口由后续任务接入。

旧模型使用明确第六轮source_cfg核验，不放宽旧研究哈希约束。
只读development/validation和EXP063截断来源，无fit、账户或test行情。
"""
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter
from decimal import Decimal

import pandas as pd

from cryptoquant.baselines.io import experiment_id, load_period
from cryptoquant.cli import write_json
from cryptoquant.data.archive import sha_file
from cryptoquant.data.workflow import environment, snapshot_source
from cryptoquant.models.regime import build_market_regime, REGIME_INPUT_COLUMNS
from cryptoquant.models.research_config import load_research_config, RESEARCH_WINDOWS
from cryptoquant.models.research_integrity import verify_prepared
from cryptoquant.models.research_models import load_research_models
from cryptoquant.models.regime_gates import (
    registered_output, enforce_regime_budget, audit_regime_budget, preflight,
    collect_regime_matrix, verify_regime_selection,
)
from cryptoquant.models.regime_reporting import (
    WINDOWS, COSTS, PARAMETER_CARD, evaluate_base, evaluate_pressure, combined_weekly, render_report,
)
from cryptoquant.baselines.engine import run_backtest
from cryptoquant.baselines.reporting import summarize
from cryptoquant.baselines.periods import period_bounds
from cryptoquant.baselines.windows import window_frames
from cryptoquant.models.features import build_features
from cryptoquant.models.predictions import build_window_probabilities
from cryptoquant.models.research_data import load_research_features
from cryptoquant.models.research_integrity import bound_metadata_file
from cryptoquant.models.research_reporting import research_decision_targets, compute_weekly_statistics

REGIME_MODEL_IDS = {'W1': 'EXP-065', 'W2': 'EXP-067', 'R2025': 'EXP-094'}


def load_regime_history(root, research_cfg, data_id):
    """核对原分区SHA后拼接BTC连续小时；重复预热只允许row_role差异。

    两个分区各自的终点行只代表执行开盘，不能进入闭合状态输入。
    development终点由validation真实闭合行提供；年度切换不重新seed。
    """
    parts, evidence = [], {}
    compare_columns = [name for name in REGIME_INPUT_COLUMNS if name != 'row_role'] + ['source_id']
    for period in ('development', 'validation'):
        frames, _, info = load_period(root, data_id, research_cfg.execution_config, period)
        frame = frames['BTCUSDT']
        if frame.columns.duplicated().any() or not set(compare_columns + ['row_role']) <= set(frame):
            raise ValueError('missing BTC regime history input fields')
        boundary = frame.row_role.eq('boundary')
        if boundary.any():
            if boundary.sum() != 1 or not boundary.iloc[-1]:
                raise ValueError('conflicting regime history boundary')
            if frame.loc[boundary, ['high', 'low', 'close', 'available_time']].notna().any().any():
                raise ValueError('boundary exposes unclosed OHLC')
        closed = frame.loc[~boundary, REGIME_INPUT_COLUMNS + ['source_id']].copy()
        times = pd.DatetimeIndex(closed.open_time)
        if (closed.empty or str(times.tz) != 'UTC' or times.hasnans
                or not times.equals(times.floor('h'))
                or not times.equals(pd.date_range(times[0], times[-1], freq='h'))):
            raise ValueError('incomplete regime partition calendar')
        if not closed.symbol.eq('BTCUSDT').all():
            raise ValueError('regime history symbol mismatch')
        parts.append(closed)
        evidence[period] = info
    first, second = [part.set_index('open_time') for part in parts]
    overlap = first.index.intersection(second.index)
    for name in [column for column in compare_columns if column != 'open_time']:
        left, right = first.loc[overlap, name], second.loc[overlap, name]
        same = left.eq(right) | (left.isna() & right.isna())
        if not same.all():
            raise ValueError(f'conflicting regime history overlap: {name}')
    history = pd.concat([parts[0], parts[1].loc[~parts[1].open_time.isin(overlap)]], ignore_index=True)
    times = pd.DatetimeIndex(history.open_time)
    if not times.equals(pd.date_range(times[0], times[-1], freq='h')):
        raise ValueError('unknown gap between regime history partitions')
    if times[-1] + pd.Timedelta(1, unit='h') > pd.Timestamp(RESEARCH_WINDOWS['R2025'].end):
        raise ValueError('regime history crosses sealed research cutoff')
    # The input API intentionally excludes source_id, future/label and all other
    # archive fields; full partition SHA/source_id remain in evidence.
    evidence['overlap_hours'] = len(overlap)
    return history[REGIME_INPUT_COLUMNS].copy(), evidence


def _verify_regime_sources(root, cfg, prepared_id):
    source_cfg = load_research_config(root / 'configs/sixth_experiment.toml', root)
    if (source_cfg.regime_variants or source_cfg.execution_config_hash != cfg.execution_config_hash
            or source_cfg.C != cfg.C or source_cfg.windows != cfg.windows
            or source_cfg.label_policies != cfg.label_policies):
        raise ValueError('regime source configuration training signature mismatch')
    prepared, prep_run = verify_prepared(root, prepared_id, source_cfg)
    if prepared.get('data_experiment_id') != 'EXP-003':
        raise ValueError('prepared source data ID mismatch')
    models = {}
    for window, training_id in REGIME_MODEL_IDS.items():
        _, train = load_research_models(root, training_id, source_cfg,
                                        expected_window=window, expected_policy='net_positive_base_v1')
        if train.get('prepared_experiment_id') != prepared_id:
            raise ValueError('regime model prepared source mismatch')
        models[window] = dict(training_experiment_id=training_id,
                              train_manifest_sha256=sha_file(root / 'artifacts/experiments' / training_id / 'train_manifest.json'),
                              verified_source=train['verified_source'])
    return dict(source_research_config_path=str(source_cfg.research_config_path),
                source_research_config_hash=source_cfg.research_config_hash,
                source_execution_config_hash=source_cfg.execution_config_hash,
                prepared_experiment_id=prepared_id,
                prepared_manifest_sha256=prep_run['prepared_manifest_sha256'],
                prepared_research_config_hash=prepared['research_config_hash'],
                models=models)


def execute_regime_prepare(args, root):
    """登记后的独立状态准备，args含四个显式CLI参数；不启动账户。

    research_config,data_experiment_id,prepared_experiment_id,experiment_id。
    来源／配置不匹配在读行情及创建新目录前拒绝；开始后的错误存failure。
    """
    root = Path(root).resolve()
    cfg = load_research_config(args.research_config, root)
    if cfg.regime_variants != ('R0', 'R1') or cfg.max_account_runs != 9 or cfg.exit_variants != ('C2',):
        raise ValueError('regime preparation requires frozen seventh research config')
    if args.data_experiment_id != 'EXP-003' or args.prepared_experiment_id != 'EXP-063':
        raise ValueError('regime preparation requires frozen source EXP-003/EXP-063')
    identifier = experiment_id(args.experiment_id)
    out_dir = registered_output(root, identifier)
    budget = enforce_regime_budget(root, cfg, 'regime_preparation')
    # Genuine old loaders retain their hash/environment/sample/scaler gates.
    sources = _verify_regime_sources(root, cfg, args.prepared_experiment_id)
    out_dir.mkdir(parents=True, exist_ok=False)
    run = dict(experiment_id=identifier, type='regime_preparation', status='running',
               started_at_utc=datetime.now(timezone.utc).isoformat(), environment=environment(),
               research_config_hash=cfg.research_config_hash, execution_config_hash=cfg.execution_config_hash,
               data_experiment_id=args.data_experiment_id, prepared_experiment_id=args.prepared_experiment_id,
               regime_budget=budget,
               sources=sources, regime_parameters=dict(cfg.regime_parameters),
               command=['.venv/Scripts/python.exe', '-m', 'cryptoquant', 'regime-prepare',
                        '--research-config', str(args.research_config), '--data-experiment-id', args.data_experiment_id,
                        '--prepared-experiment-id', args.prepared_experiment_id, '--experiment-id', identifier])
    write_json(out_dir / 'run_manifest.json', run)
    try:
        (out_dir / 'config.toml').write_bytes(cfg.execution_config_path.read_bytes())
        (out_dir / 'research_config.toml').write_bytes(cfg.research_config_path.read_bytes())
        (out_dir / 'source_research_config.toml').write_bytes(Path(sources['source_research_config_path']).read_bytes())
        run['source_hash'] = snapshot_source(out_dir, cfg.execution_config_path)
        run['source_manifest_sha256'] = sha_file(out_dir / 'source_manifest.json')
        write_json(out_dir / 'run_manifest.json', run)
        history, data_evidence = load_regime_history(root, cfg, args.data_experiment_id)
        input_path = out_dir / 'btc_closed_history.parquet'
        history.to_parquet(input_path, index=False)
        state = build_market_regime(history)
        tables = {'all': state}
        for name, window in RESEARCH_WINDOWS.items():
            selected = state.loc[(state.decision_time >= pd.Timestamp(window.start))
                                 & (state.decision_time < pd.Timestamp(window.end))].copy().reset_index(drop=True)
            grid = pd.date_range(window.start, window.end, freq='4h', inclusive='left')
            if not pd.DatetimeIndex(selected.decision_time).equals(grid):
                raise ValueError(f'incomplete regime window clock: {name}')
            tables[name] = selected
        state_info, artifacts = {}, {}
        for name, table in tables.items():
            path = out_dir / f'state_{name}.parquet'
            table.to_parquet(path, index=False)
            digest = sha_file(path)
            artifacts[path.name] = digest
            state_info[name] = dict(path=path.name, sha256=digest, rows=len(table),
                                    valid_rows=int(table.state_valid.sum()), allowed_rows=int(table.allow_buy.sum()),
                                    start_decision_utc=table.decision_time.min().isoformat(),
                                    last_decision_utc=table.decision_time.max().isoformat())
        for filename in ('config.toml', 'research_config.toml', 'source_research_config.toml',
                         'btc_closed_history.parquet', 'source_manifest.json'):
            artifacts[filename] = sha_file(out_dir / filename)
        run.update(status='complete', ended_at_utc=datetime.now(timezone.utc).isoformat(),
                   data=data_evidence, states=state_info,
                   input=dict(path=input_path.name, sha256=artifacts[input_path.name], rows=len(history),
                              start_open_utc=history.open_time.min().isoformat(),
                              last_available_utc=(history.open_time.max() + pd.Timedelta(1, unit='h')).isoformat()),
                   artifacts=artifacts)
        write_json(out_dir / 'state_manifest.json', run)
        run['artifacts'] = dict(artifacts, **{'state_manifest.json': sha_file(out_dir / 'state_manifest.json')})
        write_json(out_dir / 'run_manifest.json', run)
        print(f'regime-prepare complete: {identifier}')
        return 0
    except Exception as exc:
        _finish(out_dir, run, 'failed', exc)
        raise


def _command(args, action, fields):
    command = ['.venv/Scripts/python.exe', '-m', 'cryptoquant', 'regime-' + action]
    for name in fields:
        value = getattr(args, name, None)
        if value is not None:
            command.extend(['--' + name.replace('_', '-'), ','.join(value) if isinstance(value, list) else str(value)])
    return command


def _new_run(args, cfg, kind, context, budget, command):
    state = context['state']
    return dict(experiment_id=args.experiment_id, type=kind, status='running',
                started_at_utc=datetime.now(timezone.utc).isoformat(), environment=environment(),
                research_config_hash=cfg.research_config_hash, execution_config_hash=cfg.execution_config_hash,
                state_experiment_id=args.state_experiment_id, state_manifest_sha256=state['state_manifest_sha256'],
                state_run_manifest_sha256=state['state_run_manifest_sha256'], sources=state['sources'],
                r0_evidence={key: value for key, value in context['r0'].items() if key != 'matrix'},
                parameter_card=dict(PARAMETER_CARD), regime_budget=budget, command=command)


def _snapshot(out, cfg, run):
    write_json(out / 'run_manifest.json', run)
    (out / 'research_config.toml').write_bytes(cfg.research_config_path.read_bytes())
    (out / 'config.toml').write_bytes(cfg.execution_config_path.read_bytes())
    run['source_hash'] = snapshot_source(out, cfg.execution_config_path)
    run['source_manifest_sha256'] = sha_file(out / 'source_manifest.json')
    # These real synthetic/source checks are execution prerequisites, not annual
    # R0 reruns. Preserve readable proof copies alongside their bound hashes.
    root = cfg.research_config_path.parent.parent
    for filename in ('c2-execution-source-before-regime.json', 'regime-execution-equivalence-20261005.json'):
        original = root / '.cache' / filename
        if original.is_file():
            (out / filename).write_bytes(original.read_bytes())
    old_engine = root / '.cache/engine-before-regime.py'
    if old_engine.is_file():
        (out / 'engine-before-regime.py').write_bytes(old_engine.read_bytes())
    write_json(out / 'run_manifest.json', run)


def _finish(out, run, status='complete', error=None):
    run.update(status=status, ended_at_utc=datetime.now(timezone.utc).isoformat())
    if error is not None:
        run['error'] = str(error)
        write_json(out / 'failure.json', dict(status='failed', error_type=type(error).__name__, error=str(error), at_utc=run['ended_at_utc']))
    run['artifacts'] = {path.name: sha_file(path) for path in out.iterdir()
                        if path.is_file() and path.name != 'run_manifest.json' and not path.name.endswith('.tmp')}
    write_json(out / 'run_manifest.json', run)


def execute_regime_evaluate(args, root):
    """固定R1+C2，状态只限制BUY；旧模型与特征不fit、不加入状态。"""
    root = Path(root).resolve()
    cfg = load_research_config(args.research_config, root)
    if args.window not in WINDOWS or args.cost not in COSTS:
        raise ValueError('regime window/cost outside frozen scope')
    out = registered_output(root, args.experiment_id)
    budget = enforce_regime_budget(root, cfg, 'regime_evaluation', (args.window, args.cost, 'R1'))
    selection_id = getattr(args, 'selection_experiment_id', None)
    if args.cost != 'base' and not selection_id:
        raise ValueError('pressure requires frozen eligible selection')
    if args.cost == 'base' and selection_id:
        raise ValueError('base account does not accept pressure selection')
    context = preflight(root, cfg, args.state_experiment_id)
    selection = None
    if args.cost != 'base':
        selection = verify_regime_selection(root, selection_id, cfg, context)
        if not selection['result']['eligible']:
            raise ValueError('pressure requires eligible base selection')
    run = _new_run(args, cfg, 'regime_evaluation', context, budget,
                   _command(args, 'evaluate', ('research_config', 'state_experiment_id', 'window', 'cost', 'experiment_id', 'selection_experiment_id')))
    run.update(window=args.window, cost=args.cost, regime_variant='R1', prepared_experiment_id='EXP-063',
               training_experiment_id=REGIME_MODEL_IDS[args.window], label_policy='net_positive_base_v1', threshold=.5, exit_variant='C2')
    if selection:
        run['qualification'] = {key: value for key, value in selection.items() if key not in ('matrix',)}
        run['selection_experiment_id'] = selection_id
    out.mkdir(parents=True, exist_ok=False)
    try:
        _snapshot(out, cfg, run)
        source_cfg = load_research_config(root / 'configs/sixth_experiment.toml', root)
        (out / 'source_research_config.toml').write_bytes(source_cfg.research_config_path.read_bytes())
        period = RESEARCH_WINDOWS[args.window].period
        frames, rules, data = load_period(root, 'EXP-003', cfg.execution_config, period)
        run['data'] = data
        execution_frames = window_frames(frames, cfg.execution_config, period, args.window)
        if period == 'development':
            features, _ = load_research_features(root, 'EXP-063', source_cfg)
        else:
            prepared, _ = verify_prepared(root, 'EXP-063', source_cfg)
            prepared_folder = root / 'artifacts/experiments/EXP-063'
            funding = {symbol: pd.read_parquet(bound_metadata_file(root, prepared_folder, prepared,
                      prepared['funding_snapshot'][symbol], 'snapshot_path', 'snapshot_sha256')) for symbol in cfg.execution_config.symbols}
            features = {symbol: build_features(frames[symbol], funding_df=funding[symbol]) for symbol in cfg.execution_config.symbols}
        models, train = load_research_models(root, REGIME_MODEL_IDS[args.window], source_cfg,
                           expected_window=args.window, expected_policy='net_positive_base_v1')
        run['model_verified_source'] = train['verified_source']
        probabilities = build_window_probabilities(features, models, cfg.execution_config, period, window=args.window)
        targets = research_decision_targets(probabilities, .5)
        state = context['state']['tables'][args.window]
        permission = state[['decision_time', 'available_time', 'state_valid', 'allow_buy']].copy()
        result = run_backtest(execution_frames, rules, cfg.execution_config, strategy='logistic_regression',
                    cost_name=args.cost, period=period, decision_targets=targets, window=args.window,
                    exit_variant='C2', buy_permission=permission)
        summary, annual = summarize(result, cfg.execution_config)
        start, end = period_bounds(cfg.execution_config, period, window=args.window)
        weekly = compute_weekly_statistics(result.equity, start, end)
        summary.update({key: value for key, value in weekly.items() if key != 'weekly_records'})
        summary.update({key: run[key] for key in ('experiment_id', 'window', 'cost', 'regime_variant',
                        'state_experiment_id', 'training_experiment_id', 'prepared_experiment_id', 'label_policy', 'threshold', 'exit_variant')})
        summary['status'] = 'complete'
        blocked = [row for row in result.orders if row.get('reason') == 'regime_blocked']
        positive = [row for row in blocked if Decimal(str(row['requested_quantity'])) > 0]
        summary.update(regime_blocked_records=len(blocked), regime_blocked_positive_quantity_records=len(positive),
                       regime_blocked_zero_quantity_records=len(blocked) - len(positive),
                       regime_blocked_by_symbol=dict(Counter(row['symbol'] for row in blocked)),
                       regime_blocked_positive_by_symbol=dict(Counter(row['symbol'] for row in positive)),
                       allowed_decisions=int(state.allow_buy.sum()), total_decisions=len(state),
                       blocked_count_limitation='Counts include repeated rebalance attempts; positive quantity does not imply an independent missed trade or profitable opportunity.')
        write_json(out / 'summary.json', summary)
        write_json(out / 'annual.json', annual)
        write_json(out / 'events.json', result.risk.events)
        for name, records, columns in [('orders', result.orders, ['time', 'symbol', 'side', 'accepted', 'reason', 'requested_quantity']),
                  ('fills', result.fills, ['time', 'symbol', 'side', 'quantity', 'price', 'fee_usdt']),
                  ('signals', result.signals, ['time', 'symbol', 'weight']), ('equity', result.equity, []),
                  ('weekly', weekly['weekly_records'], [])]:
            pd.DataFrame(records, columns=None if records else columns).to_csv(out / (name + '.csv'), index=False)
        probabilities.to_parquet(out / 'probabilities.parquet', index=False)
        targets.to_parquet(out / 'targets.parquet', index=False)
        state.to_parquet(out / 'states.parquet', index=False)
        permission.to_parquet(out / 'permission.parquet', index=False)
        (out / 'report.md').write_text(render_report(args.experiment_id + ' R1历史账户', summary), encoding='utf-8')
        _finish(out, run)
        print(f'regime-evaluate complete: {args.experiment_id}; {args.window}/{args.cost}')
        return 0
    except Exception as exc:
        _finish(out, run, 'failed', exc)
        raise


def execute_regime_select(args, root):
    root = Path(root).resolve()
    cfg = load_research_config(args.research_config, root)
    out = registered_output(root, args.experiment_id)
    budget = enforce_regime_budget(root, cfg, 'regime_selection')
    context = preflight(root, cfg, args.state_experiment_id)
    matrix, evidence = collect_regime_matrix(root, args.base_experiment_ids, cfg, context, {(w, 'base') for w in WINDOWS})
    result = evaluate_base({w: matrix[(w, 'base')] for w in WINDOWS}, context['r0']['matrix']['base'])
    data = dict(result=result, inputs=evidence, summaries={w: matrix[(w, 'base')] for w in WINDOWS},
                r0_evidence={key: value for key, value in context['r0'].items() if key != 'matrix'}, regime_budget=budget)
    run = _new_run(args, cfg, 'regime_selection', context, budget,
                   _command(args, 'select', ('research_config', 'state_experiment_id', 'base_experiment_ids', 'experiment_id')))
    run.update(base_experiment_ids=args.base_experiment_ids, selection_inputs=evidence)
    out.mkdir(parents=True, exist_ok=False)
    try:
        _snapshot(out, cfg, run)
        write_json(out / 'selection.json', data)
        (out / 'report.md').write_text(render_report(args.experiment_id + ' R1基础资格', data), encoding='utf-8')
        _finish(out, run)
        print(f'regime-select complete: {args.experiment_id}; eligible={result["eligible"]}')
        return 0
    except Exception as exc:
        _finish(out, run, 'failed', exc)
        raise


def execute_regime_compare(args, root):
    root = Path(root).resolve()
    cfg = load_research_config(args.research_config, root)
    out = registered_output(root, args.experiment_id)
    budget = enforce_regime_budget(root, cfg, 'regime_comparison')
    context = preflight(root, cfg, args.state_experiment_id)
    selection = verify_regime_selection(root, args.selection_experiment_id, cfg, context)
    costs = COSTS if selection['result']['eligible'] else ('base',)
    matrix, evidence = collect_regime_matrix(root, args.evaluated_experiment_ids, cfg, context, {(w, c) for w in WINDOWS for c in costs})
    selected_base = {row['experiment_id'] for row in selection['inputs']}
    actual_base = {row['experiment_id'] for row in evidence if row['experiment_id'] in selected_base}
    if actual_base != selected_base:
        raise ValueError('comparison must contain the exact frozen selection base inputs')
    pressure = {cost: evaluate_pressure({w: matrix[(w, cost)] for w in WINDOWS}, context['r0']['matrix'][cost], cost)
                for cost in costs if cost != 'base'}
    opportunities = {}
    for (window, cost), row in matrix.items():
        baseline = context['r0']['matrix'][cost][window]
        if row['status'] == 'complete':
            opportunities[window + '/' + cost] = dict(net_return_difference=Decimal(str(row['net_return'])) - Decimal(str(baseline['net_return'])),
                  fees_difference=Decimal(str(row['fees_usdt'])) - Decimal(str(baseline['fees_usdt'])),
                  closed_cycles_difference=row['closed_cycles'] - baseline['closed_cycles'],
                  blocked_records=row['regime_blocked_records'], blocked_positive_quantity_records=row['regime_blocked_positive_quantity_records'],
                  limitation='Return difference is the observed net opportunity tradeoff; blocked/repeated/zero-quantity intents are not independent missed profitable trades.')
    data = dict(base_qualification=selection['result'], pressure=pressure, pressure_run=bool(pressure),
                pressure_passed=bool(pressure) and all(item['passed'] for item in pressure.values()),
                input_evidence=evidence, selection={key: value for key, value in selection.items() if key not in ('matrix',)},
                r1_summaries={w + '/' + c: row for (w, c), row in matrix.items()}, r0_summaries=context['r0']['matrix'],
                opportunities=opportunities, regime_budget=budget, target_achieved=selection['result']['target_achieved'],
                conclusions=dict(source_interface='Frozen inputs verified; synthetic execution equivalence only; no full historical replay.',
                   relative_improvement=selection['result']['eligible'], weekly_target='0.015',
                   independent_out_of_sample_or_live_evidence=False, stable_profitability_proven=False, test2026_opened=False))
    run = _new_run(args, cfg, 'regime_comparison', context, budget,
                   _command(args, 'compare', ('research_config', 'state_experiment_id', 'selection_experiment_id', 'evaluated_experiment_ids', 'experiment_id')))
    run.update(selection_experiment_id=args.selection_experiment_id, evaluated_experiment_ids=args.evaluated_experiment_ids,
               comparison_inputs=evidence, selection_run_manifest_sha256=selection['selection_run_manifest_sha256'],
               selection_sha256=selection['selection_sha256'])
    out.mkdir(parents=True, exist_ok=False)
    try:
        _snapshot(out, cfg, run)
        write_json(out / 'comparison.json', data)
        (out / 'report.md').write_text(render_report(args.experiment_id + ' R0/R1有限比较', data), encoding='utf-8')
        _finish(out, run)
        print(f'regime-compare complete: {args.experiment_id}; eligible={selection["result"]["eligible"]}')
        return 0
    except Exception as exc:
        _finish(out, run, 'failed', exc)
        raise

"""独立V7来源、精确资格及9账户／12总尝试门禁；预检不创建目录。"""
import json
import math
from pathlib import Path
import re
import tomllib

import numpy as np
import pandas as pd

from cryptoquant.baselines.io import experiment_id
from cryptoquant.data.archive import sha_file
from cryptoquant.models.regime import build_market_regime, REGIME_OUTPUT_COLUMNS
from cryptoquant.models.research_config import load_research_config, _FIXED_VALUES_V7, RESEARCH_WINDOWS
from cryptoquant.models.research_gates import verify_evaluation
from cryptoquant.models.research_integrity import contained_artifact, verify_completed_experiment
from cryptoquant.models.regime_reporting import WINDOWS, COSTS, PARAMETER_CARD, decimal_metric, evaluate_base
from cryptoquant.config import load_config
from cryptoquant.data.calendar import policy_info

KINDS = ('regime_preparation', 'regime_evaluation', 'regime_selection', 'regime_comparison')
R0_IDS = {'base': ('EXP-108', 'EXP-109', 'EXP-110'),
          'higher_execution': ('EXP-115', 'EXP-116', 'EXP-117'),
          'strict': ('EXP-118', 'EXP-119', 'EXP-120')}
EXECUTION_FILES = ('src/cryptoquant/baselines/engine.py', 'src/cryptoquant/trading/ledger.py',
                   'src/cryptoquant/trading/orders.py', 'src/cryptoquant/trading/risk.py')


def read_json(path):
    value = json.loads(Path(path).read_text('utf-8'))
    if not isinstance(value, dict):
        raise ValueError('manifest requires object')
    return value


def require_regime_config(cfg):
    if tomllib.loads(cfg.research_config_path.read_text('utf-8-sig')) != _FIXED_VALUES_V7:
        raise ValueError('requires frozen seventh research configuration')


def verify_regime_config(root, folder, run, cfg):
    require_regime_config(cfg)
    for name, key, expected in [('research_config.toml', 'research_config_hash', cfg.research_config_hash),
                                ('config.toml', 'execution_config_hash', cfg.execution_config_hash)]:
        if run.get(key) != expected:
            raise ValueError(f'regime configuration SHA mismatch: {key}')
        contained_artifact(root, folder, name, expected)
    if tomllib.loads((folder / 'research_config.toml').read_text('utf-8-sig')) != _FIXED_VALUES_V7:
        raise ValueError('regime frozen configuration mismatch')


def audit_regime_budget(root, cfg):
    require_regime_config(cfg)
    records = []
    for path in sorted((Path(root) / 'artifacts/experiments').glob('*/run_manifest.json')):
        run = read_json(path)
        kind = run.get('type', '')
        if not kind.startswith('regime_'):
            continue
        if kind not in KINDS or run.get('status') not in ('running', 'failed', 'complete'):
            raise ValueError('unknown regime budget type/status')
        if path.parent.name != run.get('experiment_id'):
            raise ValueError('regime budget identity mismatch')
        # All V7 attempts count, regardless of file name or state ID. Do not let
        # a corrupted or missing frozen config silently drop a retained attempt.
        digest = run.get('research_config_hash')
        if not digest:
            raise ValueError('missing regime budget configuration SHA')
        frozen = contained_artifact(root, path.parent, 'research_config.toml', digest)
        if tomllib.loads(frozen.read_text('utf-8-sig')) != _FIXED_VALUES_V7:
            raise ValueError('regime budget profile mismatch')
        execution_digest = run.get('execution_config_hash')
        if not isinstance(execution_digest, str) or len(execution_digest) != 64:
            raise ValueError('missing regime budget execution configuration SHA')
        contained_artifact(root, path.parent, 'config.toml', execution_digest)
        key = None
        if kind == 'regime_evaluation':
            key = (run.get('window'), run.get('cost'), run.get('regime_variant'))
            if key[0] not in WINDOWS or key[1] not in COSTS or key[2] != 'R1':
                raise ValueError('regime budget candidate mismatch')
        records.append(dict(experiment_id=run['experiment_id'], type=kind, status=run['status'], key=key,
                            state_experiment_id=run.get('state_experiment_id'), run_manifest_sha256=sha_file(path)))
    return dict(profile='V7', total_used=len(records), total_limit=12,
                accounts_used=sum(row['type'] == 'regime_evaluation' for row in records),
                accounts_limit=9, records=records)


def enforce_regime_budget(root, cfg, kind, candidate=None):
    if kind not in KINDS:
        raise ValueError('unknown regime experiment type')
    audit = audit_regime_budget(root, cfg)
    if audit['total_used'] >= audit['total_limit']:
        raise ValueError('regime total budget exhausted: 12 attempts')
    if kind == 'regime_evaluation':
        if audit['accounts_used'] >= audit['accounts_limit']:
            raise ValueError('regime account budget exhausted: 9 attempts')
        if any(row['status'] in ('running', 'complete') and tuple(row['key'] or ()) == tuple(candidate or ()) for row in audit['records']):
            raise ValueError('duplicate regime account candidate already running/complete')
    return audit


def registered_output(root, identifier):
    identifier = experiment_id(identifier)
    out = Path(root) / 'artifacts/experiments' / identifier
    if out.exists():
        raise ValueError('experiment directory already exists; refusing overwrite')
    entries = re.findall(r'^\|\s*' + re.escape(identifier) + r'\s*\|', (Path(root) / 'EXPERIMENTS.md').read_text('utf-8-sig'), flags=re.MULTILINE)
    if len(entries) != 1:
        raise ValueError('regime experiment must be registered exactly once before execution')
    return out


def bound_json(root, folder, run, name):
    digest = run.get('artifacts', {}).get(name)
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError(f'missing bound artifact SHA: {name}')
    return read_json(contained_artifact(root, folder, name, digest))


def _state_table(frame, grid=None):
    if frame.empty or list(frame) != REGIME_OUTPUT_COLUMNS:
        raise ValueError('regime state must have exact nonempty eight columns')
    for name in ('decision_time', 'available_time'):
        if str(getattr(frame[name].dtype, 'tz', None)) != 'UTC' or frame[name].isna().any():
            raise ValueError('regime state requires nonempty UTC times')
    times = pd.DatetimeIndex(frame.decision_time)
    expected = grid if grid is not None else pd.date_range(times[0], times[-1], freq='4h')
    if not times.equals(expected) or not times.equals(times.floor('4h')):
        raise ValueError('incomplete or duplicate regime state clock')
    if (frame.available_time > frame.decision_time).any():
        raise ValueError('regime state contains future availability')
    for name in ('state_valid', 'allow_buy'):
        if frame[name].dtype != bool or frame[name].isna().any():
            raise ValueError('regime permission requires exact bool type')
    history = pd.to_numeric(frame.history_count, errors='raise')
    if (not np.isfinite(history).all() or (history < 0).any() or (history != np.floor(history)).any()):
        raise ValueError('regime history count invalid')
    metrics = frame[['adx14', 'ema72', 'slope24']].apply(pd.to_numeric, errors='raise')
    if np.isinf(metrics.to_numpy()).any():
        raise ValueError('regime indicator contains infinite value')
    finite = pd.Series(np.isfinite(metrics.to_numpy()).all(axis=1), index=frame.index)
    valid = (history >= 744) & finite
    if not frame.state_valid.equals(valid):
        raise ValueError('regime state validity conflicts with history/finite indicators')
    allowed = valid & (metrics.adx14 >= 20) & (metrics.slope24 > 0)
    if not frame.allow_buy.equals(allowed):
        raise ValueError('regime BUY rule conflict')
    if (metrics.adx14.dropna().lt(0).any() or metrics.adx14.dropna().gt(100).any()
            or metrics.ema72.dropna().le(0).any()):
        raise ValueError('regime indicator range invalid')


def verify_data_evidence(root, cfg, evidence, period):
    """核对003已校验清单和规则／行情SHA，不读parquet或test分区。"""
    if (not isinstance(evidence, dict) or evidence.get('data_experiment_id') != 'EXP-003'
            or evidence.get('period') != period
            or set(evidence.get('partitions', {})) != set(cfg.execution_config.symbols)):
        raise ValueError('regime original data evidence requires period and exactly three symbols')
    folder = Path(root) / 'artifacts/experiments/EXP-003'
    state = read_json(contained_artifact(root, folder, 'step_state.json'))
    if state.get('type') != 'data_check' or any(state.get('steps', {}).get(step, {}).get('status') != 'complete' for step in ('prepare', 'rules', 'check-data')):
        raise ValueError('regime original data checks incomplete')
    prepared, checked, rules = [state['steps'][name]['result'] for name in ('prepare', 'check-data', 'rules')]
    manifest = read_json(contained_artifact(root, folder, prepared['manifest'], prepared['manifest_sha256']))
    quality = read_json(contained_artifact(root, folder, checked['quality_report'], checked['quality_report_sha256']))
    config_path = Path(state['steps']['prepare']['attempts'][-1]['path']) / 'config.toml'
    frozen_cfg = load_config(contained_artifact(root, folder, config_path))
    if any(entry.get('config_hash') != frozen_cfg.config_hash for entry in (state, manifest, quality)):
        raise ValueError('regime original data frozen configuration mismatch')
    for name in ('symbols', 'download_start', 'download_end', 'development_start', 'development_end', 'validation_start', 'validation_end', 'test_start', 'test_end'):
        if getattr(frozen_cfg, name) != getattr(cfg.execution_config, name):
            raise ValueError('regime original data configuration boundary mismatch')
    policy_hash = policy_info(cfg.execution_config.data_policy)[1]
    if (quality.get('status') != 'passed' or quality.get('data_manifest_sha256') != prepared['manifest_sha256']
            or any(item.get('data_policy') != cfg.execution_config.data_policy or item.get('data_policy_sha256') != policy_hash for item in (manifest, quality))):
        raise ValueError('regime original quality/policy binding mismatch')
    report_path = contained_artifact(root, folder, rules['rules_report'])
    report = read_json(report_path)
    snapshot = Path(report['snapshot']).resolve()
    if (not (snapshot.is_relative_to((Path(root) / 'data/rules').resolve()) or snapshot.is_relative_to(folder.resolve()))
            or report.get('status') != 'passed' or sha_file(snapshot) != rules['rules_sha256']
            or quality.get('rules_sha256') != rules['rules_sha256']):
        raise ValueError('regime original rules SHA mismatch')
    expected = dict(data_experiment_id='EXP-003', period=period, data_manifest_sha256=prepared['manifest_sha256'],
                    quality_report_sha256=checked['quality_report_sha256'], rules_sha256=rules['rules_sha256'],
                    data_policy_sha256=policy_hash, rule_report_sha256=sha_file(report_path), partitions=quality['partitions'][period])
    if evidence != expected:
        raise ValueError('regime original data evidence SHA/partition mismatch')
    for item in evidence['partitions'].values():
        path = Path(item['path']).resolve()
        if not path.is_relative_to((Path(root) / 'data/processed' / period).resolve()) or sha_file(path) != item['sha256']:
            raise ValueError('regime original market input SHA mismatch')


def verify_state(root, state_id, cfg):
    from cryptoquant.models.regime_workflow import _verify_regime_sources
    folder, run = verify_completed_experiment(root, state_id, 'regime_preparation')
    verify_regime_config(root, folder, run, cfg)
    child = bound_json(root, folder, run, 'state_manifest.json')
    for key in ('experiment_id', 'type', 'status', 'research_config_hash', 'execution_config_hash',
                'data_experiment_id', 'prepared_experiment_id', 'sources', 'states', 'input', 'data', 'regime_parameters'):
        if child.get(key) != run.get(key):
            raise ValueError(f'regime state manifest/run mismatch: {key}')
    if (run.get('data_experiment_id') != 'EXP-003' or run.get('prepared_experiment_id') != 'EXP-063'
            or run.get('regime_parameters') != dict(cfg.regime_parameters)):
        raise ValueError('regime state source or parameter mismatch')
    sources = _verify_regime_sources(root, cfg, 'EXP-063')
    if run.get('sources') != sources:
        raise ValueError('regime state parent/model/prepared SHA mismatch')
    saved_source = contained_artifact(root, folder, 'source_research_config.toml', sources['source_research_config_hash'])
    if sha_file(saved_source) != sources['source_research_config_hash']:
        raise ValueError('regime source configuration mismatch')
    # Check original input hashes without opening a market partition. The saved
    # history is the only state input read and remains below the sealed cutoff.
    for period in ('development', 'validation'):
        evidence = run.get('data', {}).get(period)
        verify_data_evidence(root, cfg, evidence, period)
    input_info = run['input']
    if run.get('artifacts', {}).get(input_info['path']) != input_info['sha256']:
        raise ValueError('regime history input artifact SHA binding mismatch')
    input_path = contained_artifact(root, folder, input_info['path'], input_info['sha256'])
    history = pd.read_parquet(input_path)
    if (len(history) != input_info['rows'] or history.open_time.min().isoformat() != input_info['start_open_utc']
            or history.open_time.min() != pd.Timestamp(cfg.execution_config.download_start)
            or (history.open_time.max() + pd.Timedelta(1, unit='h')).isoformat() != input_info['last_available_utc']
            or history.open_time.max() + pd.Timedelta(1, unit='h') != pd.Timestamp(RESEARCH_WINDOWS['R2025'].end)):
        raise ValueError('regime input history boundary mismatch')
    if set(run.get('states', {})) != {'all', *WINDOWS}:
        raise ValueError('regime requires all plus three window states')
    tables = {}
    for name, item in run['states'].items():
        path = contained_artifact(root, folder, item['path'], item['sha256'])
        if run.get('artifacts', {}).get(item['path']) != item['sha256']:
            raise ValueError('regime state artifact SHA binding mismatch')
        table = pd.read_parquet(path)
        grid = None if name == 'all' else pd.date_range(RESEARCH_WINDOWS[name].start, RESEARCH_WINDOWS[name].end, freq='4h', inclusive='left')
        _state_table(table, grid)
        if (len(table) != item['rows'] or int(table.state_valid.sum()) != item['valid_rows']
                or int(table.allow_buy.sum()) != item['allowed_rows']
                or table.decision_time.min().isoformat() != item['start_decision_utc']
                or table.decision_time.max().isoformat() != item['last_decision_utc']):
            raise ValueError('regime state metadata mismatch')
        tables[name] = table
    # Independent readback of fixed state formula, not a new account experiment.
    try:
        pd.testing.assert_frame_equal(tables['all'], build_market_regime(history), check_exact=True)
        for name in WINDOWS:
            window = RESEARCH_WINDOWS[name]
            sliced = tables['all'].loc[(tables['all'].decision_time >= pd.Timestamp(window.start)) &
                                      (tables['all'].decision_time < pd.Timestamp(window.end))].reset_index(drop=True)
            pd.testing.assert_frame_equal(tables[name], sliced, check_exact=True)
    except AssertionError as exc:
        raise ValueError('regime state recomputation/window slice mismatch') from exc
    return dict(state_experiment_id=state_id, state_manifest_sha256=sha_file(folder / 'state_manifest.json'),
                state_run_manifest_sha256=sha_file(folder / 'run_manifest.json'), sources=sources,
                tables=tables, run=run)


def verify_r0(root, cfg, sources):
    from cryptoquant.models.regime_workflow import REGIME_MODEL_IDS
    source_cfg = load_research_config(root / 'configs/sixth_experiment.toml', root)
    cache, matrix, evidence = {}, {}, []
    pre_path = root / '.cache/c2-execution-source-before-regime.json'
    eq_path = root / '.cache/regime-execution-equivalence-20261005.json'
    before, equivalent = read_json(pre_path), read_json(eq_path)
    if set(before.get('checked_accounts', ())) != {i for ids in R0_IDS.values() for i in ids}:
        raise ValueError('R0 execution evidence account mismatch')
    hashes = before.get('current_sha256', {})
    if set(hashes) != set(EXECUTION_FILES):
        raise ValueError('R0 execution source evidence incomplete')
    old_engine = root / before['preserved_engine']
    if not old_engine.resolve().is_relative_to((root / '.cache').resolve()) or sha_file(old_engine) != hashes[EXECUTION_FILES[0]]:
        raise ValueError('R0 preserved engine SHA mismatch')
    for filename in EXECUTION_FILES[1:]:
        if sha_file(root / filename) != hashes[filename]:
            raise ValueError('R0 current execution source mismatch')
    normalized = {str(Path(k)).replace('\\', '/'): v for k, v in equivalent.get('source_sha256', {}).items()}
    if (normalized.get(str(old_engine.relative_to(root)).replace('\\', '/')) != sha_file(old_engine)
            or normalized.get(EXECUTION_FILES[0]) != sha_file(root / EXECUTION_FILES[0])):
        raise ValueError('R0 synthetic equivalence engine SHA mismatch')
    tests = root / 'tests/test_regime_execution.py'
    if normalized.get('tests/test_regime_execution.py') != sha_file(tests):
        raise ValueError('R0 synthetic equivalence test SHA mismatch')
    checks = equivalent.get('checks', [])
    if (len(checks) != 3 or {row.get('cost') for row in checks} != set(COSTS)
            or not all(row.get('none_equals_old') is True and row.get('all_true_equals_none') is True for row in checks)):
        raise ValueError('R0 synthetic equivalence missing cost checks')
    for cost, identifiers in R0_IDS.items():
        matrix[cost] = {}
        for window, identifier in zip(WINDOWS, identifiers):
            summary, item = verify_evaluation(root, identifier, source_cfg, 'EXP-063', cache=cache)
            if (summary.get('window') != window or summary.get('cost') != cost or summary.get('exit_variant') != 'C2'
                    or summary.get('training_experiment_id') != REGIME_MODEL_IDS[window]
                    or summary.get('label_policy') != 'net_positive_base_v1' or decimal_metric(summary, 'threshold') != .5):
                raise ValueError('R0 frozen candidate/source mismatch')
            if item['training']['train_manifest_sha256'] != sources['models'][window]['train_manifest_sha256']:
                raise ValueError('R0 model manifest SHA differs from state source')
            frozen = read_json(root / 'artifacts/experiments' / identifier / 'source_manifest.json')['files']
            if any(frozen.get(name) != hashes[name] for name in EXECUTION_FILES):
                raise ValueError('R0 frozen execution source mismatch')
            matrix[cost][window] = summary
            evidence.append(dict(item, cost=cost, window=window))
    return dict(matrix=matrix, inputs=evidence, source_config_hash=source_cfg.research_config_hash,
                equivalence_proof_sha256=sha_file(eq_path), original_execution_proof_sha256=sha_file(pre_path),
                limitation='R0 uses nine frozen historical accounts; equivalence checked on synthetic 16h only, no annual rerun')


def preflight(root, cfg, state_id):
    root = Path(root).resolve()
    require_regime_config(cfg)
    state = verify_state(root, state_id, cfg)
    r0 = verify_r0(root, cfg, state['sources'])
    return dict(state=state, r0=r0)


def input_evidence(root, identifier, run):
    folder = Path(root) / 'artifacts/experiments' / identifier
    return dict(experiment_id=identifier, run_manifest_sha256=sha_file(folder / 'run_manifest.json'),
                summary_sha256=run.get('artifacts', {}).get('summary.json'),
                state_manifest_sha256=run['state_manifest_sha256'], state_run_manifest_sha256=run['state_run_manifest_sha256'])


def verify_regime_evaluation(root, identifier, cfg, context, allow_failed=False):
    from cryptoquant.models.regime_workflow import REGIME_MODEL_IDS
    folder = Path(root) / 'artifacts/experiments' / experiment_id(identifier)
    raw = read_json(contained_artifact(root, folder, 'run_manifest.json'))
    if raw.get('experiment_id') != identifier:
        raise ValueError('regime evaluation experiment ID mismatch')
    if raw.get('status') == 'failed' and allow_failed:
        run = raw
        failure = bound_json(root, folder, run, 'failure.json')
        if failure.get('status') != 'failed' or failure.get('error') != run.get('error'):
            raise ValueError('regime failed attempt evidence mismatch')
        row = dict(status='failed', error=run['error'], window=run['window'], cost=run['cost'])
    else:
        folder, run = verify_completed_experiment(root, identifier, 'regime_evaluation')
        row = bound_json(root, folder, run, 'summary.json')
    verify_regime_config(root, folder, run, cfg)
    if (run.get('type') != 'regime_evaluation' or run.get('state_experiment_id') != context['state']['state_experiment_id']
            or run.get('state_manifest_sha256') != context['state']['state_manifest_sha256']
            or run.get('state_run_manifest_sha256') != context['state']['state_run_manifest_sha256']
            or run.get('sources') != context['state']['sources']
            or run.get('r0_evidence') != {key: value for key, value in context['r0'].items() if key != 'matrix'}
            or run.get('parameter_card') != PARAMETER_CARD):
        raise ValueError('regime evaluation state/model/R0/parameter binding mismatch')
    if run.get('window') not in WINDOWS or run.get('cost') not in COSTS or run.get('regime_variant') != 'R1':
        raise ValueError('regime evaluation candidate mismatch')
    if (run.get('training_experiment_id') != REGIME_MODEL_IDS[run['window']]
            or run.get('prepared_experiment_id') != 'EXP-063' or run.get('threshold') != .5
            or run.get('exit_variant') != 'C2' or run.get('label_policy') != 'net_positive_base_v1'):
        raise ValueError('regime evaluation fixed model/window/policy mismatch')
    if run['cost'] != 'base':
        selection_id = run.get('selection_experiment_id')
        if not selection_id:
            raise ValueError('regime pressure missing selection')
        selection = verify_regime_selection(root, selection_id, cfg, context)
        expected_qualification = json.loads(json.dumps({key: value for key, value in selection.items() if key != 'matrix'}, default=str))
        if not selection['result']['eligible'] or run.get('qualification') != expected_qualification:
            raise ValueError('regime pressure qualification/source mismatch')
    if run['status'] == 'complete':
        required = {'summary.json', 'annual.json', 'events.json', 'orders.csv', 'fills.csv', 'signals.csv', 'equity.csv',
                    'weekly.csv', 'probabilities.parquet', 'targets.parquet', 'states.parquet', 'permission.parquet',
                    'source_research_config.toml', 'report.md'}
        if not required <= set(run.get('artifacts', {})):
            raise ValueError('regime evaluation missing required outputs')
        if run.get('data') != context['state']['run']['data'][RESEARCH_WINDOWS[run['window']].period]:
            raise ValueError('regime evaluation market source mismatch')
        state_table = pd.read_parquet(contained_artifact(root, folder, 'states.parquet', run['artifacts']['states.parquet']))
        permission = pd.read_parquet(contained_artifact(root, folder, 'permission.parquet', run['artifacts']['permission.parquet']))
        try:
            pd.testing.assert_frame_equal(state_table, context['state']['tables'][run['window']], check_exact=True)
            pd.testing.assert_frame_equal(permission, state_table[['decision_time', 'available_time', 'state_valid', 'allow_buy']], check_exact=True)
        except AssertionError as exc:
            raise ValueError('regime evaluation state/permission slice mismatch') from exc
        for name in ('experiment_id', 'status', 'window', 'cost', 'regime_variant', 'state_experiment_id',
                     'training_experiment_id', 'prepared_experiment_id', 'threshold', 'exit_variant', 'label_policy'):
            if row.get(name) != run.get(name):
                raise ValueError(f'regime evaluation summary/run mismatch: {name}')
        for name in ('net_return', 'max_drawdown', 'g_week', 'total_window_hours', 'floor_triggers', 'closed_cycles'):
            decimal_metric(row, name)
        initial, final = decimal_metric(row, 'initial_equity'), decimal_metric(row, 'final_equity')
        if initial != 100 or final / initial - 1 != decimal_metric(row, 'net_return'):
            raise ValueError('regime account equity/return mismatch')
        for name in ('floor_triggers', 'closed_cycles'):
            value = decimal_metric(row, name)
            if value < 0 or value != int(value):
                raise ValueError('regime account count mismatch')
        if not 0 <= decimal_metric(row, 'max_drawdown') <= 1 or decimal_metric(row, 'net_return') <= -1:
            raise ValueError('regime account return/drawdown mismatch')
        window = RESEARCH_WINDOWS[run['window']]
        hours = (window.end - window.start).total_seconds() / 3600
        if decimal_metric(row, 'total_window_hours') != hours or not math.isclose(float(row['g_week']), (1 + float(row['net_return'])) ** (168 / hours) - 1, abs_tol=1e-12):
            raise ValueError('regime account duration/weekly mismatch')
    return row, input_evidence(root, identifier, run)


def collect_regime_matrix(root, ids, cfg, context, expected):
    if len(ids) != len(set(ids)) or len(ids) != len(expected):
        raise ValueError('requires unique complete regime account matrix')
    matrix, inputs = {}, []
    for identifier in ids:
        row, evidence = verify_regime_evaluation(root, identifier, cfg, context, allow_failed=True)
        key = (row['window'], row['cost'])
        if key in matrix or key not in expected:
            raise ValueError('duplicate/outside regime account matrix')
        matrix[key] = row
        inputs.append(evidence)
    if set(matrix) != set(expected):
        raise ValueError('missing regime account matrix')
    return matrix, inputs


def verify_regime_selection(root, identifier, cfg, context):
    folder, run = verify_completed_experiment(root, identifier, 'regime_selection')
    verify_regime_config(root, folder, run, cfg)
    if (run.get('state_experiment_id') != context['state']['state_experiment_id']
            or run.get('state_manifest_sha256') != context['state']['state_manifest_sha256']
            or run.get('state_run_manifest_sha256') != context['state']['state_run_manifest_sha256']
            or run.get('sources') != context['state']['sources']):
        raise ValueError('regime selection state/source SHA mismatch')
    data = bound_json(root, folder, run, 'selection.json')
    ids = run.get('base_experiment_ids', [])
    matrix, evidence = collect_regime_matrix(root, ids, cfg, context, {(w, 'base') for w in WINDOWS})
    computed = evaluate_base({w: matrix[(w, 'base')] for w in WINDOWS}, context['r0']['matrix']['base'])
    # JSON serializes Decimal as text; compare canonical values, never trust pass.
    normalized = json.loads(json.dumps(computed, default=str))
    if data.get('result') != normalized or data.get('inputs') != evidence or run.get('selection_inputs') != evidence:
        raise ValueError('regime selection inputs/frozen qualification mismatch')
    if data.get('r0_evidence') != {key: value for key, value in context['r0'].items() if key != 'matrix'}:
        raise ValueError('regime selection R0 evidence mismatch')
    return dict(result=computed, matrix=matrix, inputs=evidence, selection_experiment_id=identifier,
                selection_run_manifest_sha256=sha_file(folder / 'run_manifest.json'), selection_sha256=sha_file(folder / 'selection.json'))

"""有限研究资格与预算。只读核验来源；预检不得创建实验目录。"""
import hashlib
import json
import math
from pathlib import Path
from decimal import Decimal
import tomllib

from cryptoquant.baselines.io import experiment_id
from cryptoquant.data.archive import sha_file
from cryptoquant.models.labels import GROSS_POLICY, NET_POLICY
from cryptoquant.models.features import ALL_FEATURE_NAMES
from cryptoquant.models.research_config import _FIXED_VALUES_V5, _FIXED_VALUES_V6, RESEARCH_WINDOWS
from cryptoquant.models.research_integrity import (
    verify_completed_experiment, verify_prepared, verify_config_binding, contained_artifact,
)
from cryptoquant.models.research_reporting import evaluate_research_candidates

THRESHOLDS = (.4, .5, .6, .64)
COSTS = ('base', 'higher_execution', 'strict')
VARIANTS = ('C0', 'C1', 'C2', 'C3')


def _read(path):
    value = json.loads(Path(path).read_text('utf-8'))
    if not isinstance(value, dict):
        raise ValueError('manifest must be an object')
    return value


def _profile(path):
    values = tomllib.loads(Path(path).read_text('utf-8-sig'))
    if values == _FIXED_VALUES_V5:
        return 'V5'
    if values == _FIXED_VALUES_V6:
        return 'V6'
    raise ValueError('unknown research budget profile')


def _exact_config(root, folder, run, cfg):
    verify_config_binding(root, folder, run, run)
    if (_profile(folder / 'research_config.toml') != _profile(cfg.research_config_path)
            or run['execution_config_hash'] != cfg.execution_config_hash):
        raise ValueError('evaluation/selection research profile mismatch')


def _bound_json(root, folder, run, name):
    digest = run.get('artifacts', {}).get(name)
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError(f'missing artifact SHA: {name}')
    return _read(contained_artifact(root, folder, name, digest))


def _evidence(folder, run):
    return dict(experiment_id=run['experiment_id'], run_manifest_sha256=sha_file(folder / 'run_manifest.json'),
                source_hash=run.get('source_hash'), verified_source=run.get('verified_source', {}))


def _variant(root, folder, run, profile):
    variant = run.get('exit_variant')
    if variant is None:
        if 'summary.json' in run.get('artifacts', {}):
            variant = _bound_json(root, folder, run, 'summary.json').get('exit_variant')
        if variant is None and profile == 'V5':
            variant = 'C0'  # 原第五轮明确只有原出场，禁止第六轮无证推断。
    if variant not in VARIANTS:
        raise ValueError('unknown budget exit variant')
    return variant


def _key(root, folder, run, profile):
    try:
        return (run['label_policy'], run['window'], float(run['threshold']), run['cost'],
                _variant(root, folder, run, profile))
    except (KeyError, TypeError) as exc:
        raise ValueError('unknown account budget candidate') from exc


def audit_account_budget(root, cfg):
    """同一冻结语义profile的所有账户尝试计数；prepared ID和配置文件名不重置。"""
    root = Path(root).resolve()
    profile = _profile(cfg.research_config_path)
    records = []
    for path in sorted((root / 'artifacts/experiments').glob('*/run_manifest.json')):
        run = _read(path)
        if run.get('type') != 'research_evaluation':
            continue
        if run.get('status') not in ('running', 'failed', 'complete'):
            raise ValueError('unknown account budget status')
        if path.parent.name != run.get('experiment_id'):
            raise ValueError('account budget experiment ID mismatch')
        config_path = path.parent / 'research_config.toml'
        if not config_path.is_file():
            raise ValueError('unknown account budget profile: missing frozen config')
        expected = run.get('research_config_hash')
        contained_artifact(root, path.parent, config_path, expected)
        if not expected:
            raise ValueError('unknown account budget profile: missing config SHA')
        verify_config_binding(root, path.parent, run, run)
        saved_profile = _profile(config_path)
        if saved_profile != profile:
            continue
        key = _key(root, path.parent, run, profile)
        records.append(dict(experiment_id=run['experiment_id'], status=run['status'], key=key,
                            run_manifest_sha256=sha_file(path)))
    return dict(profile=profile, used=len(records), limit=30 if profile == 'V5' else 18, records=records)


def enforce_account_budget(root, cfg, candidate):
    audit = audit_account_budget(root, cfg)
    if audit['used'] >= audit['limit']:
        raise ValueError(f"account budget exhausted: {audit['used']}/{audit['limit']}")
    if any(tuple(row['key']) == tuple(candidate) for row in audit['records']):
        raise ValueError('duplicate account candidate; failed/running attempts remain consumed')
    return audit


def validate_scope(cfg, window, policy, threshold=None, cost='base', variant='C0'):
    profile = _profile(cfg.research_config_path)
    if window not in RESEARCH_WINDOWS or policy not in cfg.label_policies:
        raise ValueError('window or label policy outside research scope')
    if threshold is not None and float(threshold) not in tuple(float(t) for t in cfg.thresholds):
        raise ValueError('threshold outside research scope')
    if cost not in COSTS or variant not in VARIANTS or (profile == 'V5' and variant != 'C0'):
        raise ValueError('cost or exit variant outside research scope')
    return profile


def _verify_training(root, training_id, prepared_id, cfg, window, policy, cache):
    key = ('training', training_id, prepared_id, window, policy)
    if key in cache:
        return cache[key]
    folder, run = verify_completed_experiment(root, training_id, 'research_training')
    child = _read(folder / 'train_manifest.json')
    compatibility = verify_config_binding(root, folder, child, run, cfg)
    for name, expected in [('prepared_experiment_id', prepared_id), ('window', window), ('label_policy', policy)]:
        if run.get(name) != expected or child.get(name) != expected:
            raise ValueError(f'training source {name} mismatch')
    if (child.get('C') != .1 or run.get('C') != .1 or child.get('model_family') != 'logistic_regression'
            or child.get('feature_names') != ALL_FEATURE_NAMES
            or set(child.get('symbols', {})) != set(cfg.execution_config.symbols)):
        raise ValueError('training C, model family, features or symbols mismatch')
    win = RESEARCH_WINDOWS[window]
    if child.get('fit_start_utc') != win.fit_start.isoformat() or child.get('fit_end_utc') != win.fit_end.isoformat():
        raise ValueError('training window boundary mismatch')
    prep_key = ('prepared', prepared_id)
    if prep_key not in cache:
        cache[prep_key] = verify_prepared(root, prepared_id, cfg)
    prepared, _ = cache[prep_key]
    prep_sha = sha_file(Path(root) / 'artifacts/experiments' / prepared_id / 'prepared_manifest.json')
    declared_sha = child.get('prepared_manifest_sha256')
    legacy_ids = {'EXP-064', 'EXP-065', 'EXP-066', 'EXP-067', 'EXP-093', 'EXP-094'}
    if declared_sha != prep_sha and not (declared_sha is None and training_id in legacy_ids and prepared_id == 'EXP-063'):
        raise ValueError('training prepared SHA mismatch')
    if child.get('label_card') != prepared['label_policies'][policy]:
        raise ValueError('training label policy semantics mismatch')
    if window == 'R2025' and training_id not in legacy_ids:
        selection_id = child.get('selection_experiment_id')
        if not selection_id or run.get('selection_experiment_id') != selection_id:
            raise ValueError('R2025 training selection evidence missing')
        selection, _ = verify_fifth_selection(root, selection_id, cfg, prepared_id)
        if selection['do_not_run_R2025'] or selection[policy]['selected_threshold'] is None:
            raise ValueError('R2025 training selection is not qualified')
    cache[key] = dict(_evidence(folder, run), train_manifest_sha256=sha_file(folder / 'train_manifest.json'),
                      prepared_manifest_sha256=prep_sha, config_compatibility=compatibility)
    return cache[key]


def _verify_failed(root, folder, run):
    if (run.get('status') != 'failed' or run.get('type') != 'research_evaluation'
            or run.get('experiment_id') != folder.name or not run.get('error')):
        raise ValueError('failed candidate must retain registered failed manifest and error')
    for name, digest in run.get('artifacts', {}).items():
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError('missing failed artifact SHA')
        contained_artifact(root, folder, name, digest)
    source = _read(contained_artifact(root, folder, 'source_manifest.json'))
    files = source.get('files', {})
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    if not files or source.get('source_hash') != digest or run.get('source_hash') != digest or not run.get('environment'):
        raise ValueError('failed candidate source evidence missing')
    for name, digest in files.items():
        contained_artifact(root, folder, Path('source_snapshot') / name, digest)


def verify_evaluation(root, exp_id, cfg, prepared_id=None, allow_failed=False, cache=None):
    cache = {} if cache is None else cache
    folder = Path(root) / 'artifacts/experiments' / experiment_id(exp_id)
    raw = _read(contained_artifact(root, folder, 'run_manifest.json'))
    if raw.get('status') == 'failed' and allow_failed:
        run = raw
        _verify_failed(root, folder, run)
        summary = dict(run, status='failed', error=run['error'])
    else:
        folder, run = verify_completed_experiment(root, exp_id, 'research_evaluation')
        summary = _bound_json(root, folder, run, 'summary.json')
        for name in ('experiment_id', 'status', 'prepared_experiment_id', 'training_experiment_id',
                     'window', 'label_policy', 'threshold', 'cost'):
            if summary.get(name) != run.get(name):
                raise ValueError(f'evaluation summary/run {name} mismatch')
        for name, value in run.get('summary', {}).items():
            # Frozen summaries preserve Decimal text while inline summaries store floats.
            if name not in summary or float(summary[name]) != float(value):
                raise ValueError(f'evaluation inline summary {name} mismatch')
        for name in ('net_return', 'max_drawdown', 'g_week', 'total_window_hours', 'closed_cycles', 'floor_triggers'):
            if not math.isfinite(float(summary[name])):
                raise ValueError('nonfinite evaluation metrics')
        if any(float(summary[k]) < 0 or float(summary[k]) != int(summary[k])
               for k in ('closed_cycles', 'floor_triggers')) or not 0 <= float(summary['max_drawdown']) <= 1:
            raise ValueError('evaluation risk/count semantics mismatch')
        initial, final = Decimal(str(summary['initial_equity'])), Decimal(str(summary['final_equity']))
        if initial != cfg.execution_config.initial_cash or (final - initial) / initial != Decimal(str(summary['net_return'])):
            raise ValueError('evaluation account return semantics mismatch')
        hours = (RESEARCH_WINDOWS[summary['window']].end - RESEARCH_WINDOWS[summary['window']].start).total_seconds() / 3600
        if float(summary['total_window_hours']) != hours or float(summary['net_return']) <= -1:
            raise ValueError('evaluation duration/return mismatch')
        if not math.isclose(float(summary['g_week']), (1 + float(summary['net_return'])) ** (168 / hours) - 1, abs_tol=1e-12):
            raise ValueError('evaluation weekly return mismatch')
    _exact_config(root, folder, run, cfg)
    variant = _variant(root, folder, run, _profile(cfg.research_config_path))
    if summary.get('exit_variant', variant) != variant:
        raise ValueError('evaluation exit variant mismatch')
    summary['exit_variant'] = variant
    validate_scope(cfg, summary['window'], summary['label_policy'], summary['threshold'], summary['cost'], variant)
    if prepared_id is not None and run['prepared_experiment_id'] != prepared_id:
        raise ValueError('evaluation prepared source mismatch')
    training = _verify_training(root, run['training_experiment_id'], run['prepared_experiment_id'], cfg,
                                run['window'], run['label_policy'], cache)
    return summary, dict(_evidence(folder, run), training=training,
                         summary_sha256=run.get('artifacts', {}).get('summary.json'))


def collect_base_candidates(root, ids, cfg, prepared_id):
    if _profile(cfg.research_config_path) != 'V5':
        raise ValueError('fifth selection requires V5 research profile')
    if len(ids) != 16 or len(set(ids)) != 16:
        raise ValueError('selection requires complete matrix of 16 unique inputs')
    summaries, evidence, cache = {}, {}, {}
    for exp_id in ids:
        summary, proof = verify_evaluation(root, exp_id, cfg, prepared_id, allow_failed=True, cache=cache)
        key = (summary['label_policy'], summary['window'], float(summary['threshold']))
        if summary['cost'] != 'base' or summary['window'] not in ('W1', 'W2') or key in summaries:
            raise ValueError('duplicate or out-of-matrix base candidate')
        summaries[key], evidence[exp_id] = summary, proof
    expected = {(p, w, t) for p in (GROSS_POLICY, NET_POLICY) for w in ('W1', 'W2') for t in THRESHOLDS}
    if set(summaries) != expected:
        raise ValueError('missing base candidate matrix')
    return summaries, evidence


def verify_fifth_selection(root, selection_id, cfg, prepared_id=None):
    folder, run = verify_completed_experiment(root, selection_id, 'research_selection')
    # A sixth request may consume fifth selection, but the selection itself is always V5.
    from cryptoquant.models.research_config import load_research_config
    fifth_path = Path(root) / 'configs/fifth_experiment.toml'
    fifth = cfg if _profile(cfg.research_config_path) == 'V5' else load_research_config(fifth_path, root)
    _exact_config(root, folder, run, fifth)
    actual_prepared = run.get('prepared_experiment_id')
    if prepared_id is not None and actual_prepared != prepared_id:
        raise ValueError('selection prepared source mismatch')
    data = _bound_json(root, folder, run, 'selection_summary.json')
    if data.get('experiment_id') != selection_id or data.get('prepared_experiment_id') != actual_prepared:
        raise ValueError('selection identity mismatch')
    summaries, inputs = collect_base_candidates(root, run.get('base_experiment_ids', []), fifth, actual_prepared)
    recomputed = evaluate_research_candidates(summaries, fifth)
    if data.get('selection_results') != recomputed or data.get('do_not_run_R2025') != recomputed['do_not_run_R2025']:
        raise ValueError('saved selection differs from recomputed selection')
    legacy_binding = 'input_evidence' not in data and selection_id == 'EXP-084'
    if not legacy_binding and data.get('input_evidence') != inputs:
        raise ValueError('selection input manifest SHA mismatch')
    return recomputed, dict(_evidence(folder, run), selection_summary_sha256=run['artifacts']['selection_summary.json'],
                             prepared_experiment_id=actual_prepared, inputs=inputs,
                             input_binding='legacy_recomputed; old selection lacks frozen input SHA list' if legacy_binding else 'verified_frozen_inputs')


def verify_ablation_selection(root, selection_id, cfg, prepared_id):
    if _profile(cfg.research_config_path) != 'V6':
        raise ValueError('ablation selection requires sixth research profile')
    folder, run = verify_completed_experiment(root, selection_id, 'ablation_selection_and_freeze')
    if selection_id != 'EXP-114':
        _exact_config(root, folder, run, cfg)
        if run.get('prepared_experiment_id') != prepared_id:
            raise ValueError('ablation selection prepared source mismatch')
        verify_prepared(root, prepared_id, cfg)
        parent_path = Path(root) / 'artifacts/experiments' / experiment_id(prepared_id) / 'prepared_manifest.json'
        if run.get('prepared_manifest_sha256') != sha_file(parent_path):
            raise ValueError('ablation selection prepared manifest SHA mismatch')
    data = _bound_json(root, folder, run, 'evaluation.json')
    ids = run.get('input_experiments', [])
    if len(ids) != 12 or len(set(ids)) != 12:
        raise ValueError('ablation selection requires 12 unique inputs')
    summaries, inputs, cache, base_selections = {}, {}, {}, set()
    for exp_id in ids:
        summary, proof = verify_evaluation(root, exp_id, cfg, prepared_id, cache=cache)
        key = (summary['window'], summary['exit_variant'])
        if key in summaries or summary['cost'] != 'base' or summary['label_policy'] != NET_POLICY or summary['threshold'] != .5:
            raise ValueError('duplicate or wrong ablation candidate')
        summaries[key], inputs[exp_id] = summary, proof
        input_run = _read(Path(root) / 'artifacts/experiments' / exp_id / 'run_manifest.json')
        fifth_id = input_run.get('selection_experiment_id')
        if fifth_id is None and exp_id in {f'EXP-{n}' for n in range(102, 114)}:
            fifth_id = 'EXP-084'  # 唯一已登记的旧第六轮基础来源适配。
        if not fifth_id:
            raise ValueError('ablation input lacks fifth selection binding')
        base_selections.add(fifth_id)
    if set(summaries) != {(w, v) for w in RESEARCH_WINDOWS for v in VARIANTS}:
        raise ValueError('incomplete ablation matrix')
    fifth_evidence = {}
    for fifth_id in base_selections:
        result, proof = verify_fifth_selection(root, fifth_id, cfg, prepared_id)
        if result['do_not_run_R2025'] or result[NET_POLICY]['selected_threshold'] != .5:
            raise ValueError('ablation base requires fifth qualified net .50')
        fifth_evidence[fifth_id] = proof
    def combined(variant):
        rows = [summaries[(w, variant)] for w in RESEARCH_WINDOWS]
        return math.exp(168 * sum(math.log1p(float(r['net_return'])) for r in rows) /
                        sum(float(r['total_window_hours']) for r in rows)) - 1
    qualified = []
    for variant in VARIANTS[1:]:
        rows = [summaries[(w, variant)] for w in RESEARCH_WINDOWS]
        safe = all(r['floor_triggers'] == 0 and r['closed_cycles'] >= 30 and
                   float(r['max_drawdown']) <= float(summaries[(w, 'C0')]['max_drawdown']) + .015
                   for w, r in zip(RESEARCH_WINDOWS, rows))
        w2, r25 = summaries[('W2', variant)], summaries[('R2025', variant)]
        c0_w2, c0_r = summaries[('W2', 'C0')], summaries[('R2025', 'C0')]
        if (safe and float(w2['net_return']) >= .75 * float(c0_w2['net_return'])
                and float(r25['net_return']) > float(c0_r['net_return'])
                and float(r25['max_drawdown']) < float(c0_r['max_drawdown']) and combined(variant) > combined('C0')):
            qualified.append(variant)
    qualified.sort(key=lambda v: (-float(summaries[('W2', v)]['net_return']),
                                   -float(summaries[('R2025', v)]['net_return']), -combined(v)))
    selected = data.get('selected_variant')
    if not qualified or selected != qualified[0] or run.get('selected_variant') != selected:
        raise ValueError('ablation selected variant fails recomputed qualification')
    frozen = dict(variant=selected, strategy={'C1': 'rule_a_max_duration', 'C2': 'rule_b_breakeven_stop',
                 'C3': 'combined_rules'}[selected], max_holding_hours=8 if selected in ('C1', 'C3') else None,
                 breakeven_activation='0.0120' if selected in ('C2', 'C3') else None,
                 breakeven_ratio='0.0025' if selected in ('C2', 'C3') else None, cooldown_hours=4, stop_loss='0.08',
                 capital_initial='100', equity_floor='50', weight_per_symbol='0.30', label_policy=NET_POLICY,
                 threshold=.5, C=.1, model_family='logistic_regression', feature_policy='kline_and_funding')
    if data.get('experiment_id') != selection_id or data.get('frozen_parameters') != frozen:
        raise ValueError('ablation frozen parameter mismatch')
    # Historical pass_* flags and rounded retention values are intentionally ignored.
    legacy_binding = 'input_evidence' not in data and selection_id == 'EXP-114'
    if not legacy_binding and data.get('input_evidence') != inputs:
        raise ValueError('ablation selection input SHA mismatch')
    return selected, dict(_evidence(folder, run), evaluation_sha256=run['artifacts']['evaluation.json'],
                          inputs=inputs, fifth_selections=fifth_evidence,
                          selection_config_binding='legacy_EXP114_verified_inputs; own config/prepared SHA missing' if selection_id == 'EXP-114' else 'verified_own_frozen_config_and_prepared_SHA',
                          input_binding='legacy_recomputed; old selection lacks frozen input SHA list' if legacy_binding else 'verified_frozen_inputs',
                          qualification='base_only; pressure qualification is separate')


def authorize_research(root, cfg, prepared_id, window, policy, *, selection_id=None,
                       threshold=None, cost='base', variant='C0', training=False):
    profile = validate_scope(cfg, window, policy, threshold, cost, variant)
    required = window == 'R2025' or (not training and (cost != 'base' or profile == 'V6'))
    if required and not selection_id:
        raise ValueError('selection-experiment-id is required before research execution')
    proof = {}
    if selection_id:
        if profile == 'V6' and not training and cost != 'base':
            selected, proof = verify_ablation_selection(root, selection_id, cfg, prepared_id)
            if variant != selected:
                raise ValueError('exit variant differs from frozen selection')
        else:
            result, proof = verify_fifth_selection(root, selection_id, cfg, prepared_id)
            net = result[NET_POLICY]
            if result['do_not_run_R2025'] or net['status'] != 'qualified_and_selected':
                raise ValueError('net policy lacks qualified dual-window selection')
            selected = result[policy]
            if policy == GROSS_POLICY and selected['status'] != 'qualified_and_selected' and (
                    selected['status'] != 'failed_with_reference' or not selected['is_reference_only']
                    or selected['selected_threshold'] != .64):
                raise ValueError('gross policy only allowed as fixed .64 failed reference')
            if threshold is not None and float(threshold) != selected['selected_threshold']:
                raise ValueError('threshold differs from selected policy')
            if profile == 'V6' and net['selected_threshold'] != .5:
                raise ValueError('sixth requires fifth selected net .50')
    prepared, run = verify_prepared(root, prepared_id, cfg)
    prep_folder = Path(root) / 'artifacts/experiments' / prepared_id
    return dict(selection_experiment_id=selection_id, selection_evidence=proof,
                prepared_evidence=dict(_evidence(prep_folder, run),
                                       prepared_manifest_sha256=sha_file(prep_folder / 'prepared_manifest.json')))


def collect_comparison(root, ids, selection_id, cfg):
    if _profile(cfg.research_config_path) != 'V5':
        raise ValueError('research-compare supports fifth profile only')
    result, selection = verify_fifth_selection(root, selection_id, cfg)
    if len(ids) != 18 or len(set(ids)) != 18:
        raise ValueError('comparison requires 18 unique complete selected candidates')
    summaries, evidence, cache = {}, {}, {}
    for exp_id in ids:
        summary, proof = verify_evaluation(root, exp_id, cfg, selection['prepared_experiment_id'], cache=cache)
        policy = summary['label_policy']
        key = (policy, summary['window'], float(summary['threshold']), summary['cost'])
        if key in summaries or key[2] != result[policy]['selected_threshold']:
            raise ValueError('duplicate or unselected comparison threshold')
        summaries[key], evidence[exp_id] = summary, proof
    expected = {(p, w, result[p]['selected_threshold'], c)
                for p in (GROSS_POLICY, NET_POLICY) for w in RESEARCH_WINDOWS for c in COSTS}
    if set(summaries) != expected:
        raise ValueError('incomplete comparison matrix')
    return result, summaries, dict(selection=selection, inputs=evidence)

"""有限合成门禁检查；正式实验和封存行情保持只读。"""
import hashlib
import json
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from cryptoquant.data.archive import sha_file
from cryptoquant.models.research_config import load_research_config
from cryptoquant.models.labels import NET_POLICY, GROSS_POLICY
from cryptoquant.models.research_workflow import execute_research_evaluate
from cryptoquant.models.research_models import execute_research_train, train_research_window

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def scope(tmp_path):
    shutil.copytree(PROJECT / 'configs', tmp_path / 'configs')
    return tmp_path, load_research_config(tmp_path / 'configs/fifth_experiment.toml', tmp_path)


def args(cfg, **extra):
    values = dict(research_config=cfg.research_config_path, experiment_id='EXP-900',
                  prepared_experiment_id='EXP-063', training_experiment_id='EXP-065',
                  window='R2025', label_policy=NET_POLICY, threshold=.5, cost='base', exit_variant='C0')
    return SimpleNamespace(**(values | extra))


@pytest.mark.parametrize('entry', [execute_research_evaluate, execute_research_train])
def test_unselected_r2025_rejected_before_io_and_creation(scope, monkeypatch, entry):
    root, cfg = scope
    monkeypatch.setattr('cryptoquant.models.research_workflow.load_period', lambda *a: pytest.fail('market loaded'))
    monkeypatch.setattr('cryptoquant.models.research_models.fit_model', lambda *a, **k: pytest.fail('fit called'))
    with pytest.raises(ValueError, match='selection'):
        entry(args(cfg), root)
    assert not (root / 'artifacts/experiments/EXP-900').exists()


def test_direct_fit_helper_cannot_bypass_selection(scope):
    root, cfg = scope
    with pytest.raises(ValueError, match='selection'):
        train_research_window(root, 'EXP-063', 'R2025', NET_POLICY, cfg, root / 'new-models')
    assert not (root / 'new-models').exists()


@pytest.mark.parametrize('extra', [dict(exit_variant='C2'), dict(threshold=.61), dict(label_policy='unknown')])
def test_fifth_invalid_candidates_rejected_before_creation(scope, extra):
    root, cfg = scope
    with pytest.raises(ValueError, match='scope|variant|threshold|policy'):
        execute_research_evaluate(args(cfg, window='W1', **extra), root)
    assert not (root / 'artifacts/experiments/EXP-900').exists()


def synthetic_evaluation(root, cfg, exp_id='EXP-800', status='complete', **values):
    folder = root / 'artifacts/experiments' / exp_id
    folder.mkdir(parents=True)
    for name, source in [('config.toml', cfg.execution_config_path), ('research_config.toml', cfg.research_config_path)]:
        shutil.copyfile(source, folder / name)
    source_folder = folder / 'source_snapshot'
    source_folder.mkdir()
    (source_folder / 'source.py').write_text('pass', encoding='utf-8')
    files = {'source.py': sha_file(source_folder / 'source.py')}
    source_hash = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    (folder / 'source_manifest.json').write_text(json.dumps(dict(files=files, source_hash=source_hash)), encoding='utf-8')
    summary = dict(experiment_id=exp_id, status=status, prepared_experiment_id='EXP-063',
                   training_experiment_id='EXP-065', label_policy=NET_POLICY, window='W1',
                   threshold=.5, cost='base', exit_variant='C0', net_return=.03,
                   max_drawdown=.05, closed_cycles=35, floor_triggers=0, total_window_hours=8760,
                   g_week=1.03 ** (168 / 8760) - 1, fees_usdt=1)
    summary.update(values)
    (folder / 'summary.json').write_text(json.dumps(summary), encoding='utf-8')
    run = dict(summary, type='research_evaluation', source_hash=source_hash,
               environment=dict(python='test', packages={'test': '1'}),
               research_config_hash=cfg.research_config_hash, execution_config_hash=cfg.execution_config_hash,
               artifacts={name: sha_file(folder / name) for name in ['summary.json', 'config.toml', 'research_config.toml']})
    (folder / 'run_manifest.json').write_text(json.dumps(run), encoding='utf-8')
    return folder, run


def test_budget_counts_running_and_failed_and_semantic_config_alias(scope):
    from cryptoquant.models.research_gates import audit_account_budget, enforce_account_budget
    root, cfg = scope
    synthetic_evaluation(root, cfg, status='failed')
    synthetic_evaluation(root, cfg, 'EXP-801', status='running', threshold=.6)
    alias = root / 'configs/alias.toml'
    alias.write_text('# cosmetic alias\n' + cfg.research_config_path.read_text('utf-8'), encoding='utf-8')
    alias_cfg = load_research_config(alias, root)
    assert audit_account_budget(root, alias_cfg)['used'] == 2
    with pytest.raises(ValueError, match='duplicate'):
        enforce_account_budget(root, alias_cfg, (NET_POLICY, 'W1', .5, 'base', 'C0'))


def test_budget_rejects_exhaustion_and_unknown_profile(scope):
    from cryptoquant.models.research_gates import enforce_account_budget, audit_account_budget
    root, cfg = scope
    for index in range(30):
        synthetic_evaluation(root, cfg, f'EXP-{800 + index}', status='failed')
    with pytest.raises(ValueError, match='budget'):
        enforce_account_budget(root, cfg, (NET_POLICY, 'W2', .6, 'strict', 'C0'))
    folder, run = synthetic_evaluation(root, cfg, 'EXP-850')
    (folder / 'research_config.toml').unlink()
    run['research_config_hash'] = '0' * 64
    (folder / 'run_manifest.json').write_text(json.dumps(run), encoding='utf-8')
    with pytest.raises(ValueError, match='budget|profile'):
        audit_account_budget(root, cfg)


def test_selection_duplicate_and_missing_matrix_do_not_create_output(scope):
    from cryptoquant.models.research_workflow import execute_research_select
    root, cfg = scope
    for ids in [['EXP-800'] * 16, ['EXP-800']]:
        with pytest.raises(ValueError, match='unique|matrix'):
            execute_research_select(args(cfg, base_experiment_ids=ids), root)
        assert not (root / 'artifacts/experiments/EXP-900').exists()


def test_selection_corrupt_summary_sha_rejected(scope):
    from cryptoquant.models.research_gates import verify_evaluation
    root, cfg = scope
    folder, _ = synthetic_evaluation(root, cfg)
    (folder / 'summary.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='SHA'):
        verify_evaluation(root, 'EXP-800', cfg)


@pytest.fixture
def authorized_rules(scope, monkeypatch):
    from cryptoquant.models import research_gates as gates
    root, cfg = scope
    folder = root / 'artifacts/experiments/EXP-063'
    folder.mkdir(parents=True)
    (folder / 'prepared_manifest.json').write_text('{}', encoding='utf-8')
    (folder / 'run_manifest.json').write_text('{}', encoding='utf-8')
    result = {NET_POLICY: dict(status='qualified_and_selected', selected_threshold=.5),
              GROSS_POLICY: dict(status='failed_with_reference', is_reference_only=True, selected_threshold=.64),
              'do_not_run_R2025': False}
    monkeypatch.setattr(gates, 'verify_fifth_selection', lambda *a: (result, {'verified': True}))
    monkeypatch.setattr(gates, 'verify_prepared', lambda *a: ({}, {'experiment_id': 'EXP-063'}))
    return root, cfg, result


def test_selected_policy_threshold_and_r2025_fit_qualification(authorized_rules):
    from cryptoquant.models.research_gates import authorize_research
    root, cfg, result = authorized_rules
    proof = authorize_research(root, cfg, 'EXP-063', 'R2025', NET_POLICY, threshold=.5, selection_id='EXP-084')
    assert proof['selection_experiment_id'] == 'EXP-084'
    with pytest.raises(ValueError, match='threshold'):
        authorize_research(root, cfg, 'EXP-063', 'W1', NET_POLICY, threshold=.6, cost='strict', selection_id='EXP-084')
    with pytest.raises(ValueError, match='threshold'):
        authorize_research(root, cfg, 'EXP-063', 'R2025', GROSS_POLICY, threshold=.5, selection_id='EXP-084')
    authorize_research(root, cfg, 'EXP-063', 'R2025', GROSS_POLICY, threshold=.64, selection_id='EXP-084')
    result['do_not_run_R2025'] = True
    with pytest.raises(ValueError, match='qualified'):
        authorize_research(root, cfg, 'EXP-063', 'R2025', NET_POLICY, training=True, selection_id='EXP-084')


def test_sixth_base_and_pressure_bind_different_selections(authorized_rules, monkeypatch):
    from cryptoquant.models import research_gates as gates
    root, _, _ = authorized_rules
    cfg = load_research_config(root / 'configs/sixth_experiment.toml', root)
    with pytest.raises(ValueError, match='selection'):
        gates.authorize_research(root, cfg, 'EXP-063', 'W1', NET_POLICY, threshold=.5, variant='C2')
    gates.authorize_research(root, cfg, 'EXP-063', 'W1', NET_POLICY, threshold=.5, variant='C2', selection_id='EXP-084')
    monkeypatch.setattr(gates, 'verify_ablation_selection', lambda *a: ('C2', {'qualification': 'base_only'}))
    with pytest.raises(ValueError, match='variant'):
        gates.authorize_research(root, cfg, 'EXP-063', 'W1', NET_POLICY, threshold=.5, variant='C3',
                                 cost='strict', selection_id='EXP-114')


def test_distinct_ids_cannot_overwrite_same_candidate(scope, monkeypatch):
    from cryptoquant.models import research_gates as gates
    root, cfg = scope
    row = dict(label_policy=NET_POLICY, window='W1', threshold=.5, cost='base')
    monkeypatch.setattr(gates, 'verify_evaluation', lambda *a, **k: (row, {}))
    with pytest.raises(ValueError, match='duplicate'):
        gates.collect_base_candidates(root, [f'EXP-{800+i}' for i in range(16)], cfg, 'EXP-063')


def test_started_account_failure_is_retained_and_consumes_budget(scope, monkeypatch):
    from cryptoquant.models import research_workflow as workflow
    from cryptoquant.models.research_gates import enforce_account_budget, audit_account_budget
    root, _ = scope
    cfg = load_research_config(root / 'configs/sixth_experiment.toml', root)
    monkeypatch.setattr(workflow, 'authorize_research', lambda *a, **k: {})
    monkeypatch.setattr(workflow, '_verify_training', lambda *a, **k: {})
    def unavailable(*a, **k):
        raise ValueError('synthetic market unavailable')
    monkeypatch.setattr(workflow, 'load_period', unavailable)
    with pytest.raises(ValueError, match='unavailable'):
        execute_research_evaluate(args(cfg, window='W1', exit_variant='C2',
                                      selection_experiment_id='EXP-084', data_experiment_id='EXP-777'), root)
    folder = root / 'artifacts/experiments/EXP-900'
    run = json.loads((folder / 'run_manifest.json').read_text('utf-8'))
    assert run['status'] == 'failed' and (folder / 'failure.json').is_file()
    for flag, expected in [('--selection-experiment-id', 'EXP-084'), ('--exit-variant', 'C2'),
                           ('--data-experiment-id', 'EXP-777')]:
        assert flag in run['command'] and run['command'][run['command'].index(flag) + 1] == expected
    assert audit_account_budget(root, cfg)['used'] == 1
    with pytest.raises(ValueError, match='duplicate'):
        enforce_account_budget(root, cfg, (NET_POLICY, 'W1', .5, 'base', 'C2'))


def test_failed_r2025_training_command_retains_selection_parameter(scope, monkeypatch):
    from cryptoquant.models import research_models, research_gates
    root, cfg = scope
    monkeypatch.setattr(research_gates, 'authorize_research', lambda *a, **k: {})
    def unavailable(*a, **k):
        raise ValueError('synthetic training unavailable before fit')
    monkeypatch.setattr(research_models, 'train_research_window', unavailable)
    with pytest.raises(ValueError, match='unavailable'):
        execute_research_train(args(cfg, selection_experiment_id='EXP-084'), root)
    run = json.loads((root / 'artifacts/experiments/EXP-900/run_manifest.json').read_text('utf-8'))
    assert run['status'] == 'failed'
    assert '--selection-experiment-id' in run['command']
    assert run['command'][run['command'].index('--selection-experiment-id') + 1] == 'EXP-084'


def test_comparison_missing_and_wrong_profile_rejected(scope, monkeypatch):
    from cryptoquant.models import research_gates as gates
    root, cfg = scope
    monkeypatch.setattr(gates, 'verify_fifth_selection', lambda *a: ({}, {}))
    with pytest.raises(ValueError, match='18 unique'):
        gates.collect_comparison(root, ['EXP-800'], 'EXP-084', cfg)
    sixth = load_research_config(root / 'configs/sixth_experiment.toml', root)
    with pytest.raises(ValueError, match='fifth profile'):
        gates.collect_comparison(root, [], 'EXP-114', sixth)


def test_cli_accepts_selection_and_rejects_unselected_r2025(scope, monkeypatch):
    from cryptoquant.cli import main
    root, cfg = scope
    monkeypatch.chdir(root)
    assert main(['research-train', '--research-config', str(cfg.research_config_path), '--experiment-id', 'EXP-900',
                 '--prepared-experiment-id', 'EXP-063', '--window', 'R2025', '--label-policy', NET_POLICY]) == 1
    assert not (root / 'artifacts/experiments/EXP-900').exists()


def test_new_selection_cannot_omit_frozen_input_shas(scope, monkeypatch):
    from cryptoquant.models import research_gates as gates
    root, cfg = scope
    folder, run = synthetic_evaluation(root, cfg, 'EXP-850')
    result = {'do_not_run_R2025': False}
    saved = dict(experiment_id='EXP-850', prepared_experiment_id='EXP-063', selection_results=result,
                 do_not_run_R2025=False)
    (folder / 'selection_summary.json').write_text(json.dumps(saved), encoding='utf-8')
    run['artifacts']['selection_summary.json'] = sha_file(folder / 'selection_summary.json')
    monkeypatch.setattr(gates, 'verify_completed_experiment', lambda *a: (folder, run))
    monkeypatch.setattr(gates, 'collect_base_candidates', lambda *a: ({}, {'EXP-800': {'run_manifest_sha256': 'f' * 64}}))
    monkeypatch.setattr(gates, 'evaluate_research_candidates', lambda *a: result)
    with pytest.raises(ValueError, match='input manifest SHA'):
        gates.verify_fifth_selection(root, 'EXP-850', cfg, 'EXP-063')


def test_registered_failed_candidates_are_reported_and_ineligible(scope):
    from cryptoquant.models.research_reporting import evaluate_research_candidates
    from cryptoquant.models.research_workflow import generate_select_report
    from cryptoquant.models.research_reporting import evaluate_three_tier_conclusions
    _, cfg = scope
    rows = {(p, w, t): dict(status='failed', experiment_id=f'EXP-{800+i}', error='synthetic failure')
            for i, (p, w, t) in enumerate((p, w, t) for p in (NET_POLICY, GROSS_POLICY)
                                         for w in ('W1', 'W2') for t in (.4, .5, .6, .64))}
    result = evaluate_research_candidates(rows, cfg)
    assert result['do_not_run_R2025'] is True
    assert len(result[NET_POLICY]['all_candidates']) == 4
    report = generate_select_report(dict(experiment_id='EXP-900', selection_results=result,
                                    three_tier_conclusions=evaluate_three_tier_conclusions(result),
                                    do_not_run_R2025=True), cfg)
    assert 'synthetic failure' in report and '不合格' in report


@pytest.mark.parametrize('fault', ['profile', 'config_sha', 'prepared_id', 'prepared_sha'])
def test_new_ablation_selection_requires_own_config_and_parent_binding(scope, monkeypatch, fault):
    from cryptoquant.models import research_gates as gates
    root, fifth = scope
    sixth = load_research_config(root / 'configs/sixth_experiment.toml', root)
    folder, run = synthetic_evaluation(root, sixth, 'EXP-850')
    prepared_folder = root / 'artifacts/experiments/EXP-063'
    prepared_folder.mkdir(parents=True)
    (prepared_folder / 'prepared_manifest.json').write_text('{}', encoding='utf-8')
    run['prepared_manifest_sha256'] = sha_file(prepared_folder / 'prepared_manifest.json')
    run['type'] = 'ablation_selection_and_freeze'
    (folder / 'evaluation.json').write_text('{}', encoding='utf-8')
    run['artifacts']['evaluation.json'] = sha_file(folder / 'evaluation.json')
    if fault == 'profile':
        shutil.copyfile(fifth.research_config_path, folder / 'research_config.toml')
        run['research_config_hash'] = fifth.research_config_hash
        run['artifacts']['research_config.toml'] = fifth.research_config_hash
    elif fault == 'config_sha':
        run['artifacts']['config.toml'] = '0' * 64
    elif fault == 'prepared_id':
        run['prepared_experiment_id'] = 'EXP-064'
    else:
        run['prepared_manifest_sha256'] = '0' * 64
    monkeypatch.setattr(gates, 'verify_completed_experiment', lambda *a: (folder, run))
    monkeypatch.setattr(gates, 'verify_prepared', lambda *a: ({}, {}))
    with pytest.raises(ValueError, match='profile|config hash|prepared'):
        gates.verify_ablation_selection(root, 'EXP-850', sixth, 'EXP-063')


def test_comparison_report_displays_actual_qualified_thresholds(scope):
    from cryptoquant.models.research_workflow import generate_compare_report
    _, cfg = scope
    selection = {GROSS_POLICY: dict(status='qualified_and_selected', selected_threshold=.4, is_reference_only=False),
                 NET_POLICY: dict(status='qualified_and_selected', selected_threshold=.6, is_reference_only=False)}
    conclusions = dict(method_valid=False, method_valid_details='未验收', relative_improvement=False,
                       relative_improvement_reasons=[], target_achieved=False, target_achieved_reasons=[])
    report = generate_compare_report(dict(experiment_id='EXP-900', selection_results=selection,
                                     final_conclusions=conclusions, evaluated_summaries={}), cfg)
    assert f'`{GROSS_POLICY}`：T=0.4' in report
    assert f'`{NET_POLICY}`：T=0.6' in report
    assert 'qualified_and_selected' in report and 'is_reference_only=False' in report
    assert '对照阈值 T=0.64' not in report and '冻结阈值 T=0.50' not in report

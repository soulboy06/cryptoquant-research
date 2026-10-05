"""第七轮有限入口：只用临时冻结产物和小合成账户，不运行正式研究。"""
import json
import shutil
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from cryptoquant.cli import write_json
from cryptoquant.data.archive import sha_file
from cryptoquant.models.research_config import load_research_config

ROOT = Path(__file__).resolve().parents[1]


def config(tmp_path):
    shutil.copytree(ROOT / 'configs', tmp_path / 'configs')
    return load_research_config(tmp_path / 'configs/seventh_experiment.toml', tmp_path)


def attempt(root, cfg, identifier, status='failed', kind='regime_evaluation', window='W1', cost='base', state='EXP-900'):
    folder = root / 'artifacts/experiments' / identifier
    folder.mkdir(parents=True)
    (folder / 'research_config.toml').write_bytes(cfg.research_config_path.read_bytes())
    (folder / 'config.toml').write_bytes(cfg.execution_config_path.read_bytes())
    write_json(folder / 'run_manifest.json', dict(experiment_id=identifier, type=kind, status=status,
               research_config_hash=cfg.research_config_hash, execution_config_hash=cfg.execution_config_hash,
               window=window, cost=cost, regime_variant='R1', state_experiment_id=state))
    return folder


def rows(returns=('.05', '.25', '-.01'), dd=('.05', '.05', '.10')):
    return {name: dict(window=name, status='complete', net_return=r, max_drawdown=d,
                       floor_triggers=0, closed_cycles=30, total_window_hours=h)
            for name, r, d, h in zip(('W1', 'W2', 'R2025'), returns, dd, (8760, 8784, 8756))}


def test_budget_failed_retry_and_running_duplicate_new_state_cannot_reset(tmp_path):
    from cryptoquant.models.regime_gates import enforce_regime_budget
    cfg = config(tmp_path)
    attempt(tmp_path, cfg, 'EXP-901')
    renamed = tmp_path / 'configs/renamed.toml'
    renamed.write_bytes(cfg.research_config_path.read_bytes())
    cfg = load_research_config(renamed, tmp_path)
    assert enforce_regime_budget(tmp_path, cfg, 'regime_evaluation', ('W1', 'base', 'R1'))['accounts_used'] == 1
    attempt(tmp_path, cfg, 'EXP-910', status='complete')
    with pytest.raises(ValueError, match='duplicate'):
        enforce_regime_budget(tmp_path, cfg, 'regime_evaluation', ('W1', 'base', 'R1'))
    for i in range(902, 909):
        attempt(tmp_path, cfg, f'EXP-{i}', status='running', window='W2', state='EXP-999')
    with pytest.raises(ValueError, match='account budget exhausted'):
        enforce_regime_budget(tmp_path, cfg, 'regime_evaluation', ('R2025', 'strict', 'R1'))


def test_total_budget_includes_preparation_and_reports(tmp_path):
    from cryptoquant.models.regime_gates import enforce_regime_budget
    cfg = config(tmp_path)
    for i in range(900, 912):
        attempt(tmp_path, cfg, f'EXP-{i}', kind='regime_preparation')
    with pytest.raises(ValueError, match='total budget exhausted'):
        enforce_regime_budget(tmp_path, cfg, 'regime_selection')


def test_exact_base_and_pressure_thresholds_and_incomplete_matrices():
    from cryptoquant.models.regime_reporting import evaluate_base, evaluate_pressure, combined_weekly
    r0 = rows(('.042', '.266', '-.129'), ('.066', '.058', '.162'))
    good = rows()
    assert evaluate_base(good, r0)['eligible']
    assert combined_weekly(good) > combined_weekly(r0)
    good['W2']['net_return'] = '.1999999999999999999999'
    result = evaluate_base(good, r0)
    assert not result['eligible'] and 'W2:net_return>=0.20' in result['failed_checks']
    with pytest.raises(ValueError, match='complete three-window'):
        evaluate_base({'W1': good['W1']}, r0)
    strict = rows(('.01', '.149816541437466', '-.10'), ('.08', '.06', '.20'))
    r0_strict = rows(('.006', '.149816541437466', '-.23'), ('.08', '.06', '.254'))
    result = evaluate_pressure(strict, r0_strict, 'strict')
    assert not result['passed'] and 'W2:net_return>=0.15' in result['failed_checks']
    good = rows()
    good['R2025'] = dict(status='failed', error='input failure')
    assert not evaluate_base(good, r0)['eligible']


def test_cli_has_fixed_regime_parameters_and_dispatches(monkeypatch):
    from cryptoquant import cli
    from cryptoquant.models import regime_workflow
    seen = []
    monkeypatch.setattr(regime_workflow, 'execute_regime_evaluate', lambda args, root: seen.append(args) or 0)
    assert cli.main(['regime-evaluate', '--research-config', 'configs/seventh_experiment.toml',
                     '--state-experiment-id', 'EXP-900', '--window', 'W1', '--experiment-id', 'EXP-901']) == 0
    assert seen[0].cost == 'base' and seen[0].selection_experiment_id is None
    with pytest.raises(SystemExit):
        cli.main(['regime-evaluate', '--research-config', 'configs/seventh_experiment.toml',
                  '--state-experiment-id', 'EXP-900', '--window', 'W1', '--experiment-id', 'EXP-901', '--threshold', '.4'])


def test_bad_state_or_model_rejected_before_market_or_new_directory(tmp_path, monkeypatch):
    from cryptoquant.models import regime_workflow as workflow
    cfg = config(tmp_path)
    (tmp_path / 'EXPERIMENTS.md').write_text('| EXP-901 | pending |', encoding='utf-8')
    args = SimpleNamespace(research_config=cfg.research_config_path, state_experiment_id='EXP-900',
                           window='W1', cost='base', experiment_id='EXP-901', selection_experiment_id=None)
    def invalid(*args):
        raise ValueError('state parent/model SHA mismatch')
    monkeypatch.setattr(workflow, 'preflight', invalid)
    monkeypatch.setattr(workflow, 'load_period', lambda *args: pytest.fail('preflight must precede market'))
    with pytest.raises(ValueError, match='SHA mismatch'):
        workflow.execute_regime_evaluate(args, tmp_path)
    assert not (tmp_path / 'artifacts/experiments/EXP-901').exists()


def test_pressure_without_eligible_selection_is_rejected_pre_start(tmp_path, monkeypatch):
    from cryptoquant.models import regime_workflow as workflow
    cfg = config(tmp_path)
    (tmp_path / 'EXPERIMENTS.md').write_text('| EXP-901 | pending |', encoding='utf-8')
    args = SimpleNamespace(research_config=cfg.research_config_path, state_experiment_id='EXP-900',
                           window='W1', cost='strict', experiment_id='EXP-901', selection_experiment_id=None)
    monkeypatch.setattr(workflow, 'preflight', lambda *args: {})
    monkeypatch.setattr(workflow, 'load_period', lambda *args: pytest.fail('pressure cannot start'))
    with pytest.raises(ValueError, match='selection'):
        workflow.execute_regime_evaluate(args, tmp_path)
    args.selection_experiment_id = 'EXP-902'
    monkeypatch.setattr(workflow, 'verify_regime_selection', lambda *args: {'result': {'eligible': False}})
    with pytest.raises(ValueError, match='eligible'):
        workflow.execute_regime_evaluate(args, tmp_path)
    assert not (tmp_path / 'artifacts/experiments/EXP-901').exists()


def test_started_failure_retains_full_command_frozen_config_and_budget(tmp_path, monkeypatch):
    from cryptoquant.models import regime_workflow as workflow
    from cryptoquant.models.regime_gates import audit_regime_budget
    cfg = config(tmp_path)
    (tmp_path / 'EXPERIMENTS.md').write_text('| EXP-901 | pending |', encoding='utf-8')
    context = dict(state=dict(state_manifest_sha256='a' * 64, state_run_manifest_sha256='b' * 64,
                              sources={'fixture': 'verified'}, tables={'W1': pd.DataFrame()}, run={}),
                   r0=dict(inputs=[], matrix={}))
    monkeypatch.setattr(workflow, 'preflight', lambda *args: context)
    def failed(*args):
        raise ValueError('synthetic input failed after start')
    monkeypatch.setattr(workflow, 'load_period', failed)
    args = SimpleNamespace(research_config=cfg.research_config_path, state_experiment_id='EXP-900',
                           window='W1', cost='base', experiment_id='EXP-901', selection_experiment_id=None)
    with pytest.raises(ValueError, match='synthetic input'):
        workflow.execute_regime_evaluate(args, tmp_path)
    folder = tmp_path / 'artifacts/experiments/EXP-901'
    run = json.loads((folder / 'run_manifest.json').read_text('utf-8'))
    assert run['status'] == 'failed' and (folder / 'research_config.toml').exists()
    assert run['command'] == ['.venv/Scripts/python.exe', '-m', 'cryptoquant', 'regime-evaluate',
            '--research-config', str(cfg.research_config_path), '--state-experiment-id', 'EXP-900',
            '--window', 'W1', '--cost', 'base', '--experiment-id', 'EXP-901']
    assert run['artifacts']['failure.json'] == sha_file(folder / 'failure.json')
    assert audit_regime_budget(tmp_path, cfg)['accounts_used'] == 1
    from cryptoquant.models.regime_gates import verify_regime_evaluation
    context['state']['state_experiment_id'] = 'EXP-900'
    run['training_experiment_id'] = 'EXP-067'
    write_json(folder / 'run_manifest.json', run)
    with pytest.raises(ValueError, match='fixed model/window'):
        verify_regime_evaluation(tmp_path, 'EXP-901', cfg, context, allow_failed=True)


def test_state_table_rejects_future_missing_boolean_conflict_and_bad_history():
    from cryptoquant.models.regime_gates import _state_table
    clock = pd.date_range('2023-01-01', periods=3, freq='4h', tz='UTC')
    frame = pd.DataFrame(dict(decision_time=clock, available_time=clock, adx14=25., ema72=100.,
                              slope24=.01, history_count=800, state_valid=True, allow_buy=True))
    _state_table(frame)
    for column, value in [('available_time', clock[-1]), ('allow_buy', False), ('history_count', 800.5), ('state_valid', 1)]:
        bad = frame.copy()
        if column == 'state_valid':
            bad[column] = value
        else:
            if column == 'history_count':
                bad[column] = bad[column].astype(float)
            bad.loc[0, column] = value
        with pytest.raises(ValueError):
            _state_table(bad)
    with pytest.raises(ValueError, match='clock'):
        _state_table(frame.iloc[[0, 2]])


def test_missing_data_evidence_and_missing_budget_execution_hash_fail(tmp_path):
    from cryptoquant.models.regime_gates import verify_data_evidence, audit_regime_budget
    cfg = config(tmp_path)
    for evidence in ({}, {'data_experiment_id': 'EXP-003', 'period': 'development', 'partitions': {}},
                     {'data_experiment_id': 'EXP-003', 'period': 'validation', 'partitions': dict.fromkeys(cfg.execution_config.symbols)}):
        with pytest.raises(ValueError, match='exactly three symbols'):
            verify_data_evidence(tmp_path, cfg, evidence, 'development')
    folder = attempt(tmp_path, cfg, 'EXP-901')
    run = json.loads((folder / 'run_manifest.json').read_text('utf-8'))
    del run['execution_config_hash']
    write_json(folder / 'run_manifest.json', run)
    with pytest.raises(ValueError, match='execution configuration SHA'):
        audit_regime_budget(tmp_path, cfg)


def test_selection_recomputes_ineligible_result_and_compare_requires_full_matrix(tmp_path, monkeypatch):
    from cryptoquant.models import regime_workflow as workflow, regime_gates as gates
    cfg = config(tmp_path)
    (tmp_path / 'EXPERIMENTS.md').write_text('| EXP-910 | selection |\n| EXP-911 | comparison |', encoding='utf-8')
    state = dict(state_experiment_id='EXP-900', state_manifest_sha256='a'*64,
                 state_run_manifest_sha256='b'*64, sources={'fixed': True})
    r0 = rows(('.042', '.266', '-.129'), ('.066', '.058', '.162'))
    context = dict(state=state, r0=dict(matrix={'base': r0}, inputs=[]))
    bad = rows(('.02', '.19999999999', '-.01'))
    matrix = {(w, 'base'): bad[w] for w in bad}
    inputs = [dict(experiment_id=f'EXP-{901+i}', sha='fixture') for i in range(3)]
    monkeypatch.setattr(workflow, 'preflight', lambda *args: context)
    monkeypatch.setattr(workflow, 'collect_regime_matrix', lambda *args: (matrix, inputs))
    monkeypatch.setattr(gates, 'collect_regime_matrix', lambda *args: (matrix, inputs))
    args = SimpleNamespace(research_config=cfg.research_config_path, state_experiment_id='EXP-900',
                           base_experiment_ids=['EXP-901','EXP-902','EXP-903'], experiment_id='EXP-910')
    assert workflow.execute_regime_select(args, tmp_path) == 0
    result = gates.verify_regime_selection(tmp_path, 'EXP-910', cfg, context)
    assert not result['result']['eligible']
    folder = tmp_path / 'artifacts/experiments/EXP-910'
    data = json.loads((folder / 'selection.json').read_text('utf-8'))
    data['result']['eligible'] = True
    write_json(folder / 'selection.json', data)
    run = json.loads((folder / 'run_manifest.json').read_text('utf-8'))
    run['artifacts']['selection.json'] = sha_file(folder / 'selection.json')
    write_json(folder / 'run_manifest.json', run)
    with pytest.raises(ValueError, match='qualification mismatch'):
        gates.verify_regime_selection(tmp_path, 'EXP-910', cfg, context)
    monkeypatch.undo()
    with pytest.raises(ValueError, match='unique complete'):
        gates.collect_regime_matrix(tmp_path, ['EXP-901'], cfg, context, {(w, 'base') for w in bad})


def test_small_account_producer_saved_artifacts_consumer_and_tamper(tmp_path, monkeypatch):
    from dataclasses import replace
    from test_baseline_engine import fixture
    from cryptoquant.models import regime_workflow as workflow, regime_gates as gates, research_config
    from cryptoquant.models.research_integrity import verify_completed_experiment
    frames, rules, execution = fixture(hours=16)
    cfg = replace(config(tmp_path), execution_config=execution)
    (tmp_path / 'EXPERIMENTS.md').write_text('| EXP-901 | pending |', encoding='utf-8')
    window = SimpleNamespace(start=execution.development_start, end=execution.development_end, period='development')
    for module in (workflow, gates, research_config):
        monkeypatch.setattr(module, 'RESEARCH_WINDOWS', {'W1': window})
    times = pd.date_range(window.start, window.end, freq='4h', inclusive='left')
    state = pd.DataFrame(dict(decision_time=times, available_time=times, adx14=25., ema72=100., slope24=.01,
                              history_count=800, state_valid=True, allow_buy=[False, True, False, False]))
    data = dict(synthetic='16h, no archive read')
    context = dict(state=dict(state_experiment_id='EXP-900', state_manifest_sha256='a'*64,
              state_run_manifest_sha256='b'*64, sources={'fixture': 'preverified'}, tables={'W1': state}, run={'data': {'development': data}}),
              r0=dict(inputs=[], matrix={}))
    probs = pd.DataFrame([dict(symbol=symbol, decision_time=time, probability=.9 if i < 3 else .1)
                           for i, time in enumerate(times) for symbol in execution.symbols])
    monkeypatch.setattr(workflow, 'load_research_config', lambda *args: cfg)
    monkeypatch.setattr(workflow, 'preflight', lambda *args: context)
    monkeypatch.setattr(workflow, 'load_period', lambda *args: (frames, rules, data))
    monkeypatch.setattr(workflow, 'window_frames', lambda frames, *args: frames)
    monkeypatch.setattr(workflow, 'load_research_features', lambda *args: ({}, {}))
    monkeypatch.setattr(workflow, 'load_research_models', lambda *args, **kwargs: ({}, {'verified_source': {'synthetic': True}}))
    monkeypatch.setattr(workflow, 'build_window_probabilities', lambda *args, **kwargs: probs)
    args = SimpleNamespace(research_config=cfg.research_config_path, state_experiment_id='EXP-900',
                           window='W1', cost='base', experiment_id='EXP-901', selection_experiment_id=None)
    assert workflow.execute_regime_evaluate(args, tmp_path) == 0
    folder, run = verify_completed_experiment(tmp_path, 'EXP-901', 'regime_evaluation')
    row, evidence = gates.verify_regime_evaluation(tmp_path, 'EXP-901', cfg, context)
    assert row['regime_blocked_records'] == row['regime_blocked_positive_quantity_records'] == 3
    assert row['regime_blocked_zero_quantity_records'] == 0
    assert row['floor_triggers'] == 0 and row['closed_cycles'] == 3
    assert Decimal(row['fees_usdt']) > 0 and len(pd.read_csv(folder / 'fills.csv')) == 6
    assert evidence['summary_sha256'] == sha_file(folder / 'summary.json')
    # File bytes changed without updating the input SHA must fail before reuse.
    (folder / 'summary.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='SHA mismatch'):
        gates.verify_regime_evaluation(tmp_path, 'EXP-901', cfg, context)


def test_state_producer_consumer_model_binding_and_rehashed_slice_tamper(tmp_path, monkeypatch):
    from test_market_regime import candles
    from cryptoquant.models import regime_workflow as workflow, regime_gates as gates
    cfg = config(tmp_path)
    (tmp_path / 'EXPERIMENTS.md').write_text('| EXP-900 | state |\n| EXP-901 | failed state |', encoding='utf-8')
    source_path = tmp_path / 'configs/sixth_experiment.toml'
    sources = dict(source_research_config_path=str(source_path), source_research_config_hash=sha_file(source_path),
                   prepared_experiment_id='EXP-063', models={'fixture': 'verified'})
    monkeypatch.setattr(workflow, '_verify_regime_sources', lambda *args: sources)
    clock = pd.date_range('2021-12-01', '2025-12-31T19:00:00', freq='h', tz='UTC')
    history = candles('2021-12-01', len(clock))
    no_trade = history.open_time.eq(pd.Timestamp('2023-03-24T12:00:00Z'))
    halt = history.open_time.eq(pd.Timestamp('2023-03-24T13:00:00Z'))
    history.loc[no_trade, 'market_state'] = 'no_trade'
    history.loc[halt, 'market_state'] = 'halt'
    history.loc[halt, ['open', 'high', 'low', 'close']] = float('nan')
    history.loc[halt, 'available_time'] = pd.NaT
    monkeypatch.setattr(workflow, 'load_regime_history', lambda *args: (history, {'development': {'fixture': True}, 'validation': {'fixture': True}}))
    monkeypatch.setattr(gates, 'verify_data_evidence', lambda *args: None)
    args = SimpleNamespace(research_config=cfg.research_config_path, data_experiment_id='EXP-003',
                           prepared_experiment_id='EXP-063', experiment_id='EXP-900')
    assert workflow.execute_regime_prepare(args, tmp_path) == 0
    result = gates.verify_state(tmp_path, 'EXP-900', cfg)
    assert result['tables']['W2'].history_count.iloc[0] > 744
    monkeypatch.setattr(workflow, '_verify_regime_sources', lambda *args: dict(sources, models={'fixture': 'changed'}))
    with pytest.raises(ValueError, match='parent/model/prepared SHA'):
        gates.verify_state(tmp_path, 'EXP-900', cfg)
    monkeypatch.setattr(workflow, '_verify_regime_sources', lambda *args: sources)
    folder = tmp_path / 'artifacts/experiments/EXP-900'
    run = json.loads((folder / 'run_manifest.json').read_text('utf-8'))
    item = run['states']['W1']
    path = folder / item['path']
    table = pd.read_parquet(path)
    table.loc[0, 'ema72'] += 1
    table.to_parquet(path, index=False)
    item['sha256'] = sha_file(path)
    run['artifacts'][path.name] = item['sha256']
    child = json.loads((folder / 'state_manifest.json').read_text('utf-8'))
    child['states'] = run['states']
    child['artifacts'][path.name] = item['sha256']
    write_json(folder / 'state_manifest.json', child)
    run['artifacts']['state_manifest.json'] = sha_file(folder / 'state_manifest.json')
    write_json(folder / 'run_manifest.json', run)
    with pytest.raises(ValueError, match='slice mismatch'):
        gates.verify_state(tmp_path, 'EXP-900', cfg)
    args.experiment_id = 'EXP-901'
    def failed_snapshot(*args):
        raise ValueError('snapshot failure')
    monkeypatch.setattr(workflow, 'snapshot_source', failed_snapshot)
    with pytest.raises(ValueError, match='snapshot failure'):
        workflow.execute_regime_prepare(args, tmp_path)
    assert (tmp_path / 'artifacts/experiments/EXP-901/research_config.toml').is_file()

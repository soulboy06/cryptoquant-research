"""验证新期间、冻结预测、离线入口及预定筛选规则。"""

from dataclasses import replace
from decimal import Decimal as D
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

from cryptoquant.baselines.engine import run_backtest
from cryptoquant.baselines.reporting import summarize
from cryptoquant.cli import main, write_json
from cryptoquant.config import load_config
from cryptoquant.data.archive import sha_file
from cryptoquant.data.workflow import environment
from cryptoquant.models.features import FEATURE_NAMES
from cryptoquant.models.training import C_VALUES, fit_model
from test_baseline_engine import fixture
from test_baseline_workflow import fake_data
from test_model_training import samples

CONFIG = Path(__file__).resolve().parents[1] / 'configs/first_experiment.toml'


def validation_fixture():
    frames, rules, short = fixture(rising=True)
    original = load_config(CONFIG)
    start = pd.Timestamp(original.validation_end) - pd.Timedelta(24, unit='h')
    shift = start - pd.Timestamp(short.development_start)
    config = replace(original, development_end=start.to_pydatetime(), validation_start=start.to_pydatetime())
    for frame in frames.values():
        frame['open_time'] += shift
        frame['available_time'] += shift
        frame['quote_volume'] = np.where(frame.row_role == 'boundary', np.nan, 100.)
    return frames, rules, config


def validation_data(root):
    frames, _, config = validation_fixture()
    path = fake_data(root, frames, config)
    config = load_config(path)
    folder = root / 'artifacts/experiments/EXP-001'
    quality_path = folder / 'quality_report.json'
    quality = json.loads(quality_path.read_text('utf-8'))
    parts = {}
    for symbol, frame in frames.items():
        target = root / 'data/processed/validation/EXP-001' / (symbol + '.parquet')
        target.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(target, index=False)
        parts[symbol] = dict(path=str(target), sha256=sha_file(target))
    quality['partitions']['validation'] = parts
    write_json(quality_path, quality)
    state_path = folder / 'step_state.json'
    state = json.loads(state_path.read_text('utf-8'))
    state['steps']['check-data']['result']['quality_report_sha256'] = sha_file(quality_path)
    write_json(state_path, state)
    return frames, config, path


def frozen_models(root, config):
    folder = root / 'artifacts/experiments/EXP-007'
    (folder / 'models').mkdir(parents=True)
    manifest = dict(experiment_id='EXP-007', type='model_training', status='complete', period='development',
                    config_hash=config.config_hash, feature_names=FEATURE_NAMES,
                    start_utc=config.development_start, label_end_before_utc=config.development_end,
                    source_hash='synthetic-training', environment=environment(), models=[])
    for C in C_VALUES:
        for symbol in config.symbols:
            model = fit_model(samples(symbol), C)
            path = folder / 'models' / f'{symbol}_C-{C:g}.joblib'
            joblib.dump(model, path)
            manifest['models'].append(dict(symbol=symbol, C=C, status='complete', samples=80,
                                          model_path=path.relative_to(folder).as_posix(), model_sha256=sha_file(path), reload_verified=True))
    write_json(folder / 'train_manifest.json', manifest)


def test_period_interface_preserves_execution_and_terminal_fees():
    frames, rules, config = validation_fixture()
    result = run_backtest(frames, rules, config, 'buy_hold', 'base', period='validation')
    # Express the same targets through the external interface and compare fills.
    times = pd.date_range(config.validation_start, config.validation_end, freq='4h', inclusive='left')
    targets = pd.DataFrame([dict(symbol=s, decision_time=t, probability=.9 if t == times[0] else None,
                                 target_weight=config.weight_per_symbol if t == times[0] else None)
                            for t in times for s in config.symbols])
    external = run_backtest(frames, rules, config, 'logistic_regression', 'base', period='validation', decision_targets=targets)
    assert result.fills == external.fills
    assert result.book.equity(result.marks) == external.book.equity(external.marks)
    summary, annual = summarize(external, config)
    assert summary['start_utc'] == config.validation_start and summary['end_utc'] == config.validation_end
    assert summary['fees_usdt'] == sum(fill['fee_usdt'] for fill in external.fills)
    assert annual[-1]['end_equity'] == summary['final_equity']
    assert external.equity[-1]['time'] == config.validation_end and external.equity[-1]['phase'] == 'terminal'
    with pytest.raises(ValueError, match='period'):
        run_backtest(frames, rules, config, 'buy_hold', 'base', period='test')
    with pytest.raises(ValueError, match='columns'):
        run_backtest(frames, rules, config, 'logistic_regression', 'base', period='validation', decision_targets=targets.assign(label=1))


def test_frozen_probabilities_targets_and_future_candle_isolation():
    from cryptoquant.models.predictions import build_probabilities, decision_targets
    frames, _, config = validation_fixture()
    models = {s: fit_model(samples(s), .1) for s in config.symbols}
    probabilities = build_probabilities(frames, models, config.validation_start, config.validation_end)
    targets = decision_targets(probabilities, .55, config.weight_per_symbol)
    assert list(targets.columns) == ['symbol', 'decision_time', 'probability', 'target_weight']
    first = targets[targets.decision_time == config.validation_start].reset_index(drop=True)
    for frame in frames.values():
        mask = (frame.open_time >= config.validation_start) & (frame.row_role != 'boundary')
        frame.loc[mask, ['close', 'high', 'low']] = '1'
        frame.loc[mask, 'quote_volume'] = 1e9
    changed = decision_targets(build_probabilities(frames, models, config.validation_start, config.validation_end), .55, config.weight_per_symbol)
    pd.testing.assert_frame_equal(first, changed[changed.decision_time == config.validation_start].reset_index(drop=True))
    probabilities.loc[0, 'probability'] = np.nan
    assert decision_targets(probabilities, .55, config.weight_per_symbol).iloc[0].target_weight is None


def test_validation_cli_reads_only_validation_never_fits_and_preserves_id(tmp_path, monkeypatch):
    from sklearn.pipeline import Pipeline
    _, config, config_path = validation_data(tmp_path)
    frozen_models(tmp_path, config)
    read = pd.read_parquet
    seen = []
    def guarded(path, *args, **kwargs):
        assert 'validation' in Path(path).parts
        seen.append(path)
        return read(path, *args, **kwargs)
    monkeypatch.setattr(pd, 'read_parquet', guarded)
    monkeypatch.setattr(Pipeline, 'fit', lambda *a, **k: pytest.fail('validation must never refit'))
    import requests
    monkeypatch.setattr(requests, 'Session', lambda: pytest.fail('offline validation attempted network'))
    monkeypatch.chdir(tmp_path)
    args = ['validate', '--config', str(config_path), '--data-experiment-id', 'EXP-001', '--training-experiment-id', 'EXP-007',
            '--C', '.1', '--threshold', '.55', '--cost', 'base', '--experiment-id', 'EXP-008']
    assert main(args) == 0
    output = tmp_path / 'artifacts/experiments/EXP-008'
    manifest = json.loads((output / 'run_manifest.json').read_text('utf-8'))
    assert manifest['status'] == 'complete' and manifest['period'] == 'validation' and len(seen) == 3
    summary = json.loads((output / 'summary.json').read_text('utf-8'))
    assert pd.Timestamp(summary['end_utc']) == config.validation_end
    signals = pd.read_csv(output / 'decision_targets.csv')
    assert 'label' not in signals.columns
    diagnostics = pd.read_csv(output / 'validation_labels.csv')
    assert pd.to_datetime(diagnostics.label_end, utc=True).max() <= config.validation_end
    assert main(args) == 1


def test_selection_applies_gate_and_deterministic_tie_order():
    from cryptoquant.models.selection import select_candidate
    def candidate(C, threshold, **overrides):
        summary = dict(period='validation', cost='base', final_equity='120', net_return='.2', max_drawdown='.1',
                       turnover_usdt='100', floor_triggers=0, closed_cycles=30)
        summary.update(overrides)
        return dict(experiment_id=f'{C}/{threshold}', C=C, threshold=threshold, summary=summary)
    rows = [candidate(1., .65), candidate(.1, .55), candidate(.1, .65), candidate(10., .65),
            candidate(.1, .6, final_equity='150', max_drawdown='.4')]
    selection = select_candidate(rows)
    assert selection['selected']['C'] == .1 and selection['selected']['threshold'] == .65
    failed = select_candidate([candidate(1., .55, closed_cycles=29)])
    assert failed['selected'] is None and failed['candidates'][0]['qualified'] is False
    with pytest.raises(ValueError, match='base validation'):
        select_candidate([candidate(1., .55, cost='strict')])

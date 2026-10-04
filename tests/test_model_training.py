"""仅验证训练隔离、失败处理和离线持久化入口。"""

import json
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import pytest

from cryptoquant.cli import main, write_json
from cryptoquant.config import load_config
from cryptoquant.data.archive import sha_file
from cryptoquant.models.features import FEATURE_NAMES, HOUR

CONFIG = Path(__file__).resolve().parents[1] / 'configs/first_experiment.toml'


def samples(symbol='BTCUSDT'):
    rng = np.random.default_rng(42)
    frame = pd.DataFrame(rng.normal(size=(80, 9)), columns=FEATURE_NAMES)
    frame['label'] = (frame.return_1h + rng.normal(size=80) > 0).astype('int64')
    frame['symbol'] = symbol
    frame['decision_time'] = pd.date_range('2022-01-01', periods=80, freq='4h', tz='UTC')
    frame['feature_open_time'] = frame.decision_time - HOUR
    frame['feature_available_time'] = frame.decision_time
    frame['source_id'] = 'synthetic-test'
    frame['history_count'] = 744
    frame['label_start'] = frame.decision_time
    frame['label_end'] = frame.decision_time + 4 * HOUR
    frame['label_return'] = np.where(frame.label == 1, .01, -.01)
    return frame


def sample_experiment(root):
    config = load_config(CONFIG)
    folder = root / 'artifacts/experiments/EXP-006'
    (folder / 'training_samples').mkdir(parents=True)
    manifest = dict(experiment_id='EXP-006', type='training_samples', status='complete',
                    config_hash=config.config_hash, period='development', feature_names=FEATURE_NAMES,
                    start_utc=config.development_start, label_end_before_utc=config.development_end,
                    source_hash='synthetic-test', symbols={})
    for symbol in config.symbols:
        frame = samples(symbol)
        path = folder / 'training_samples' / (symbol + '.parquet')
        frame.to_parquet(path, index=False)
        manifest['symbols'][symbol] = dict(samples=len(frame), samples_path=str(path.resolve()),
                                          samples_sha256=sha_file(path), label_1=int(frame.label.sum()),
                                          label_0=int((frame.label == 0).sum()))
    write_json(folder / 'sample_manifest.json', manifest)
    return folder


def test_predictions_do_not_fit_on_future_or_consume_labels():
    from cryptoquant.models.training import fit_model, predict_probabilities
    train = samples()
    model = fit_model(train, 1.)
    scaler = model.named_steps['scaler']
    np.testing.assert_allclose(scaler.mean_, train[FEATURE_NAMES].mean().to_numpy())
    before = scaler.mean_.copy(), model.named_steps['classifier'].coef_.copy()
    future = train.copy()
    future.loc[40:, FEATURE_NAMES] = 1e6
    future['label'] = 1 - future.label
    future['label_return'] = 1e10
    future['decision_time'] += pd.Timedelta(1461, unit='d')
    expected = predict_probabilities(model, train.iloc[:40])
    actual = predict_probabilities(model, future)
    np.testing.assert_array_equal(expected, actual[:40])
    for threshold in [.55, .60, .65]:
        np.testing.assert_array_equal(expected >= threshold, actual[:40] >= threshold)
    np.testing.assert_array_equal(scaler.mean_, before[0])
    np.testing.assert_array_equal(model.named_steps['classifier'].coef_, before[1])
    assert scaler.n_samples_seen_ == 80


def test_single_class_and_nonconvergence_are_failures(monkeypatch):
    from cryptoquant.models.training import fit_model
    from sklearn.exceptions import ConvergenceWarning
    from sklearn.linear_model import LogisticRegression
    frame = samples()
    with pytest.raises(ValueError, match='both classes'):
        fit_model(frame.assign(label=1), 1.)
    def fail_fit(*args, **kwargs):
        warnings.warn('synthetic nonconvergence', ConvergenceWarning)
    monkeypatch.setattr(LogisticRegression, 'fit', fail_fit)
    with pytest.raises(ConvergenceWarning):
        fit_model(frame, 1.)


def test_offline_train_saves_nine_usable_models(tmp_path, monkeypatch):
    import joblib
    import requests
    from cryptoquant.models.training import predict_probabilities
    sample_experiment(tmp_path)
    real_read = pd.read_parquet
    read_paths = []
    def training_only(path, *args, **kwargs):
        assert Path(path).parent.name == 'training_samples'
        read_paths.append(Path(path))
        return real_read(path, *args, **kwargs)
    monkeypatch.setattr(pd, 'read_parquet', training_only)
    monkeypatch.setattr(requests, 'Session', lambda: pytest.fail('train must be offline'))
    monkeypatch.chdir(tmp_path)
    args = ['train', '--config', str(CONFIG), '--sample-experiment-id', 'EXP-006', '--experiment-id', 'EXP-007']
    assert main(args) == 0
    output = tmp_path / 'artifacts/experiments/EXP-007'
    manifest = json.loads((output / 'train_manifest.json').read_text(encoding='utf-8'))
    assert manifest['status'] == 'complete' and len(manifest['models']) == 9
    assert len(read_paths) == 3
    assert {item['C'] for item in manifest['models']} == {.1, 1., 10.}
    for item in manifest['models']:
        saved = joblib.load(output / item['model_path'])
        np.testing.assert_array_equal(predict_probabilities(saved, samples(item['symbol'])),
                                      pd.read_csv(output / item['probabilities_path'], float_precision='round_trip').probability.to_numpy())
        assert item['reload_verified'] is True
    assert main(args) == 1


def test_tampered_training_input_preserves_failed_experiment(tmp_path, monkeypatch):
    folder = sample_experiment(tmp_path)
    with (folder / 'training_samples/BTCUSDT.parquet').open('ab') as stream:
        stream.write(b'tampered')
    monkeypatch.chdir(tmp_path)
    assert main(['train', '--config', str(CONFIG), '--experiment-id', 'EXP-007']) == 1
    output = tmp_path / 'artifacts/experiments/EXP-007'
    manifest = json.loads((output / 'train_manifest.json').read_text(encoding='utf-8'))
    assert manifest['status'] == 'failed' and 'SHA' in manifest['error']
    assert (output / 'failure.json').exists()
    assert not list(output.rglob('*.joblib'))

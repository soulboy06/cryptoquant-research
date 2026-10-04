from decimal import Decimal as D
import json
from pathlib import Path

import pandas as pd
import pytest

from cryptoquant.cli import main
from cryptoquant.data.archive import sha_file
from cryptoquant.models.features import build_features, FEATURE_NAMES
from cryptoquant.models.samples import build_training_samples
from test_baseline_engine import fixture
from test_baseline_workflow import fake_data


def data(hours=24, rising=True):
    frames, rules, config = fixture(hours=hours, rising=rising)
    for frame in frames.values():
        frame['quote_volume'] = '100'
        frame.loc[frame.row_role == 'boundary', 'quote_volume'] = None
    return frames, rules, config


def test_features_have_known_values_and_cannot_see_future_prices():
    frames, _, config = data()
    frame = frames['BTCUSDT']
    for i in frame.index[:-1]:
        p = D('1.001') ** int(i)
        frame.loc[i, ['open', 'close', 'high', 'low']] = [str(p), str(p), str(p * D('1.1')), str(p * D('.9'))]
    features = build_features(frame)
    row = features[features.decision_time == config.development_start].iloc[0]
    assert row.feature_valid and row.history_count == 744
    assert row['return_1h'] == pytest.approx(.001)
    assert row['return_4h'] == pytest.approx(1.001 ** 4 - 1)
    assert row['volatility_24h'] == pytest.approx(0, abs=1e-12)
    assert row['range_fraction'] == pytest.approx(.2)
    assert row['quote_volume_change'] == pytest.approx(0)
    assert 0 < row['ema24_distance'] < row['ema72_distance']
    frame.loc[frame.open_time >= config.development_start, ['open', 'close', 'high', 'low', 'quote_volume']] = '1'
    changed = build_features(frame)
    pd.testing.assert_frame_equal(features.iloc[:744], changed.iloc[:744])
    # A zero historical volume denominator is invalid, never replaced by zero.
    frame.loc[719:742, 'quote_volume'] = '0'
    assert not build_features(frame).iloc[743].feature_valid


def test_no_trade_halt_and_744_observation_restart():
    frames, _, _ = data(hours=760)
    frame = frames['BTCUSDT']
    frame.loc[745, 'market_state'] = 'no_trade'
    frame.loc[746, 'market_state'] = 'halt'
    frame.loc[746, ['open', 'close', 'high', 'low', 'quote_volume', 'available_time']] = [None] * 5 + [pd.NaT]
    features = build_features(frame)
    assert features.iloc[744].feature_valid
    assert not features.iloc[745:1490].feature_valid.any()
    assert features.iloc[745].history_count == features.iloc[746].history_count == 0
    assert features.iloc[1490].feature_valid and features.iloc[1490].history_count == 744
    assert not features.iloc[-1].feature_valid
    assert len(FEATURE_NAMES) == 9


def test_labels_use_four_calendar_hours_and_reject_boundary_and_outage():
    frames, _, config = data()
    frame = frames['BTCUSDT']
    samples, excluded = build_training_samples(frame, config.development_start, config.development_end)
    assert len(samples) == 5 and (samples.label == 1).all()
    row = samples.iloc[0]
    assert row.label_end - row.label_start == pd.Timedelta(4, unit='h')
    assert row.label_return == pytest.approx(float(D('10.748') / D('10.744') - 1))
    assert (samples.label_end < config.development_end).all()
    assert excluded.iloc[-1]['reason'] == 'label_crosses_boundary'
    frame.loc[frame.open_time == pd.Timestamp(config.development_start) + pd.Timedelta(2, unit='h'), 'market_state'] = 'no_trade'
    _, excluded = build_training_samples(frame, config.development_start, config.development_end)
    assert excluded.iloc[0]['reason'] == 'label_unavailable_window'
    frames, _, config = data(rising=False)
    samples, _ = build_training_samples(frames['BTCUSDT'], config.development_start, config.development_end)
    assert (samples.label == 0).all()


def test_samples_cli_is_offline_development_only_and_preserves_id(tmp_path, monkeypatch):
    frames, _, config = data()
    config_path = fake_data(tmp_path, frames, config)
    monkeypatch.chdir(tmp_path)
    import requests
    monkeypatch.setattr(requests, 'Session', lambda: pytest.fail('unexpected network'))
    import cryptoquant.baselines.io as io
    original = io.pd.read_parquet
    reads = []
    def checked(path):
        reads.append(str(path))
        assert 'development' in str(path)
        return original(path)
    monkeypatch.setattr(io.pd, 'read_parquet', checked)
    command = ['build-samples', '--config', str(config_path), '--data-experiment-id', 'EXP-001', '--experiment-id', 'EXP-002']
    assert main(command) == 0 and len(reads) == 3
    output = tmp_path / 'artifacts/experiments/EXP-002'
    manifest = json.loads((output / 'sample_manifest.json').read_text('utf-8'))
    assert manifest['status'] == 'complete'
    assert all(x['samples'] == 5 for x in manifest['symbols'].values())
    path = output / 'training_samples/BTCUSDT.parquet'
    digest = sha_file(path)
    assert main(command) == 1 and sha_file(path) == digest
    command[-1] = 'EXP-003'
    command[command.index('EXP-001')] = 'EXP-999'
    assert main(command) == 1
    assert json.loads((tmp_path / 'artifacts/experiments/EXP-003/sample_manifest.json').read_text('utf-8'))['status'] == 'failed'

"""市场过滤的有限因果、指标与来源检查；不跑真实账户或模型fit。"""
from pathlib import Path
from types import SimpleNamespace
import json
import shutil

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]


def candles(start='2023-01-01', hours=1000, flat=False):
    times = pd.date_range(start, periods=hours, freq='h', tz='UTC')
    close = np.full(hours, 100.) if flat else 100. + np.arange(hours) / 10
    return pd.DataFrame(dict(symbol='BTCUSDT', open_time=times,
                             available_time=times + pd.Timedelta(1, unit='h'),
                             open=close, high=close + 1, low=close - 1, close=close,
                             market_state='observed', row_role='evaluation'))


def build(frame):
    from cryptoquant.models.regime import build_market_regime
    return build_market_regime(frame)


def test_closed_hour_state_is_causal_and_has_complete_four_hour_clock():
    frame = candles()
    original = build(frame)
    cutoff = frame.open_time.iloc[800]
    changed = frame.copy()
    changed.loc[changed.open_time >= cutoff, ['open', 'high', 'low', 'close']] *= 2
    perturbed = build(changed)
    pd.testing.assert_frame_equal(original[original.decision_time <= cutoff],
                                  perturbed[perturbed.decision_time <= cutoff])
    pd.testing.assert_frame_equal(original[original.decision_time <= cutoff], build(frame.iloc[:800]))
    assert list(original) == ['decision_time', 'available_time', 'adx14', 'ema72',
                              'slope24', 'history_count', 'state_valid', 'allow_buy']
    assert pd.DatetimeIndex(original.decision_time).equals(pd.date_range(
        '2023-01-01T04:00:00Z', '2023-02-11T16:00:00Z', freq='4h'))
    assert original.available_time.equals(original.decision_time)
    assert not original.loc[original.history_count < 744, 'allow_buy'].any()
    assert original.loc[original.history_count >= 744, 'allow_buy'].all()


def test_indicator_seeds_and_zero_denominators_are_explicit():
    state = build(candles(hours=100))
    seed = state[state.history_count == 72].iloc[0]
    assert seed.ema72 == pytest.approx(np.mean(100 + np.arange(72) / 10), abs=1e-12)
    assert state.loc[state.history_count < 28, 'adx14'].isna().all()
    assert state.loc[state.history_count >= 28, 'adx14'].eq(100).all()
    ema = seed.ema72
    for i in range(72, 96):
        ema = (1 - 2 / 73) * ema + 2 / 73 * (100 + i / 10)
    last = state[state.history_count == 96].iloc[0]
    assert last.ema72 == pytest.approx(ema, abs=1e-12)
    assert last.slope24 == pytest.approx(ema / seed.ema72 - 1, abs=1e-12)
    mixed = candles(hours=100)
    i = np.arange(100)
    mixed['close'] = mixed['open'] = 100 + i % 7 * 2 + i / 10
    mixed['high'] = mixed.close + i % 3 + 1
    mixed['low'] = mixed.close - i % 4 - 1
    mixed_state = build(mixed).set_index('history_count')
    # Frozen independent 70-digit Decimal reference, including the nontrivial
    # Wilder seed and subsequent recurrence (not merely always-up ADX=100).
    for count, expected in [(28, 10.18687121148662055), (32, 8.97101128423194966),
                            (40, 9.23244216569256330), (100, 9.38124377288385927)]:
        assert mixed_state.loc[count, 'adx14'] == pytest.approx(expected, abs=1e-11)
    flat = candles(flat=True)
    flat['high'] = flat['low'] = flat['close']
    zero = build(flat)
    assert zero.loc[zero.state_valid, 'adx14'].eq(0).all()
    assert zero.loc[zero.state_valid, 'slope24'].eq(0).all()
    assert not zero.allow_buy.any()


def test_verified_no_trade_and_halt_reset_all_indicators_and_history():
    frame = candles('2023-02-15', 1700)
    no_trade = frame.open_time == pd.Timestamp('2023-03-24T12:00:00Z')
    halt = frame.open_time == pd.Timestamp('2023-03-24T13:00:00Z')
    frame.loc[no_trade, 'market_state'] = 'no_trade'
    frame.loc[halt, 'market_state'] = 'halt'
    frame.loc[halt, ['open', 'high', 'low', 'close']] = np.nan
    frame.loc[halt, 'available_time'] = pd.NaT
    state = build(frame)
    recovered = state[state.decision_time >= pd.Timestamp('2023-03-24T16:00:00Z')]
    assert recovered.iloc[0].history_count == 2
    assert recovered.iloc[0][['adx14', 'ema72', 'slope24']].isna().all()
    assert not recovered.loc[recovered.history_count < 744, 'allow_buy'].any()
    assert recovered.loc[recovered.history_count >= 744, 'state_valid'].all()


@pytest.mark.parametrize('damage', ['missing_hour', 'duplicate', 'bad_price', 'bad_ohlc',
                                    'future_clock', 'fake_halt', 'label_column'])
def test_corrupt_inputs_fail_instead_of_becoming_warmup(damage):
    frame = candles()
    if damage == 'missing_hour':
        frame = frame.drop(index=10)
    elif damage == 'duplicate':
        frame = pd.concat([frame.iloc[:10], frame.iloc[9:]])
    elif damage == 'bad_price':
        frame.loc[10, 'close'] = np.nan
    elif damage == 'bad_ohlc':
        frame.loc[10, 'high'] = 1
    elif damage == 'future_clock':
        frame.loc[10, 'available_time'] += pd.Timedelta(1, unit='h')
    elif damage == 'fake_halt':
        frame.loc[10, 'market_state'] = 'halt'
        frame.loc[10, ['open', 'high', 'low', 'close']] = np.nan
        frame.loc[10, 'available_time'] = pd.NaT
    else:
        frame['label'] = 1
    with pytest.raises(ValueError):
        build(frame)


def test_seventh_scope_is_fixed_and_does_not_change_legacy_configs(tmp_path):
    from cryptoquant.models.research_config import load_research_config
    cfg = load_research_config(ROOT / 'configs/seventh_experiment.toml', ROOT)
    assert cfg.max_account_runs == 9 and cfg.exit_variants == ('C2',)
    assert cfg.regime_variants == ('R0', 'R1')
    assert cfg.regime_parameters == dict(symbol='BTCUSDT', adx_period=14, adx_min=20,
                                        ema_period=72, slope_hours=24, history_hours=744)
    assert load_research_config(ROOT / 'configs/fifth_experiment.toml', ROOT).max_account_runs == 30
    assert load_research_config(ROOT / 'configs/sixth_experiment.toml', ROOT).exit_variants == ('C0', 'C1', 'C2', 'C3')
    configs = tmp_path / 'configs'
    configs.mkdir()
    raw = (ROOT / 'configs/seventh_experiment.toml').read_text('utf-8')
    changed = configs / 'changed.toml'
    changed.write_text(raw.replace('adx_min = 20', 'adx_min = 19'), encoding='utf-8')
    with pytest.raises(ValueError, match='fixed research scope'):
        load_research_config(changed, tmp_path)


def test_history_overlap_conflicts_fail_and_annual_boundary_keeps_seed(monkeypatch):
    from cryptoquant.models import regime_workflow as workflow
    full = candles('2023-11-01', 2300)
    full['source_id'] = 'verified-source'
    dev, val = full.iloc[:1600].copy(), full.iloc[850:].copy()
    val['row_role'] = 'warmup'
    periods = {'development': dev, 'validation': val}
    cfg = SimpleNamespace(execution_config=object())
    def load(root, data_id, config, period):
        return {'BTCUSDT': periods[period]}, {}, {'period': period}
    monkeypatch.setattr(workflow, 'load_period', load)
    history, _ = workflow.load_regime_history(ROOT, cfg, 'EXP-003')
    assert len(history) == len(full)
    pd.testing.assert_frame_equal(build(history), build(full.drop(columns='source_id')))
    periods['validation'].loc[periods['validation'].index[0], 'close'] += .01
    with pytest.raises(ValueError, match='overlap'):
        workflow.load_regime_history(ROOT, cfg, 'EXP-003')


def test_prepare_wrong_source_rejected_before_loading_or_creating_directory(tmp_path, monkeypatch):
    from cryptoquant.models import regime_workflow as workflow
    args = SimpleNamespace(research_config=ROOT / 'configs/seventh_experiment.toml',
                           data_experiment_id='EXP-004', prepared_experiment_id='EXP-063',
                           experiment_id='EXP-999')
    # Config root must be the real project; bad source must leave it untouched.
    def forbidden(*args, **kwargs):
        pytest.fail('wrong source must be rejected before any history/model loading')
    monkeypatch.setattr(workflow, 'load_period', forbidden)
    with pytest.raises(ValueError, match='frozen source'):
        workflow.execute_regime_prepare(args, ROOT)
    assert not (ROOT / 'artifacts/experiments/EXP-999').exists()


def test_prepare_freezes_only_closed_states_and_retains_started_failure(tmp_path, monkeypatch):
    from cryptoquant.models import regime_workflow as workflow
    from cryptoquant.models.research_integrity import verify_completed_experiment
    from cryptoquant.data.archive import sha_file
    shutil.copytree(ROOT / 'configs', tmp_path / 'configs')
    (tmp_path / 'EXPERIMENTS.md').write_text('| EXP-998 | 状态准备 | 待运行 |\n| EXP-999 | 状态准备 | 待运行 |', encoding='utf-8')
    source_cfg = tmp_path / 'configs/sixth_experiment.toml'
    source = dict(source_research_config_path=str(source_cfg), source_research_config_hash=sha_file(source_cfg),
                  prepared_experiment_id='EXP-063', models={window: {'training_experiment_id': identifier}
                                                         for window, identifier in workflow.REGIME_MODEL_IDS.items()})
    # No real serialized models in a miniature fixture; verify product workflow
    # using a fixed preverified source boundary, never a real fit or account.
    monkeypatch.setattr(workflow, '_verify_regime_sources', lambda *args: source)
    times = pd.date_range('2021-12-01', '2025-12-31T19:00:00', freq='h', tz='UTC')
    history = candles('2021-12-01', len(times))
    no_trade = history.open_time.eq(pd.Timestamp('2023-03-24T12:00:00Z'))
    halt = history.open_time.eq(pd.Timestamp('2023-03-24T13:00:00Z'))
    history.loc[no_trade, 'market_state'] = 'no_trade'
    history.loc[halt, 'market_state'] = 'halt'
    history.loc[halt, ['open', 'high', 'low', 'close']] = np.nan
    history.loc[halt, 'available_time'] = pd.NaT
    monkeypatch.setattr(workflow, 'load_regime_history', lambda *args: (history, {'synthetic': True}))
    args = SimpleNamespace(research_config=tmp_path / 'configs/seventh_experiment.toml',
                           data_experiment_id='EXP-003', prepared_experiment_id='EXP-063', experiment_id='EXP-998')
    assert workflow.execute_regime_prepare(args, tmp_path) == 0
    folder, run = verify_completed_experiment(tmp_path, 'EXP-998', 'regime_preparation')
    state_manifest = json.loads((folder / 'state_manifest.json').read_text('utf-8'))
    assert state_manifest['sources'] == source
    assert state_manifest['input']['rows'] == len(history)
    assert state_manifest['input']['last_available_utc'] == '2025-12-31T20:00:00+00:00'
    for window in ('W1', 'W2', 'R2025'):
        item = state_manifest['states'][window]
        table = pd.read_parquet(folder / item['path'])
        assert sha_file(folder / item['path']) == item['sha256']
        assert list(table) == ['decision_time', 'available_time', 'adx14', 'ema72',
                              'slope24', 'history_count', 'state_valid', 'allow_buy']
    assert pd.read_parquet(folder / 'state_W2.parquet').history_count.iloc[0] > 744
    with pytest.raises(ValueError, match='already exists'):
        workflow.execute_regime_prepare(args, tmp_path)
    args.experiment_id = 'EXP-999'
    def broken(*args):
        raise ValueError('synthetic history input failure')
    monkeypatch.setattr(workflow, 'load_regime_history', broken)
    with pytest.raises(ValueError, match='synthetic history input failure'):
        workflow.execute_regime_prepare(args, tmp_path)
    failed = tmp_path / 'artifacts/experiments/EXP-999'
    assert json.loads((failed / 'run_manifest.json').read_text('utf-8'))['status'] == 'failed'
    assert json.loads((failed / 'failure.json').read_text('utf-8'))['error_type'] == 'ValueError'
    assert (failed / 'research_config.toml').exists() and (failed / 'source_manifest.json').exists()

"""受控研究窗口：只用合成历史检查时间隔离与共用账本。"""

from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from cryptoquant.baselines.engine import run_backtest, validate_frames
from cryptoquant.baselines.periods import period_bounds
from cryptoquant.baselines.reporting import save_report, summarize
from cryptoquant.config import load_config
from cryptoquant.data.rules import MarketRules
from cryptoquant.models.features import ALL_FEATURE_NAMES, build_features
from cryptoquant.models.research_config import RESEARCH_WINDOWS
from cryptoquant.trading.ledger import Portfolio


def synthetic_history(*, varying=False):
    config = load_config(Path(__file__).parents[1] / 'configs/second_experiment.toml')
    grid = pd.date_range(config.development_start - pd.Timedelta(744, unit='h'), config.development_end, freq='h')
    prices = 10 + np.sin(np.arange(len(grid)) / 25) if varying else np.full(len(grid), 10.)
    frames, rules = {}, {}
    for symbol in config.symbols:
        frame = pd.DataFrame(dict(symbol=symbol, open_time=grid, open=prices, close=prices,
                                  high=prices + .1, low=prices - .1, quote_volume=100.,
                                  available_time=grid + pd.Timedelta(1, unit='h'), source_id='synthetic',
                                  market_state='observed', row_role=np.where(grid < config.development_start, 'warmup', 'evaluation'),
                                  history_count=np.arange(len(grid)) + 1, history_ready=True, extra_future=9.))
        for column in ['open', 'close', 'high', 'low']:
            frame[column] = frame[column].astype(str)
        frame.loc[frame.open_time == config.development_end, 'row_role'] = 'boundary'
        safe = {'symbol', 'open_time', 'open', 'source_id', 'market_state', 'row_role'}
        for column in set(frame) - safe:
            frame[column] = frame[column].where(frame.row_role != 'boundary')
        frames[symbol] = frame
        rules[symbol] = MarketRules(symbol, D('.001'), D('.001'), D('1000'), D('10'), None, (5,))
    return frames, rules, config


def test_fixed_windows_copy_calendar_terminal_mask_and_legacy_bounds():
    from cryptoquant.baselines.windows import window_frames
    frames, _, config = synthetic_history()
    original = {symbol: frame.copy(deep=True) for symbol, frame in frames.items()}
    assert period_bounds(config, 'development') == (config.development_start, config.development_end)
    assert period_bounds(config, 'validation') == (config.validation_start, config.validation_end)
    for name, fixed in RESEARCH_WINDOWS.items():
        assert period_bounds(config, fixed.period, window=name) == (fixed.start, fixed.end)
    for name in ['W1', 'W2']:
        fixed = RESEARCH_WINDOWS[name]
        view = window_frames(frames, config, 'development', name)
        grid, _ = validate_frames(view, config, window=name)
        assert grid[0] == fixed.start - pd.Timedelta(744, unit='h') and grid[-1] == fixed.end
        assert len(grid) == 745 + int((fixed.end - fixed.start).total_seconds() / 3600)
        for symbol, frame in view.items():
            assert (frame.row_role == 'warmup').sum() == 744
            assert frame.iloc[-1].row_role == 'boundary' and D(frame.iloc[-1].open) == 10
            unsafe = set(frame) - {'symbol', 'open_time', 'open', 'source_id', 'market_state', 'row_role'}
            assert frame.iloc[-1][list(unsafe)].isna().all()
            pd.testing.assert_frame_equal(frames[symbol], original[symbol])
    for period, name in [('development', 'R2025'), ('validation', 'W1'), ('test', 'W2'),
                         ('development', '2026'), ('development', pd.Timestamp('2023-01-01', tz='UTC'))]:
        with pytest.raises(ValueError):
            period_bounds(config, period, window=name)
    with pytest.raises(ValueError, match='partition|contain'):
        period_bounds(replace(config, development_start=RESEARCH_WINDOWS['W2'].start), 'development', window='W1')
    with pytest.raises(ValueError, match='calendar'):
        window_frames({s: f.iloc[1:] for s, f in frames.items()}, config, 'development', 'W1')
    broken = {s: f.copy() for s, f in frames.items()}
    broken['BTCUSDT'].loc[0, 'row_role'] = 'evaluation'
    with pytest.raises(ValueError, match='role'):
        window_frames(broken, config, 'development', 'W1')


class FeatureProbabilityModel:
    feature_names_in_ = np.array(ALL_FEATURE_NAMES)
    classes_ = np.array([0, 1])

    def predict_proba(self, frame):
        assert list(frame) == ALL_FEATURE_NAMES
        p = np.clip(.6 + frame.ema72_distance.to_numpy() + frame.funding_rate_latest.to_numpy(), 0, 1)
        return np.column_stack([1 - p, p])


def test_continuous_features_halt_recovery_future_isolation_and_complete_grid():
    from cryptoquant.baselines.windows import select_window_features, window_frames
    from cryptoquant.data.funding import compute_funding_features
    from cryptoquant.models.predictions import build_window_probabilities
    frames, _, config = synthetic_history(varying=True)
    start = pd.Timestamp(RESEARCH_WINDOWS['W1'].start)
    for frame in frames.values():
        halt = frame.open_time == start + pd.Timedelta(20, unit='h')
        frame.loc[halt, 'market_state'] = 'halt'
        for column in ['open', 'close', 'high', 'low', 'quote_volume', 'available_time']:
            frame[column] = frame[column].where(~halt)
    funding_times = pd.date_range(frames['BTCUSDT'].open_time.iloc[0], config.development_end, freq='8h')
    funding = {s: compute_funding_features(pd.DataFrame(dict(symbol=s, funding_time=funding_times,
                       funding_rate=np.sin(np.arange(len(funding_times))) / 10000))) for s in config.symbols}
    full = {s: build_features(f, funding_df=funding[s]) for s, f in frames.items()}
    before = {s: f.copy(deep=True) for s, f in full.items()}
    selected = select_window_features(full, config, 'development', 'W1')
    for s in config.symbols:
        expected = full[s][(full[s].decision_time >= start) & (full[s].decision_time < RESEARCH_WINDOWS['W1'].end)]
        pd.testing.assert_frame_equal(selected[s], expected.reset_index(drop=True))
        pd.testing.assert_frame_equal(full[s], before[s])
        assert not selected[s].loc[selected[s].decision_time == start + pd.Timedelta(24, unit='h'), 'feature_valid'].item()
        assert selected[s].loc[selected[s].decision_time == start + pd.Timedelta(768, unit='h'), 'feature_valid'].item()
        sliced = build_features(window_frames(frames, config, 'development', 'W1')[s], funding_df=funding[s])
        # Reinitializing EMA on the 744h execution view changes the model's exact feature.
        assert selected[s].iloc[0].ema72_distance != sliced.loc[sliced.decision_time == start, 'ema72_distance'].item()
    cutoff = start + pd.Timedelta(800, unit='h')
    for s, frame in frames.items():
        later = (frame.open_time >= cutoff) & (frame.row_role != 'boundary')
        frame.loc[later, ['close', 'high', 'low']] = (frame.loc[later, ['close', 'high', 'low']].astype(float) * 2).astype(str)
        funding[s].loc[funding[s].funding_time > cutoff, 'funding_rate'] = .9
        changed = build_features(frame, funding_df=compute_funding_features(funding[s]))
        pd.testing.assert_frame_equal(full[s].loc[full[s].decision_time <= cutoff], changed.loc[changed.decision_time <= cutoff])
    models = {s: FeatureProbabilityModel() for s in config.symbols}
    probabilities = build_window_probabilities(full, models, config, 'development', window='W1')
    expected_times = pd.date_range(start, RESEARCH_WINDOWS['W1'].end, freq='4h', inclusive='left')
    assert len(probabilities) == len(expected_times) * len(config.symbols)
    for s in config.symbols:
        result = probabilities[probabilities.symbol == s]
        assert pd.DatetimeIndex(result.decision_time).equals(expected_times)
        assert pd.isna(result.loc[result.decision_time == start + pd.Timedelta(24, unit='h'), 'probability'].item())
        valid = selected[s][selected[s].feature_valid & (selected[s].decision_time.dt.hour % 4 == 0)]
        np.testing.assert_array_equal(result[result.probability.notna()].probability, models[s].predict_proba(valid[ALL_FEATURE_NAMES])[:, 1])
    for kind in ['duplicate', 'missing', 'future', 'symbol']:
        bad = {s: f.copy() for s, f in full.items()}
        frame = bad['BTCUSDT']
        index = frame.index[frame.decision_time == start][0]
        if kind == 'duplicate':
            bad['BTCUSDT'] = pd.concat([frame, frame.loc[[index]]])
        elif kind == 'missing':
            bad['BTCUSDT'] = frame.drop(index)
        elif kind == 'future':
            frame.loc[index, 'feature_available_time'] = start + pd.Timedelta(1, unit='h')
        else:
            frame.loc[index, 'symbol'] = 'OTHER'
        with pytest.raises(ValueError):
            build_window_probabilities(bad, models, config, 'development', window='W1')


def test_window_common_engine_cash_fees_halt_tail_and_report_endpoints(tmp_path):
    from cryptoquant.baselines.windows import window_frames
    frames, rules, config = synthetic_history()
    end = RESEARCH_WINDOWS['W1'].end
    halt = frames['BTCUSDT'].open_time == end
    frames['BTCUSDT'].loc[halt, 'market_state'] = 'halt'
    for column in ['open', 'close', 'high', 'low', 'quote_volume', 'available_time']:
        frames['BTCUSDT'][column] = frames['BTCUSDT'][column].where(~halt)
    view = window_frames(frames, config, 'development', 'W1')
    start, end = period_bounds(config, 'development', window='W1')
    times = pd.date_range(start, end, freq='4h', inclusive='left')
    targets = pd.DataFrame([dict(symbol=s, decision_time=t, probability=.9 if t == times[0] else np.nan,
                               target_weight=config.weight_per_symbol if t == times[0] else None)
                           for t in times for s in config.symbols])
    hold = run_backtest(view, rules, config, 'buy_hold', 'base', window='W1')
    model = run_backtest(view, rules, config, 'logistic_regression', 'base', window='W1', decision_targets=targets)
    assert hold.fills == model.fills and hold.book.cash == model.book.cash
    assert all(r['cash'] >= 0 for r in model.equity)
    assert model.equity[0]['equity'] == D('100')
    assert model.equity[-1]['time'] == end and model.equity[-1]['phase'] == 'terminal'
    assert model.book.positions['BTCUSDT'].quantity > 0 and len(model.fills) == 5
    replay = Portfolio(D('100'), config.symbols)
    for fill in model.fills:
        replay.apply_fill(fill['side'], fill['symbol'], fill['quantity'], fill['price'], config.costs['base'].fee)
    assert replay.cash == model.book.cash and replay.fees_usdt == sum(r['fee_usdt'] for r in model.fills)
    assert replay.equity(model.marks) == model.book.equity(model.marks)
    summary, annual = summarize(model, config)
    assert summary['window'] == 'W1' and summary['start_utc'] == start and summary['end_utc'] == end
    assert len(annual) == 1 and annual[0]['start_equity'] == D('100') and annual[-1]['end_equity'] == summary['final_equity']
    assert summary['final_equity'] == summary['final_cash'] + summary['residual_value']
    save_report(model, config, tmp_path, 'SYNTHETIC')
    quarterly = pd.read_csv(tmp_path / 'quarterly.csv')
    assert len(quarterly) == 4 and quarterly.iloc[0].start_equity == 100
    np.testing.assert_array_equal(quarterly.start_equity.iloc[1:], quarterly.end_equity.iloc[:-1])
    assert quarterly.iloc[-1].end_equity == pytest.approx(float(summary['final_equity']))
    assert 'W1' in (tmp_path / 'report.md').read_text('utf-8')
    second = run_backtest(window_frames(frames, config, 'development', 'W2'), rules, config, 'buy_hold', 'base', window='W2')
    assert second.equity[0]['equity'] == D('100') and second.equity[0]['cash'] == D('100')
    with pytest.raises(ValueError, match='columns'):
        run_backtest(view, rules, config, 'logistic_regression', 'base', window='W1', decision_targets=targets.assign(label=1))
    with pytest.raises(ValueError, match='continuous|EMA|ema_trend'):
        run_backtest(view, rules, config, 'ema_trend', 'base', window='W1')

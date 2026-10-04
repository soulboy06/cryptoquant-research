from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import pandas as pd
import pytest

from cryptoquant.config import load_config
from cryptoquant.data.rules import MarketRules
from cryptoquant.baselines.engine import run_backtest
from cryptoquant.baselines.strategies import TrendSignals


def fixture(hours=24, rising=False):
    config = load_config(Path(__file__).parents[1] / 'configs/first_experiment.toml')
    start = pd.Timestamp(config.development_start)
    end = (start + pd.Timedelta(hours, unit='h')).to_pydatetime()
    config = replace(config, development_end=end, validation_start=end)
    grid = pd.date_range(start - pd.Timedelta(744, unit='h'), config.development_end, freq='h')
    frames, rules = {}, {}
    for symbol in config.symbols:
        rows = []
        for i, time in enumerate(grid):
            p = str(D('10') + D(i) / 1000) if rising else '10'
            boundary = time == config.development_end
            rows.append(dict(symbol=symbol, open_time=time, open=p, close=None if boundary else p,
                             high=None if boundary else p, low=None if boundary else p,
                             available_time=pd.NaT if boundary else time + pd.Timedelta(1, unit='h'),
                             source_id='synthetic', market_state='observed',
                             row_role='boundary' if boundary else 'warmup' if time < start else 'evaluation'))
        frames[symbol] = pd.DataFrame(rows)
        rules[symbol] = MarketRules(symbol, D('.001'), D('.001'), D('1000'), D('10'), None, (5,))
    return frames, rules, config


def test_buy_hold_cash_fees_terminal_residual_and_determinism():
    frames, rules, config = fixture()
    a = run_backtest(frames, rules, config, 'buy_hold', 'base')
    b = run_backtest(frames, rules, config, 'buy_hold', 'base')
    assert len(a.fills) == 6
    assert [x['side'] for x in a.fills] == ['BUY'] * 3 + ['SELL'] * 3
    assert a.book.cash >= 0 and a.book.equity(a.marks) < D('100')
    assert a.book.equity(a.marks) == b.book.equity(b.marks)
    assert a.fills == b.fills and a.risk.closed_cycles == 3
    assert a.equity[0]['equity'] == D('100')
    assert all(x['cash'] >= 0 for x in a.equity)


def test_same_open_future_candle_cannot_change_signal_or_initial_orders():
    frames, rules, config = fixture(rising=True)
    start = pd.Timestamp(config.development_start)
    a = run_backtest(frames, rules, config, 'ema_trend', 'base')
    for frame in frames.values():
        frame.loc[frame.open_time == start, ['close', 'high', 'low']] = '1'
        frame.loc[(frame.open_time > start) & (frame.row_role != 'boundary'), ['open', 'close', 'high', 'low']] = '1'
    b = run_backtest(frames, rules, config, 'ema_trend', 'base')
    assert [x for x in a.orders if x['time'] == start] == [x for x in b.orders if x['time'] == start]
    assert [x for x in a.signals if x['time'] == start] == [x for x in b.signals if x['time'] == start]


def test_floor_exit_waits_for_real_quote_then_remains_locked():
    frames, rules, config = fixture()
    start = pd.Timestamp(config.development_start)
    for frame in frames.values():
        frame.loc[frame.open_time == start + pd.Timedelta(1, unit='h'), ['close', 'low']] = '4'
        frame.loc[frame.open_time == start + pd.Timedelta(2, unit='h'), 'market_state'] = 'no_trade'
        frame.loc[frame.open_time == start + pd.Timedelta(3, unit='h'), 'market_state'] = 'halt'
        frame.loc[frame.market_state == 'halt', ['open', 'close', 'available_time']] = [None, None, pd.NaT]
    result = run_backtest(frames, rules, config, 'buy_hold', 'base')
    assert result.risk.locked and result.risk.floor_triggers == 1
    assert all(x['time'] == start + pd.Timedelta(4, unit='h') for x in result.fills if x['side'] == 'SELL')
    assert len([x for x in result.fills if x['side'] == 'BUY']) == 3
    assert any(x['stale_symbols'] for x in result.equity)


def test_terminal_missing_quote_preserves_holdings_without_fabricated_sale():
    frames, rules, config = fixture()
    frames['BTCUSDT'].loc[frames['BTCUSDT'].row_role == 'boundary', ['open', 'market_state']] = [None, 'halt']
    result = run_backtest(frames, rules, config, 'buy_hold', 'base')
    assert result.book.positions['BTCUSDT'].quantity > D('1')
    assert len(result.fills) == 5
    assert result.orders[-3]['reason'] == 'no_quote'


def test_unavailable_history_resets_and_does_not_trade_on_unready_signals():
    frames, rules, config = fixture(hours=48, rising=True)
    start = pd.Timestamp(config.development_start)
    for frame in frames.values():
        frame.loc[frame.open_time == start + pd.Timedelta(1, unit='h'), 'market_state'] = 'no_trade'
    result = run_backtest(frames, rules, config, 'ema_trend', 'base')
    assert all(x['weight'] is None for x in result.signals if x['time'] == start + pd.Timedelta(4, unit='h'))
    assert not [x for x in result.orders if start < x['time'] < config.development_end]


def test_boundary_future_fields_and_calendar_misalignment_rejected():
    frames, rules, config = fixture()
    frames['BTCUSDT'].loc[frames['BTCUSDT'].row_role == 'boundary', 'close'] = '100'
    with pytest.raises(ValueError, match='boundary'):
        run_backtest(frames, rules, config, 'buy_hold', 'base')
    frames, rules, config = fixture()
    frames['ETHUSDT'] = frames['ETHUSDT'].iloc[1:]
    with pytest.raises(ValueError, match='calendar'):
        run_backtest(frames, rules, config, 'buy_hold', 'base')


def test_cooldown_symbol_does_not_scale_down_other_initial_buys(monkeypatch):
    frames, rules, config = fixture()
    config = replace(config, weight_per_symbol=D('0.3333333333333333333333333333'))
    from cryptoquant.trading.risk import RiskState
    original = RiskState.can_buy
    monkeypatch.setattr(RiskState, 'can_buy', lambda self, s, t: False if s == 'BTCUSDT' else original(self, s, t))
    result = run_backtest(frames, rules, config, 'buy_hold', 'base')
    buys = [r for r in result.fills if r['side'] == 'BUY']
    assert [r['symbol'] for r in buys] == ['ETHUSDT', 'SOLUSDT']
    assert all(r['quantity'] == D('3.336') for r in buys)


def test_resumed_open_gap_through_floor_checked_before_new_orders():
    frames, rules, config = fixture()
    start = pd.Timestamp(config.development_start)
    for frame in frames.values():
        frame.loc[frame.open_time == start + pd.Timedelta(1, unit='h'), 'market_state'] = 'no_trade'
        frame.loc[frame.open_time == start + pd.Timedelta(2, unit='h'), ['open', 'close', 'high', 'low']] = '4'
    result = run_backtest(frames, rules, config, 'buy_hold', 'base')
    floors = [e for e in result.risk.events if e['event'] == 'floor_triggered']
    assert floors[0]['time'] == start + pd.Timedelta(2, unit='h')
    assert all(r['time'] == floors[0]['time'] for r in result.fills if r['side'] == 'SELL')
    assert result.book.equity(result.marks) < D('50')


def test_active_stop_executes_next_available_open_and_does_not_sell_future_close():
    frames, rules, config = fixture(rising=True)
    start = pd.Timestamp(config.development_start)
    frame = frames['BTCUSDT']
    frame.loc[frame.open_time == start, ['close', 'low']] = '9'
    frame.loc[frame.open_time == start + pd.Timedelta(1, unit='h'), 'market_state'] = 'no_trade'
    result = run_backtest(frames, rules, config, 'ema_trend', 'base')
    stops = [r for r in result.fills if r['intent_reason'] == 'stop_loss']
    assert len(stops) == 1 and stops[0]['time'] == start + pd.Timedelta(2, unit='h')
    assert result.risk.stop_triggers == 1 and result.risk.closed_cycles >= 1


def test_terminal_quantity_cap_is_one_attempt_and_residual_is_not_erased():
    frames, rules, config = fixture()
    # Initial orders are valid, but the terminal price rise binds max notional.
    for s, frame in frames.items():
        rules[s] = replace(rules[s], max_notional=D('35'))
        frame.loc[frame.row_role == 'boundary', 'open'] = '100'
    result = run_backtest(frames, rules, config, 'buy_hold', 'base')
    terminals = [r for r in result.orders if r['intent_reason'] == 'terminal']
    assert len(terminals) == 3 and all(r['accepted'] for r in terminals)
    assert all(r['quantity'] * r['price'] <= D('35') for r in terminals)
    assert all(p.quantity > D('2') for p in result.book.positions.values())
    assert result.risk.closed_cycles == 0


def test_ema_matches_adjust_false_and_not_ready_until_744_closes():
    frames, _, config = fixture(rising=True)
    history = TrendSignals(config.symbols)
    rows = frames['BTCUSDT'].iloc[:744].to_dict('records')
    for row in rows[:-1]:
        history.observe('BTCUSDT', row, row['available_time'])
    assert history.weights(config.weight_per_symbol)['BTCUSDT'] is None
    history.observe('BTCUSDT', rows[-1], rows[-1]['available_time'])
    expected = pd.Series([float(row['close']) for row in rows])
    assert history.history['BTCUSDT'].fast == pytest.approx(expected.ewm(span=24, adjust=False).mean().iloc[-1])
    assert history.history['BTCUSDT'].slow == pytest.approx(expected.ewm(span=72, adjust=False).mean().iloc[-1])
    assert history.weights(config.weight_per_symbol)['BTCUSDT'] == D('.30')

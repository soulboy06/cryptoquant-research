from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

import pytest
import pandas as pd
from dataclasses import replace

from cryptoquant.baselines.engine import run_backtest
from cryptoquant.baselines.reporting import summarize
from cryptoquant.trading.ledger import Portfolio
from cryptoquant.trading.orders import Intent, simulate_fill
from cryptoquant.trading.risk import RiskState
from test_orders import COST, quote, rule
from test_baseline_engine import fixture

NOW = datetime(2023, 1, 1, tzinfo=timezone.utc)


@pytest.mark.parametrize('symbol', ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'])
@pytest.mark.parametrize('reason', ['stop_loss', 'breakeven_exit'])
def test_rejected_exit_keeps_live_cycle_until_real_exit(symbol, reason):
    limits = rule(symbol)
    book = Portfolio('100', [symbol])
    book.apply_fill('BUY', symbol, '1.04', '10', COST.fee)
    risk = RiskState([symbol], D('50'), D('.08'), 4,
                     breakeven_activation=D('.012'), breakeven_ratio=D('.0025'),
                     dust_policy='writeoff_zero_recovery')
    risk.register_buy(symbol, book, D('10'), limits, COST, NOW)
    risk.observe(book, {symbol: D('11')}, {symbol}, NOW + timedelta(hours=1))
    quantity, basis = book.positions[symbol].quantity, book.positions[symbol].average_cost
    price = D('9') if reason == 'stop_loss' else D('9.60')
    t2 = NOW + timedelta(hours=2)
    risk.observe(book, {symbol: price}, {symbol}, t2)
    state = risk.states[symbol]
    assert state.pending == reason and state.breakeven_active
    rejected = simulate_fill(Intent(symbol, 'SELL', quantity, reason, True), quote(str(price)), limits, COST, book)
    assert not rejected.accepted
    assert not risk.complete_exit_if_tail(symbol, book, quote(str(price)), limits, COST, t2)
    assert book.positions[symbol].quantity == quantity
    assert book.positions[symbol].average_cost == basis
    assert state.cycle_open and not state.exit_completed and state.breakeven_active
    assert state.pending == reason and state.cooldown_until is None
    assert risk.closed_cycles == 0 and not any(e['event'] == 'cycle_closed' for e in risk.events)
    assert not risk.can_buy(symbol, NOW + timedelta(hours=4))
    risk.register_buy(symbol, book, price, limits, COST, t2)
    assert state.entry_time == NOW and state.holding_hours == 2
    # Duplicate observations and quote recovery cannot restart or double-count time.
    risk.observe(book, {symbol: D('10.1')}, {symbol}, NOW + timedelta(hours=4))
    risk.observe(book, {symbol: D('10.1')}, {symbol}, NOW + timedelta(hours=4))
    assert state.holding_hours == 4 and state.pending == reason
    sold = simulate_fill(Intent(symbol, 'SELL', quantity, reason, True), quote('10.1'), limits, COST, book)
    assert sold.accepted
    book.apply_fill('SELL', symbol, sold.quantity, sold.price, COST.fee)
    risk.register_full_exit_fill(symbol)
    assert risk.complete_exit_if_tail(symbol, book, quote('10.1'), limits, COST, NOW + timedelta(hours=4))
    assert book.positions[symbol].quantity == 0
    assert not state.cycle_open and risk.closed_cycles == 1
    assert state.cooldown_until == NOW + timedelta(hours=8)
    assert book.cash == D('100') - D('10.4') + sold.notional * (1 - COST.fee)
    assert abs(book.equity({symbol: D('10.1')}) - (D('100') + book.realized_pnl)) < D('1e-24')
    assert book.fees_usdt == D('10.4') * COST.fee + sold.notional * COST.fee
    assert len([e for e in risk.events if e['event'] == 'dust_written_off']) == 1
    assert not risk.complete_exit_if_tail(symbol, book, quote('10.1'), limits, COST, NOW + timedelta(hours=5))
    assert risk.closed_cycles == 1 and state.cooldown_until == NOW + timedelta(hours=8)


def test_partial_exit_below_notional_is_not_precision_dust():
    symbol = 'BTCUSDT'
    book = Portfolio('100', [symbol])
    book.apply_fill('BUY', symbol, '5', '10', '0')
    limits = rule(symbol, maximum='2')
    risk = RiskState([symbol], D('50'), D('.08'), 4)
    risk.register_buy(symbol, book, D('10'), limits, COST, NOW)
    risk.request_exit(symbol, 'stop_loss', NOW)
    for hour in [1, 2]:
        book.apply_fill('SELL', symbol, '2', '9', '0')
        risk.register_full_exit_fill(symbol)
        assert not risk.complete_exit_if_tail(symbol, book, quote('9'), limits, COST, NOW + timedelta(hours=hour))
    assert book.positions[symbol].quantity == 1
    assert risk.states[symbol].cycle_open and risk.states[symbol].pending == 'stop_loss'
    assert risk.closed_cycles == 0 and risk.states[symbol].cooldown_until is None


@pytest.mark.parametrize('symbol', ['BTCUSDT', 'ETHUSDT', 'SOLUSDT'])
def test_engine_retry_blocks_reentry_and_report_includes_dust_loss(symbol):
    frames, rules, config = fixture(hours=12)
    config = replace(config, initial_cash=D('103'))
    start = pd.Timestamp(config.development_start)
    frame = frames[symbol]
    frame.loc[frame.open_time == start + pd.Timedelta(1, unit='h'), 'close'] = '9'
    frame.loc[frame.open_time.between(start + pd.Timedelta(2, unit='h'), start + pd.Timedelta(5, unit='h')), ['open', 'close']] = '9'
    frame.loc[frame.open_time == start + pd.Timedelta(6, unit='h'), ['open', 'close']] = '11'
    targets = pd.DataFrame([
        dict(symbol=s, decision_time=start + pd.Timedelta(h, unit='h'), probability=.9,
             target_weight=D('.10') if s == symbol and h == 0 else D('.30') if s == symbol and h == 4 else D('0'))
        for h in [0, 4, 8] for s in config.symbols
    ])
    result = run_backtest(frames, rules, config, 'logistic_regression', 'base',
                          decision_targets=targets, exit_variant='C2',
                          dust_policy='writeoff_zero_recovery')
    assert [f['side'] for f in result.fills] == ['BUY', 'SELL']
    assert result.fills[-1]['time'] == start + pd.Timedelta(6, unit='h')
    assert result.fills[-1]['intent_reason'] == 'stop_loss'
    assert result.book.positions[symbol].quantity == 0
    assert result.risk.closed_cycles == 1
    assert result.risk.states[symbol].cooldown_until == start + pd.Timedelta(10, unit='h')
    summary, _ = summarize(result, config)
    assert abs(sum(v['realized_pnl'] for v in summary['per_symbol'].values()) - result.book.realized_pnl) < D('1e-24')


def test_rejected_strategy_exit_stays_pending_when_next_signal_wants_to_buy():
    frames, rules, config = fixture(hours=12)
    start = pd.Timestamp(config.development_start)
    frame = frames['BTCUSDT']
    # A signal exit below minimum notional, without a stop trigger.
    frame.loc[frame.open_time == start + pd.Timedelta(4, unit='h'), 'open'] = '2'
    frame.loc[frame.open_time.between(start + pd.Timedelta(5, unit='h'), start + pd.Timedelta(8, unit='h')), 'open'] = '2'
    targets = pd.DataFrame([
        dict(symbol=s, decision_time=start + pd.Timedelta(h, unit='h'), probability=.9,
             target_weight=D('.30') if s == 'BTCUSDT' and h != 4 else D('0'))
        for h in [0, 4, 8] for s in config.symbols
    ])
    result = run_backtest(frames, rules, config, 'logistic_regression', 'base', decision_targets=targets)
    assert len([f for f in result.fills if f['side'] == 'BUY']) == 1
    exits = [f for f in result.fills if f['side'] == 'SELL']
    assert len(exits) == 1 and exits[0]['intent_reason'] == 'strategy_exit'
    assert exits[0]['time'] == start + pd.Timedelta(9, unit='h')

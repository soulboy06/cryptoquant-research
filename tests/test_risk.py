from datetime import datetime, timedelta, timezone
from decimal import Decimal as D

from cryptoquant.trading.ledger import Portfolio
from cryptoquant.trading.risk import RiskState
from test_orders import rule, quote, COST

NOW = datetime(2023, 1, 1, tzinfo=timezone.utc)
SYMBOL = 'BTCUSDT'


def book():
    value = Portfolio('100', [SYMBOL])
    value.apply_fill('BUY', SYMBOL, '5', '10', '0')
    return value


def test_floor_is_fixed_and_permanent_after_recovery():
    portfolio = Portfolio('100', [SYMBOL])
    portfolio.apply_fill('BUY', SYMBOL, '10', '10', '0')
    risk = RiskState([SYMBOL], D('50'), D('0.08'), 4)
    for price in ['20', '15']:
        risk.observe(portfolio, {SYMBOL: D(price)}, {SYMBOL}, NOW, active=False)
        assert not risk.locked
    risk.observe(portfolio, {SYMBOL: D('5')}, {SYMBOL}, NOW, active=False)
    assert risk.locked and risk.states[SYMBOL].pending == 'floor'
    risk.observe(portfolio, {SYMBOL: D('20')}, {SYMBOL}, NOW + timedelta(hours=4), active=False)
    assert not risk.can_buy(SYMBOL, NOW + timedelta(hours=4)) and risk.floor_triggers == 1


def test_stop_uses_fee_inclusive_cost_and_does_not_sell_at_close():
    portfolio = book()
    risk = RiskState([SYMBOL], D('50'), D('0.08'), 4)
    risk.register_buy(SYMBOL, portfolio, D('10'), rule(), COST)
    risk.observe(portfolio, {SYMBOL: D('9')}, {SYMBOL}, NOW)
    assert risk.states[SYMBOL].pending == 'stop_loss'
    assert portfolio.positions[SYMBOL].quantity == D('5')
    risk.observe(portfolio, {SYMBOL: D('12')}, {SYMBOL}, NOW + timedelta(hours=1))
    assert risk.states[SYMBOL].pending == 'stop_loss'


def test_no_fresh_price_creates_no_new_stop_and_buy_hold_has_no_stop():
    portfolio = book()
    risk = RiskState([SYMBOL], D('50'), D('0.08'), 4)
    risk.observe(portfolio, {SYMBOL: D('1')}, set(), NOW)
    assert risk.states[SYMBOL].pending is None and not risk.locked
    risk.observe(portfolio, {SYMBOL: D('9')}, {SYMBOL}, NOW, active=False)
    assert risk.states[SYMBOL].pending is None


def test_exit_retry_tail_cycle_and_wall_clock_cooldown():
    portfolio = book()
    risk = RiskState([SYMBOL], D('50'), D('0.08'), 4)
    limits = rule(maximum='2')
    risk.register_buy(SYMBOL, portfolio, D('10'), limits, COST)
    risk.request_exit(SYMBOL, 'stop_loss', NOW)
    assert not risk.complete_exit_if_tail(SYMBOL, portfolio, None, limits, COST, NOW)
    assert risk.states[SYMBOL].pending == 'stop_loss'
    for hour in [1, 2]:
        portfolio.apply_fill('SELL', SYMBOL, '2', '9', '0')
        risk.register_full_exit_fill(SYMBOL)
        done = risk.complete_exit_if_tail(SYMBOL, portfolio, quote('9'), limits, COST, NOW + timedelta(hours=hour))
        assert done is (hour == 2)
    assert portfolio.positions[SYMBOL].quantity == D('1') and risk.closed_cycles == 1
    assert risk.states[SYMBOL].cooldown_until == NOW + timedelta(hours=6)
    assert not risk.can_buy(SYMBOL, NOW + timedelta(hours=4))
    assert not risk.can_buy(SYMBOL, NOW + timedelta(hours=7))
    assert risk.can_buy(SYMBOL, NOW + timedelta(hours=8))


def test_pure_rejection_or_partial_rebalance_does_not_close_cycle():
    portfolio = book()
    risk = RiskState([SYMBOL], D('50'), D('0.08'), 4)
    risk.register_buy(SYMBOL, portfolio, D('10'), rule(), COST)
    portfolio.apply_fill('SELL', SYMBOL, '1', '10', '0')
    assert risk.closed_cycles == 0
    risk.request_exit(SYMBOL, 'stop_loss', NOW)
    assert risk.complete_exit_if_tail(SYMBOL, portfolio, quote('1'), rule(), COST, NOW)
    assert risk.closed_cycles == 0 and portfolio.positions[SYMBOL].quantity == D('4')


def test_completed_stop_tail_does_not_refresh_cooldown_or_stop_count():
    portfolio = book()
    risk = RiskState([SYMBOL], D('50'), D('0.08'), 4)
    risk.register_buy(SYMBOL, portfolio, D('10'), rule(), COST)
    risk.observe(portfolio, {SYMBOL: D('9')}, {SYMBOL}, NOW)
    portfolio.apply_fill('SELL', SYMBOL, '4.999', '9', '0')
    risk.register_full_exit_fill(SYMBOL)
    risk.complete_exit_if_tail(SYMBOL, portfolio, quote('9'), rule(), COST, NOW + timedelta(hours=1))
    for hour in range(2, 9):
        risk.observe(portfolio, {SYMBOL: D('9')}, {SYMBOL}, NOW + timedelta(hours=hour))
        assert risk.states[SYMBOL].pending is None
    assert risk.stop_triggers == 1
    assert risk.states[SYMBOL].cooldown_until == NOW + timedelta(hours=5)
    assert risk.can_buy(SYMBOL, NOW + timedelta(hours=8))
    portfolio.apply_fill('BUY', SYMBOL, '2', '10', '0')
    risk.register_buy(SYMBOL, portfolio, D('10'), rule(), COST)
    risk.observe(portfolio, {SYMBOL: D('9')}, {SYMBOL}, NOW + timedelta(hours=9))
    assert risk.states[SYMBOL].pending == 'stop_loss' and risk.stop_triggers == 2

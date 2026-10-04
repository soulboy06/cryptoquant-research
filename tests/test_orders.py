from decimal import Decimal as D
from dataclasses import replace

from cryptoquant.config import Cost
from cryptoquant.data.rules import MarketRules
from cryptoquant.trading.ledger import Portfolio
from cryptoquant.trading.orders import Intent, simulate_fill, plan_rebalance, sellable_quantity

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']
COST = Cost(D('0.001'), D('0.0005'))


def rule(symbol='BTCUSDT', maximum='1000', min_notional='10', max_notional=None):
    return MarketRules(symbol, D('0.001'), D('0.001'), D(maximum), D(min_notional), D(max_notional) if max_notional else None, (5,))


def quote(price='10', state='observed'):
    return {'open': price, 'market_state': state}


def test_adverse_prices_and_no_double_spread_charge():
    book = Portfolio('100', SYMBOLS)
    buy = simulate_fill(Intent('BTCUSDT', 'BUY', D('2')), quote(), rule(), COST, book)
    assert buy.accepted and buy.price == D('10.0050')
    book.apply_fill('BUY', 'BTCUSDT', buy.quantity, buy.price, COST.fee)
    sell = simulate_fill(Intent('BTCUSDT', 'SELL', D('1.998')), quote(), rule(), COST, book)
    assert sell.accepted and sell.price == D('9.9950')


def test_max_position_checks_submitted_quantity_before_commission():
    book = Portfolio('100', SYMBOLS)
    limited = replace(rule(), max_position=D('1'))
    rejected = simulate_fill(Intent('BTCUSDT', 'BUY', D('1.001')), quote(), limited, COST, book)
    assert not rejected.accepted and rejected.reason == 'maximum_position'
    assert simulate_fill(Intent('BTCUSDT', 'BUY', D('1')), quote(), limited, COST, book).accepted


def test_no_quote_and_below_notional_orders_cannot_fill():
    book = Portfolio('100', SYMBOLS)
    for state in ['halt', 'no_trade']:
        decision = simulate_fill(Intent('BTCUSDT', 'BUY', D('2')), quote(state=state), rule(), COST, book)
        assert not decision.accepted and decision.reason == 'no_quote'
    assert not simulate_fill(Intent('BTCUSDT', 'BUY', D('0.999')), quote(), rule(), COST, book).accepted
    assert simulate_fill(Intent('BTCUSDT', 'BUY', D('1')), quote(), rule(), COST, book).accepted
    assert book.cash == D('100')


def test_risk_sell_caps_quantity_and_notional_but_normal_order_rejects():
    book = Portfolio('100', SYMBOLS)
    book.apply_fill('BUY', 'BTCUSDT', '5', '10', '0')
    limited = rule(maximum='2', max_notional='15')
    ordinary = simulate_fill(Intent('BTCUSDT', 'SELL', D('5')), quote(), limited, COST, book)
    assert not ordinary.accepted and ordinary.reason == 'maximum_quantity'
    forced = simulate_fill(Intent('BTCUSDT', 'SELL', D('5'), 'stop_loss', True), quote(), limited, COST, book)
    assert forced.accepted and forced.quantity == D('1.500')
    assert forced.notional <= D('15')
    assert sellable_quantity(D('0.05'), D('10'), limited, COST) == 0


def test_shared_cash_allocation_is_independent_of_symbol_order():
    def execute(symbols):
        book = Portfolio('100', symbols)
        quotes = {s: quote() for s in symbols}
        rules = {s: rule(s) for s in symbols}
        orders = plan_rebalance({s: D('0.3333333333333333333333333333') for s in symbols}, book, quotes, rules, COST)
        for intent in orders:
            result = simulate_fill(intent, quotes[intent.symbol], rules[intent.symbol], COST, book)
            if result.accepted:
                book.apply_fill(intent.side, intent.symbol, result.quantity, result.price, COST.fee)
        return book
    forward, reverse = execute(SYMBOLS), execute(list(reversed(SYMBOLS)))
    assert forward.cash >= 0 and forward.cash == reverse.cash
    assert all(forward.positions[s].quantity == reverse.positions[s].quantity for s in SYMBOLS)
    assert sum(p.quantity * D('10') for p in forward.positions.values()) <= D('100')


def test_target_net_quantity_accounts_for_buy_fee_and_sells_first():
    book = Portfolio('100', SYMBOLS)
    book.apply_fill('BUY', 'BTCUSDT', '5', '10', '0')
    quotes = {s: quote() for s in SYMBOLS}
    orders = plan_rebalance({'BTCUSDT': D('0'), 'ETHUSDT': D('0.30'), 'SOLUSDT': D('0.30')}, book, quotes, {s: rule(s) for s in SYMBOLS}, COST)
    assert orders[0].side == 'SELL' and orders[0].reason == 'strategy_exit'
    assert orders[1].quantity == D('3.003')

from decimal import Decimal as D

import pytest

from cryptoquant.trading.ledger import Portfolio

SYMBOLS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT']


def test_round_trip_fees_are_charged_once():
    book = Portfolio(D('100'), SYMBOLS)
    book.apply_fill('BUY', 'ETHUSDT', D('2'), D('10'), D('0.001'))
    assert book.cash == D('80') and book.positions['ETHUSDT'].quantity == D('1.998')
    assert book.equity({'ETHUSDT': D('10')}) == D('99.98')
    book.apply_fill('SELL', 'ETHUSDT', D('1.998'), D('10'), D('0.001'))
    assert book.cash == D('99.96002') and book.fees_usdt == D('0.03998')
    assert book.positions['ETHUSDT'].quantity == 0
    assert book.realized_pnl == D('-0.03998')


def test_average_cost_accounts_for_fee_and_survives_partial_sell():
    book = Portfolio('100', SYMBOLS)
    book.apply_fill('BUY', 'ETHUSDT', '2', '10', '0.001')
    book.apply_fill('BUY', 'ETHUSDT', '1', '40', '0.001')
    assert book.cash == D('40')
    position = book.positions['ETHUSDT']
    assert position.average_cost == D('60') / D('2.997')
    cost = position.average_cost
    book.apply_fill('SELL', 'ETHUSDT', '0.999', '50', '0.001')
    assert position.quantity == D('1.998') and position.average_cost == cost


def test_symbols_share_cash_and_rejected_fill_does_not_mutate():
    book = Portfolio('100', SYMBOLS)
    for symbol in SYMBOLS[:2]:
        book.apply_fill('BUY', symbol, '4', '10', '0')
    with pytest.raises(ValueError, match='cash'):
        book.apply_fill('BUY', SYMBOLS[2], '4', '10', '0')
    assert book.cash == D('20') and book.positions[SYMBOLS[2]].quantity == 0
    assert book.equity({s: D('10') for s in SYMBOLS}) == D('100')


@pytest.mark.parametrize('side,quantity,price,fee', [
    ('BUY', '-1', '10', '0'), ('BUY', '1', 'nan', '0'),
    ('BUY', '1', '10', '1'), ('BUY', 1.0, '10', '0'),
    ('SELL', '1', '10', '0'), ('INVALID', '1', '10', '0'),
])
def test_invalid_fill_is_atomic(side, quantity, price, fee):
    book = Portfolio('100', SYMBOLS)
    with pytest.raises(ValueError):
        book.apply_fill(side, SYMBOLS[0], quantity, price, fee)
    assert book.cash == D('100') and book.fees_usdt == 0


def test_held_asset_requires_a_real_or_explicit_stale_mark():
    book = Portfolio('100', SYMBOLS)
    book.apply_fill('BUY', SYMBOLS[0], '1', '10', '0')
    with pytest.raises(ValueError, match='mark'):
        book.equity({})

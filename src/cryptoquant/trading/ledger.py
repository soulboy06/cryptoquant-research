"""现金与持仓统一记账；数量、价格和费用均使用 Decimal。"""

from dataclasses import dataclass
from decimal import Decimal

from cryptoquant.config import decimal_text

ZERO = Decimal('0')


def amount(value):
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError('non-finite amount')
        return value
    return decimal_text(value)


@dataclass
class Position:
    quantity: Decimal = ZERO
    average_cost: Decimal = ZERO


class Portfolio:
    def __init__(self, initial_cash, symbols):
        self.cash = amount(initial_cash)
        if self.cash <= 0 or not symbols or len(symbols) != len(set(symbols)):
            raise ValueError('invalid initial portfolio')
        self.initial_cash = self.cash
        self.positions = {symbol: Position() for symbol in sorted(symbols)}
        self.fees_usdt = ZERO
        self.realized_pnl = ZERO
        self.turnover_usdt = ZERO
        self.dust_writeoff_value = ZERO
        self.dust_writeoff_cost = ZERO

    def write_off_precision_dust(self, symbol, step_size, mark):
        """Explicit simulated abandonment, not a fill; only a sub-step quantity.

        Caller must prove a real full-exit sell occurred. Cash/fees are unchanged,
        cost becomes a realized loss and the actual simulated position is zero.
        """
        position = self.positions[symbol]
        if not ZERO < position.quantity < amount(step_size) or amount(mark) <= ZERO:
            raise ValueError('only strictly sub-step precision dust may be written off')
        quantity = position.quantity
        cost = quantity * position.average_cost
        value = quantity * amount(mark)
        self.realized_pnl -= cost
        self.dust_writeoff_cost += cost
        self.dust_writeoff_value += value
        position.quantity, position.average_cost = ZERO, ZERO
        return dict(quantity=quantity, cost_usdt=cost, value_usdt=value)

    def apply_fill(self, side, symbol, gross_quantity, execution_price, fee_rate):
        quantity, price, fee = map(amount, (gross_quantity, execution_price, fee_rate))
        if side not in {'BUY', 'SELL'} or symbol not in self.positions or quantity <= 0 or price <= 0 or not 0 <= fee < 1:
            raise ValueError('invalid fill')
        position = self.positions[symbol]
        notional = quantity * price
        if side == 'BUY':
            if notional > self.cash:
                raise ValueError('insufficient cash')
            received = quantity * (1 - fee)
            cost = position.quantity * position.average_cost + notional
            new_quantity = position.quantity + received
            new_average = cost / new_quantity
            self.cash -= notional
            position.quantity, position.average_cost = new_quantity, new_average
        else:
            if quantity > position.quantity:
                raise ValueError('insufficient holding')
            proceeds = notional * (1 - fee)
            self.realized_pnl += proceeds - quantity * position.average_cost
            self.cash += proceeds
            position.quantity -= quantity
            if position.quantity == 0:
                position.average_cost = ZERO
        self.fees_usdt += notional * fee
        self.turnover_usdt += notional

    def equity(self, mark_prices):
        result = self.cash
        for symbol, position in self.positions.items():
            if position.quantity:
                if symbol not in mark_prices or mark_prices[symbol] is None:
                    raise ValueError(f'missing mark for held asset: {symbol}')
                price = amount(mark_prices[symbol])
                if price <= 0:
                    raise ValueError('invalid mark')
                result += position.quantity * price
        return result

"""市价成交近似、规则约束与统一资金分配；不修改真实账户。"""

from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal

from cryptoquant.data.calendar import can_execute
from cryptoquant.data.rules import round_market_quantity
from cryptoquant.trading.ledger import amount, ZERO


@dataclass(frozen=True)
class Intent:
    symbol: str
    side: str
    quantity: Decimal
    reason: str = 'rebalance'
    risk: bool = False


@dataclass(frozen=True)
class Decision:
    accepted: bool
    reason: str
    quantity: Decimal = ZERO
    price: Decimal = ZERO

    @property
    def notional(self):
        return self.quantity * self.price


def execution_price(side, reference, cost):
    return amount(reference) * (1 + cost.adverse_price if side == 'BUY' else 1 - cost.adverse_price)


def sellable_quantity(quantity, reference, rules, cost):
    price = execution_price('SELL', reference, cost)
    limits = [amount(quantity)]
    if rules.max_quantity is not None:
        limits.append(rules.max_quantity)
    if rules.max_notional is not None:
        limits.append(rules.max_notional / price)
    result = round_market_quantity(min(limits), rules)
    return result if result >= rules.min_quantity and result * price >= rules.min_notional else ZERO


def simulate_fill(intent, open_quote, rules, cost, portfolio, *, check_cash=True):
    if intent.symbol != rules.symbol or intent.symbol not in portfolio.positions or intent.side not in {'BUY', 'SELL'}:
        raise ValueError('invalid order identity')
    if open_quote is None or not can_execute(open_quote):
        return Decision(False, 'no_quote')
    reference = amount(open_quote['open'])
    if reference <= 0 or not 0 <= cost.fee < 1 or not 0 <= cost.adverse_price < 1:
        raise ValueError('invalid cost or quote')
    price = execution_price(intent.side, reference, cost)
    quantity = amount(intent.quantity)
    if quantity < 0:
        raise ValueError('negative requested quantity')
    if intent.side == 'SELL':
        quantity = min(quantity, portfolio.positions[intent.symbol].quantity)
        if intent.risk:
            quantity = sellable_quantity(quantity, reference, rules, cost)
    quantity = round_market_quantity(quantity, rules)
    if quantity == 0:
        return Decision(False, 'zero_quantity', quantity, price)
    if quantity < rules.min_quantity:
        return Decision(False, 'minimum_quantity', quantity, price)
    if rules.max_quantity is not None and quantity > rules.max_quantity:
        return Decision(False, 'maximum_quantity', quantity, price)
    notional = quantity * price
    if notional < rules.min_notional:
        return Decision(False, 'minimum_notional', quantity, price)
    if rules.max_notional is not None and notional > rules.max_notional:
        return Decision(False, 'maximum_notional', quantity, price)
    if intent.side == 'BUY':
        if rules.max_position is not None and portfolio.positions[intent.symbol].quantity + quantity > rules.max_position:
            return Decision(False, 'maximum_position', quantity, price)
        if check_cash and notional > portfolio.cash:
            return Decision(False, 'insufficient_cash', quantity, price)
    return Decision(True, 'filled', quantity, price)


def plan_rebalance(target_weights, portfolio, all_open_quotes, rules, cost, *, mark_prices=None):
    """固定同一开盘净值；先模拟合法卖单，再同比缩放全部合法买单。"""
    weights = {symbol: amount(weight) for symbol, weight in target_weights.items() if weight is not None}
    if not set(weights) <= set(portfolio.positions) or any(w < 0 for w in weights.values()) or sum(weights.values()) > 1:
        raise ValueError('invalid target weights')
    marks = dict(mark_prices or {})
    for symbol, quote in all_open_quotes.items():
        if quote is not None and can_execute(quote):
            marks[symbol] = amount(quote['open'])
    equity = portfolio.equity(marks)
    sells, buys = [], []
    for symbol in sorted(weights):
        quote = all_open_quotes.get(symbol)
        if quote is None or not can_execute(quote):
            # No price supports an amount calculation; log a rejected intent.
            intent = Intent(symbol, 'SELL' if weights[symbol] == 0 else 'BUY', ZERO, 'strategy_exit' if weights[symbol] == 0 else 'rebalance')
            sells.append(intent) if intent.side == 'SELL' else buys.append(intent)
            continue
        target = equity * weights[symbol] / amount(quote['open'])
        difference = target - portfolio.positions[symbol].quantity
        if difference < 0:
            sells.append(Intent(symbol, 'SELL', -difference, 'strategy_exit' if weights[symbol] == 0 else 'rebalance'))
        elif difference > 0:
            buys.append(Intent(symbol, 'BUY', difference / (1 - cost.fee)))
    ghost = deepcopy(portfolio)
    for intent in sells:
        decision = simulate_fill(intent, all_open_quotes.get(intent.symbol), rules[intent.symbol], cost, ghost)
        if decision.accepted:
            ghost.apply_fill(intent.side, intent.symbol, decision.quantity, decision.price, cost.fee)
    preliminary = {intent.symbol: simulate_fill(intent, all_open_quotes.get(intent.symbol), rules[intent.symbol], cost, ghost, check_cash=False) for intent in buys}
    demand = sum(item.notional for item in preliminary.values() if item.accepted)
    scale = min(Decimal('1'), ghost.cash / demand) if demand else Decimal('1')
    funded = [Intent(intent.symbol, intent.side, round_market_quantity(preliminary[intent.symbol].quantity * scale, rules[intent.symbol]) if preliminary[intent.symbol].accepted else intent.quantity, intent.reason) for intent in buys]
    return sells + funded

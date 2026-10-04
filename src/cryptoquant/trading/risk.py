"""固定本金底线、单币待退出、真实时间冷却与持仓周期。"""

from dataclasses import dataclass
from datetime import timedelta

from cryptoquant.data.calendar import can_execute
from cryptoquant.trading.ledger import ZERO, amount
from cryptoquant.trading.orders import sellable_quantity


@dataclass
class SymbolState:
    pending: str | None = None
    trigger_time: object = None
    cooldown_until: object = None
    cycle_open: bool = False
    had_exit_fill: bool = False
    exit_completed: bool = False
    entry_time: object = None
    holding_hours: int = 0
    max_return_observed: object = ZERO
    breakeven_active: bool = False


class RiskState:
    def __init__(self, symbols, floor, stop_loss, cooldown_hours, *,
                 max_holding_hours=None, breakeven_activation=None, breakeven_ratio=None):
        self.states = {symbol: SymbolState() for symbol in sorted(symbols)}
        self.floor = amount(floor)
        self.stop_loss = amount(stop_loss)
        self.cooldown_hours = cooldown_hours
        self.max_holding_hours = int(max_holding_hours) if max_holding_hours is not None else None
        self.breakeven_activation = amount(breakeven_activation) if breakeven_activation is not None else None
        self.breakeven_ratio = amount(breakeven_ratio) if breakeven_ratio is not None else None
        self.locked = False
        self.floor_triggers = 0
        self.stop_triggers = 0
        self.breakeven_triggers = 0
        self.duration_triggers = 0
        self.closed_cycles = 0
        self.events = []

    def emit(self, kind, timestamp, **fields):
        self.events.append({'time': timestamp, 'event': kind, **fields})

    def request_exit(self, symbol, reason, timestamp):
        state = self.states[symbol]
        if state.pending is None or (reason == 'floor' and state.pending != 'floor'):
            if state.pending is None:
                state.had_exit_fill = False
                state.trigger_time = timestamp
            state.pending = reason
            if reason == 'stop_loss':
                self.stop_triggers += 1
            elif reason == 'breakeven_exit':
                self.breakeven_triggers += 1
            elif reason == 'max_duration_exit':
                self.duration_triggers += 1
            self.emit('exit_requested', timestamp, symbol=symbol, reason=reason)

    def observe(self, portfolio, marks, fresh_symbols, timestamp, active=True, *, allow_single_stops=True):
        if not fresh_symbols:
            return
        equity = portfolio.equity(marks)
        if equity <= self.floor and not self.locked:
            self.locked = True
            self.floor_triggers += 1
            self.emit('floor_triggered', timestamp, equity=equity)
            for symbol, position in portfolio.positions.items():
                if position.quantity:
                    self.request_exit(symbol, 'floor', timestamp)
        if active and not self.locked:
            for symbol in sorted(fresh_symbols):
                position = portfolio.positions[symbol]
                state = self.states[symbol]
                if position.quantity and not state.exit_completed:
                    state.holding_hours += 1
                    cost_basis = position.average_cost
                    if cost_basis > 0:
                        float_return = (marks[symbol] - cost_basis) / cost_basis
                        if float_return > state.max_return_observed:
                            state.max_return_observed = float_return
                        if self.breakeven_activation is not None and float_return >= self.breakeven_activation:
                            state.breakeven_active = True

                    if allow_single_stops:
                        if marks[symbol] <= cost_basis * (1 - self.stop_loss):
                            self.request_exit(symbol, 'stop_loss', timestamp)
                        elif state.breakeven_active and self.breakeven_ratio is not None and marks[symbol] <= cost_basis * (1 + self.breakeven_ratio):
                            self.request_exit(symbol, 'breakeven_exit', timestamp)
                        elif self.max_holding_hours is not None and state.holding_hours >= self.max_holding_hours:
                            self.request_exit(symbol, 'max_duration_exit', timestamp)

    def can_buy(self, symbol, timestamp):
        state = self.states[symbol]
        decision_point = timestamp.hour % 4 == 0 and timestamp.minute == timestamp.second == timestamp.microsecond == 0
        return decision_point and not self.locked and state.pending is None and (state.cooldown_until is None or timestamp >= state.cooldown_until)

    def register_buy(self, symbol, portfolio, reference, rules, cost, timestamp=None):
        state = self.states[symbol]
        if not state.cycle_open and sellable_quantity(portfolio.positions[symbol].quantity, reference, rules, cost):
            state.cycle_open = True
            state.had_exit_fill = False
            state.exit_completed = False
            state.holding_hours = 0
            state.max_return_observed = ZERO
            state.breakeven_active = False
            state.entry_time = timestamp

    def register_full_exit_fill(self, symbol):
        self.states[symbol].had_exit_fill = True

    def complete_exit_if_tail(self, symbol, portfolio, open_quote, rules, cost, timestamp):
        if open_quote is None or not can_execute(open_quote):
            return False
        state = self.states[symbol]
        if sellable_quantity(portfolio.positions[symbol].quantity, open_quote['open'], rules, cost):
            return False
        if state.cycle_open and state.had_exit_fill:
            self.closed_cycles += 1
            self.emit('cycle_closed', timestamp, symbol=symbol)
        reason = state.pending
        state.pending, state.cycle_open, state.had_exit_fill = None, False, False
        state.exit_completed = True
        state.holding_hours = 0
        state.max_return_observed = ZERO
        state.breakeven_active = False
        if reason in {'stop_loss', 'breakeven_exit', 'max_duration_exit'}:
            state.cooldown_until = timestamp + timedelta(hours=self.cooldown_hours)
        self.emit('exit_complete', timestamp, symbol=symbol, reason=reason, residual_quantity=portfolio.positions[symbol].quantity, cooldown_until=state.cooldown_until)
        return True

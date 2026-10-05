"""共用事件循环：已知收盘 → 风控 → 当前开盘 → 卖出 → 买入。"""

from dataclasses import dataclass
import math

import pandas as pd

from cryptoquant.baselines.strategies import TrendSignals
from cryptoquant.baselines.periods import period_bounds
from cryptoquant.data.calendar import can_execute
from cryptoquant.trading.ledger import Portfolio, amount, ZERO
from cryptoquant.trading.orders import Intent, plan_rebalance, simulate_fill
from cryptoquant.trading.risk import RiskState


@dataclass
class BacktestResult:
    book: Portfolio
    marks: dict
    orders: list
    fills: list
    equity: list
    signals: list
    risk: RiskState
    strategy: str
    cost_name: str
    period: str = 'development'
    window: str | None = None
    exit_variant: str | None = None


def validate_frames(frames, config, period='development', *, window=None):
    if set(frames) != set(config.symbols):
        raise ValueError('symbol mismatch')
    start, end = map(pd.Timestamp, period_bounds(config, period, window=window))
    grid = pd.date_range(start - pd.Timedelta(744, unit='h'), end, freq='h')
    records = {}
    for symbol, frame in frames.items():
        if not pd.DatetimeIndex(frame.open_time).equals(grid) or not (frame.symbol == symbol).all():
            raise ValueError('calendar mismatch')
        if not frame.market_state.isin(['observed', 'no_trade', 'halt']).all():
            raise ValueError('unknown market state')
        expected_role = ['warmup' if t < start else 'boundary' if t == end else 'evaluation' for t in grid]
        if frame.row_role.tolist() != expected_role:
            raise ValueError('invalid row roles')
        boundary = frame.iloc[-1]
        safe = {'symbol', 'open_time', 'open', 'source_id', 'row_role', 'market_state'}
        if any(pd.notna(boundary[column]) for column in frame.columns if column not in safe):
            raise ValueError('boundary exposes future fields')
        for row in frame.iloc[:-1].to_dict('records'):
            if can_execute(row):
                if pd.isna(row['available_time']) or row['available_time'] != row['open_time'] + pd.Timedelta(1, unit='h'):
                    raise ValueError('invalid close availability')
                if amount(row['open']) <= 0 or amount(row['close']) <= 0:
                    raise ValueError('invalid observed price')
        records[symbol] = frame.to_dict('records')
    return grid, records


def run_backtest(frames, rules, config, strategy, cost_name, period='development', decision_targets=None, *, window=None,
                 exit_variant=None, max_holding_hours=None, breakeven_activation=None, breakeven_ratio=None):
    """独立账户评价；window模型信号须来自原连续历史特征。

    ema_trend在此循环重算EMA，744h视图会改变连续历史，故拒绝window。
    """
    if strategy not in {'buy_hold', 'ema_trend', 'logistic_regression'} or cost_name not in config.costs:
        raise ValueError('unsupported baseline or cost')
    if set(rules) != set(config.symbols):
        raise ValueError('rule symbol mismatch')
    start, end = map(pd.Timestamp, period_bounds(config, period, window=window))
    if window is not None and strategy == 'ema_trend':
        raise ValueError('ema_trend window requires continuous EMA history; unsupported')
    grid, rows = validate_frames(frames, config, period, window=window)
    external = {}
    if strategy == 'logistic_regression':
        columns = ['symbol', 'decision_time', 'probability', 'target_weight']
        if decision_targets is None or list(decision_targets.columns) != columns:
            raise ValueError('invalid decision target columns; no labels allowed')
        for row in decision_targets.to_dict('records'):
            time, symbol = pd.Timestamp(row['decision_time']), row['symbol']
            if symbol not in config.symbols or time.tz is None or time.utcoffset().total_seconds() != 0 or time != time.floor('4h') or not start <= time < end:
                raise ValueError('invalid decision time or symbol')
            key = (time, symbol)
            if key in external:
                raise ValueError('duplicate decision target')
            probability, weight = row['probability'], row['target_weight']
            if not pd.isna(probability) and (not math.isfinite(probability) or not 0 <= probability <= 1):
                raise ValueError('invalid decision probability')
            if pd.isna(weight):
                row['target_weight'] = None
            elif amount(weight) not in {ZERO, config.weight_per_symbol} or pd.isna(probability):
                raise ValueError('invalid decision target weight')
            external[key] = row
        expected = {(t, s) for t in grid if start <= t < end and t.hour % 4 == 0 for s in config.symbols}
        if set(external) != expected:
            raise ValueError('incomplete decision targets')
    elif decision_targets is not None:
        raise ValueError('external targets require model strategy')
    if exit_variant == 'C0':
        max_holding_hours = None
        breakeven_activation = None
        breakeven_ratio = None
    elif exit_variant == 'C1':
        max_holding_hours = 8
        breakeven_activation = None
        breakeven_ratio = None
    elif exit_variant == 'C2':
        max_holding_hours = None
        breakeven_activation = amount('0.0120')
        breakeven_ratio = amount('0.0025')
    elif exit_variant == 'C3':
        max_holding_hours = 8
        breakeven_activation = amount('0.0120')
        breakeven_ratio = amount('0.0025')
    elif exit_variant is not None:
        raise ValueError(f'unsupported exit variant: {exit_variant}')

    book = Portfolio(config.initial_cash, config.symbols)
    risk = RiskState(
        config.symbols, config.equity_floor, config.stop_loss, config.cooldown_hours,
        max_holding_hours=max_holding_hours,
        breakeven_activation=breakeven_activation,
        breakeven_ratio=breakeven_ratio,
    )
    trend, cost = TrendSignals(config.symbols), config.costs[cost_name]
    active = strategy in {'ema_trend', 'logistic_regression'}
    symbols = sorted(config.symbols)
    marks, mark_times, orders, fills, equity, signals = {}, {}, [], [], [], []

    def snapshot(time, phase, quotes=None):
        value = book.equity(marks)
        stale = [s for s in symbols if book.positions[s].quantity and
                 (mark_times.get(s) != time or (quotes is not None and not can_execute(quotes[s])))]
        row = dict(time=time, phase=phase, cash=book.cash, equity=value,
                   exposure=(value - book.cash) / value if value else ZERO,
                   stale_symbols=','.join(stale), locked=risk.locked)
        for s in symbols:
            row[s + '_quantity'] = book.positions[s].quantity
            row[s + '_mark'] = marks.get(s)
            row[s + '_mark_time'] = mark_times.get(s)
            row[s + '_mark_age_hours'] = (time - mark_times[s]).total_seconds() / 3600 if s in mark_times else None
        equity.append(row)

    def execute(intent, time, quotes, full_exit=False):
        decision = simulate_fill(intent, quotes.get(intent.symbol), rules[intent.symbol], cost, book)
        record = dict(time=time, symbol=intent.symbol, side=intent.side,
                      requested_quantity=intent.quantity, quantity=decision.quantity,
                      price=decision.price, accepted=decision.accepted, reason=decision.reason,
                      intent_reason=intent.reason, source_id=quotes[intent.symbol].get('source_id'))
        orders.append(record)
        if decision.accepted:
            book.apply_fill(intent.side, intent.symbol, decision.quantity, decision.price, cost.fee)
            fills.append(record | dict(notional=decision.notional, fee_usdt=decision.notional * cost.fee,
                                       fee_asset=intent.symbol.removesuffix('USDT') if intent.side == 'BUY' else 'USDT',
                                       fee_quantity=decision.quantity * cost.fee if intent.side == 'BUY' else decision.notional * cost.fee,
                                       cash_after=book.cash, holding_after=book.positions[intent.symbol].quantity))
            if intent.side == 'BUY':
                risk.register_buy(intent.symbol, book, quotes[intent.symbol]['open'], rules[intent.symbol], cost, time)
            elif full_exit:
                risk.register_full_exit_fill(intent.symbol)
        if full_exit:
            risk.complete_exit_if_tail(intent.symbol, book, quotes[intent.symbol], rules[intent.symbol], cost, time)

    for i, time in enumerate(grid):
        fresh_closes = set()
        if i:
            for symbol in symbols:
                previous = rows[symbol][i - 1]
                trend.observe(symbol, previous, time)
                if can_execute(previous):
                    marks[symbol] = amount(previous['close'])
                    mark_times[symbol] = time
                    fresh_closes.add(symbol)
        if time < start:
            continue
        if time == start:
            snapshot(time, 'initial')
        else:
            risk.observe(book, marks, fresh_closes, time, active=active)
            snapshot(time, 'close')
        quotes = {s: rows[s][i] for s in symbols}
        fresh_opens = {s for s in symbols if can_execute(quotes[s])}
        for symbol in fresh_opens:
            marks[symbol], mark_times[symbol] = amount(quotes[symbol]['open']), time
        # An outage can conceal a gap through the floor. Check the first real
        # resumed open before execution; single-coin stops still use closes.
        recovered = {s for s in fresh_opens if i and not can_execute(rows[s][i - 1])}
        if recovered:
            risk.observe(book, marks, fresh_opens, time, active=False, allow_single_stops=False)
        terminal = time == end
        blocked = set()
        for symbol in symbols:
            state = risk.states[symbol]
            if terminal:
                if book.positions[symbol].quantity:
                    execute(Intent(symbol, 'SELL', book.positions[symbol].quantity, 'terminal', True), time, quotes, True)
            elif state.pending:
                blocked.add(symbol)
                execute(Intent(symbol, 'SELL', book.positions[symbol].quantity, state.pending, True), time, quotes, True)
        if terminal:
            snapshot(time, 'terminal', quotes)
            break
        decision_point = time.hour % 4 == 0
        weights = None
        if strategy == 'buy_hold' and time == start:
            weights = {s: config.weight_per_symbol for s in symbols}
        elif strategy == 'logistic_regression' and decision_point:
            weights = {s: external[(time, s)]['target_weight'] for s in symbols}
            signals.extend(dict(time=time, symbol=s, weight=weights[s], probability=external[(time, s)]['probability']) for s in symbols)
        elif strategy == 'ema_trend' and decision_point:
            weights = trend.weights(config.weight_per_symbol)
            for s in symbols:
                state = trend.history[s]
                signals.append(dict(time=time, symbol=s, weight=weights[s], history_count=state.count,
                                    ema24=state.fast, ema72=state.slow))
        if weights is not None:
            eligible = {s: w for s, w in weights.items() if s not in blocked and not risk.locked}
            # Cold symbols cannot consume the cash scaling budget of legal buys.
            for s, w in list(eligible.items()):
                if w is not None and w > 0 and not risk.can_buy(s, time):
                    eligible.pop(s)
                    orders.append(dict(time=time, symbol=s, side='BUY', requested_quantity=ZERO,
                                       accepted=False, reason='risk_blocked', intent_reason='cooldown', quantity=ZERO, price=ZERO))
            intents = plan_rebalance(eligible, book, quotes, rules, cost, mark_prices=marks)
            for intent in intents:
                if intent.side == 'BUY' and not risk.can_buy(intent.symbol, time):
                    orders.append(dict(time=time, symbol=intent.symbol, side='BUY', requested_quantity=intent.quantity,
                                       accepted=False, reason='risk_blocked', intent_reason=intent.reason, quantity=ZERO, price=ZERO))
                else:
                    execute(intent, time, quotes, full_exit=intent.reason == 'strategy_exit')
        snapshot(time, 'open', quotes)
    return BacktestResult(book, marks, orders, fills, equity, signals, risk, strategy, cost_name, period, window, exit_variant)

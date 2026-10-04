"""逐根已收盘观察计算 EMA；停机后重新预热，不读取未来字段。"""

from dataclasses import dataclass
import math

from cryptoquant.data.calendar import can_execute


@dataclass
class History:
    count: int = 0
    fast: float | None = None
    slow: float | None = None


class TrendSignals:
    def __init__(self, symbols):
        self.history = {symbol: History() for symbol in symbols}

    def observe(self, symbol, closed_row, decision_time):
        state = self.history[symbol]
        if not can_execute(closed_row):
            self.history[symbol] = History()
            return
        if closed_row['available_time'] > decision_time:
            raise ValueError('unavailable future close')
        close = float(closed_row['close'])
        if not math.isfinite(close) or close <= 0:
            raise ValueError('invalid close for EMA')
        state.fast = close if state.fast is None else state.fast + (close - state.fast) * (2 / 25)
        state.slow = close if state.slow is None else state.slow + (close - state.slow) * (2 / 73)
        state.count += 1

    def weights(self, weight):
        return {symbol: None if state.count < 744 else weight if state.fast > state.slow else weight * 0
                for symbol, state in self.history.items()}

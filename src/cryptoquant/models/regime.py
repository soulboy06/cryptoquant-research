"""冻结的BTC共同市场状态：仅消费已闭合小时OHLC，不接模型或标签。

输入须为REGIME_INPUT_COLUMNS这九列、完整UTC小时日历。已核验停机／
no_trade重置指标段；损坏行情直接失败。输出每4h唯一状态，available_time
表示该闭合小时及其可用／停机状态已知的时刻；停机输入本身不伪造报价。
"""
import numpy as np
import pandas as pd

from cryptoquant.data.calendar import known_halts, known_no_trade_bars

HOUR = pd.Timedelta(1, unit='h')
REGIME_INPUT_COLUMNS = ['symbol', 'open_time', 'available_time', 'open', 'high',
                        'low', 'close', 'market_state', 'row_role']
REGIME_OUTPUT_COLUMNS = ['decision_time', 'available_time', 'adx14', 'ema72',
                         'slope24', 'history_count', 'state_valid', 'allow_buy']


def _validate_input(frame):
    if (frame.empty or frame.columns.duplicated().any()
            or set(frame) != set(REGIME_INPUT_COLUMNS)):
        raise ValueError('regime input requires only whitelisted closed OHLC fields')
    frame = frame.reset_index(drop=True).copy()
    for name in ['open_time', 'available_time']:
        if str(getattr(frame[name].dtype, 'tz', None)) != 'UTC':
            raise ValueError('regime timestamps must be UTC datetime')
    times = pd.DatetimeIndex(frame.open_time)
    if (times.hasnans or not times.equals(times.floor('h'))
            or not times.equals(pd.date_range(times[0], times[-1], freq='h'))):
        raise ValueError('regime calendar contains a missing, duplicate or conflicting hour')
    if (not frame.symbol.eq('BTCUSDT').all()
            or not frame.row_role.isin(['warmup', 'evaluation']).all()
            or not frame.market_state.isin(['observed', 'no_trade', 'halt']).all()):
        raise ValueError('regime requires BTC closed history with valid roles and market state')
    halted = frame.open_time.isin(known_halts('BTCUSDT', times[0], times[-1] + HOUR, 'halt_aware_v2'))
    no_trade = frame.open_time.isin(known_no_trade_bars('BTCUSDT', times[0], times[-1] + HOUR, 'halt_aware_v2'))
    if (not (frame.market_state.eq('halt') == halted).all()
            or not (frame.market_state.eq('no_trade') == no_trade).all()):
        raise ValueError('unverified or conflicting halt/no_trade state')
    price_names = ['open', 'high', 'low', 'close']
    if frame.loc[halted, price_names + ['available_time']].notna().any().any():
        raise ValueError('halt must have empty prices and close availability')
    priced = ~halted
    if not (frame.loc[priced, 'available_time'] == frame.loc[priced, 'open_time'] + HOUR).all():
        raise ValueError('closed OHLC availability conflicts with hourly clock')
    try:
        values = frame.loc[priced, price_names].apply(pd.to_numeric, errors='raise').astype(float)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError('invalid OHLC numeric price') from exc
    if (not np.isfinite(values.to_numpy()).all() or (values <= 0).any().any()
            or (values.high < values[['open', 'close', 'low']].max(axis=1)).any()
            or (values.low > values[['open', 'close', 'high']].min(axis=1)).any()):
        raise ValueError('invalid, missing or inconsistent OHLC price')
    for name in price_names:
        frame[name] = pd.to_numeric(frame[name], errors='raise').astype(float)
    return frame


def _seeded_smoothing(values, period, alpha):
    """Leading missing values stay missing; first period actual values seed mean."""
    output = np.full(len(values), np.nan)
    indexes = np.flatnonzero(np.isfinite(values))
    if len(indexes) < period:
        return output
    first = indexes[0]
    if not np.isfinite(values[first:]).all():
        raise ValueError('missing indicator observation inside a continuous segment')
    seed = first + period - 1
    output[seed] = np.mean(values[first:seed + 1])
    for i in range(seed + 1, len(values)):
        output[i] = (1 - alpha) * output[i - 1] + alpha * values[i]
    return output


def _ratio(numerator, denominator):
    output = np.full(len(numerator), np.nan)
    finite = np.isfinite(numerator) & np.isfinite(denominator)
    output[finite & (denominator == 0)] = 0
    np.divide(numerator, denominator, out=output, where=finite & (denominator != 0))
    return output


def build_market_regime(frame):
    """Return fixed ADX14/EMA72/slope24 and BUY permission on the UTC4h grid.

    t consumes open_time=t-1h, available_time=t; no t candle is read at t.
    First TR/DM requires a prior closed candle, hence ADX seed at hour28.
    Slope requires 24 subsequent EMA observations; validity also requires744h.
    """
    frame = _validate_input(frame)
    decisions = frame.open_time + HOUR
    observed = frame.market_state.eq('observed')
    segments = (~observed).cumsum()
    counts = observed.groupby(segments).cumsum().astype('int64')
    output = pd.DataFrame(dict(decision_time=decisions, available_time=decisions,
                               adx14=np.nan, ema72=np.nan, slope24=np.nan,
                               history_count=counts))
    for _, part in frame.loc[observed].groupby(segments[observed], sort=False):
        high, low, close = [part[name].to_numpy() for name in ['high', 'low', 'close']]
        previous = np.r_[np.nan, close[:-1]]
        tr = np.maximum.reduce([high - low, np.abs(high - previous), np.abs(low - previous)])
        up, down = np.r_[np.nan, np.diff(high)], np.r_[np.nan, -np.diff(low)]
        plus = np.where((up > down) & (up > 0), up, 0.)
        minus = np.where((down > up) & (down > 0), down, 0.)
        plus[0] = minus[0] = np.nan
        # Wilder's mean-seed RMA; no pandas ewm implicit first-value seed.
        rma_tr = _seeded_smoothing(tr, 14, 1 / 14)
        positive = 100 * _ratio(_seeded_smoothing(plus, 14, 1 / 14), rma_tr)
        negative = 100 * _ratio(_seeded_smoothing(minus, 14, 1 / 14), rma_tr)
        dx = 100 * _ratio(np.abs(positive - negative), positive + negative)
        adx = _seeded_smoothing(dx, 14, 1 / 14)
        ema = _seeded_smoothing(close, 72, 2 / 73)
        slope = np.full(len(part), np.nan)
        if len(part) > 24:
            slope[24:] = _ratio(ema[24:], ema[:-24]) - 1
        output.loc[part.index, ['adx14', 'ema72', 'slope24']] = np.column_stack([adx, ema, slope])
    finite = np.isfinite(output[['adx14', 'ema72', 'slope24']].to_numpy()).all(axis=1)
    output['state_valid'] = observed & (counts >= 744) & finite
    output['allow_buy'] = output.state_valid & (output.adx14 >= 20) & (output.slope24 > 0)
    result = output.loc[decisions.dt.hour % 4 == 0, REGIME_OUTPUT_COLUMNS].reset_index(drop=True)
    if not result.empty:
        expected = pd.date_range(result.decision_time.iloc[0], result.decision_time.iloc[-1], freq='4h')
        if not pd.DatetimeIndex(result.decision_time).equals(expected):
            raise ValueError('incomplete four-hour regime clock')
    return result

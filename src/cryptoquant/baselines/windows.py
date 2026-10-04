"""已核验分区的执行视图与连续历史特征分开截取。

调用者先用load_period核对原Config、政策及SHA；本模块不读源文件。
执行视图只给账本使用。模型必须先在原分区连续历史上build_features，
再用select_window_features截取，不能在744h执行视图上重算EMA／历史计数。
旧ema_trend在引擎内重算EMA，因此暂不支持研究window。
"""

import pandas as pd

from cryptoquant.baselines.engine import validate_frames
from cryptoquant.baselines.periods import period_bounds


def window_frames(verified_frames, config, period, window):
    """拷贝[start-744h,end]并屏蔽清算行未来字段，保留空停机行。"""
    start, end = map(pd.Timestamp, period_bounds(config, period, window=window))
    if window is None:
        raise ValueError('execution window must be explicit')
    validate_frames(verified_frames, config, period)
    output = {}
    safe = {'symbol', 'open_time', 'open', 'source_id', 'row_role', 'market_state'}
    for symbol, frame in verified_frames.items():
        halt = frame.market_state == 'halt'
        quote_columns = set(frame) & {'open', 'close', 'high', 'low', 'volume', 'quote_volume', 'available_time'}
        if frame.loc[halt, list(quote_columns)].notna().any().any():
            raise ValueError('halt row must have empty prices, volumes and close availability')
        view = frame.loc[frame.open_time.between(start - pd.Timedelta(744, unit='h'), end)].copy().reset_index(drop=True)
        view['row_role'] = 'evaluation'
        view.loc[view.open_time < start, 'row_role'] = 'warmup'
        boundary = view.open_time == end
        view.loc[boundary, 'row_role'] = 'boundary'
        for column in set(view) - safe:
            view[column] = view[column].where(~boundary)
        output[symbol] = view
    validate_frames(output, config, period, window=window)
    return output


def select_window_features(feature_frames, config, period, window):
    """选择预先算好的特征；不fit、不重算，也不消费事后标签。

完整历史／特征版本由准备阶段的来源manifest核验。这里检查币种、
决策唯一性、全部4h决策及有效特征可获得时刻；无效特征仍留在网格。
"""
    start, end = map(pd.Timestamp, period_bounds(config, period, window=window))
    if window is None:
        raise ValueError('feature window must be explicit')
    if set(feature_frames) != set(config.symbols):
        raise ValueError('feature symbol mismatch')
    grid = pd.date_range(start, end, freq='4h', inclusive='left')
    required = {'symbol', 'decision_time', 'feature_available_time', 'feature_valid'}
    output = {}
    for symbol, frame in feature_frames.items():
        if not required <= set(frame) or not (frame.symbol == symbol).all():
            raise ValueError('missing feature columns or mismatched symbol')
        times = pd.DatetimeIndex(frame.decision_time)
        if times.tz is None or times.hasnans or any(t.utcoffset().total_seconds() != 0 for t in times):
            raise ValueError('feature decision times must be UTC')
        if not times.is_unique or not times.is_monotonic_increasing or not times.equals(times.floor('h')):
            raise ValueError('duplicate, unordered or non-hourly feature decisions')
        selected = frame.loc[(frame.decision_time >= start) & (frame.decision_time < end)].copy().reset_index(drop=True)
        decisions = selected.loc[selected.decision_time.dt.hour % 4 == 0, 'decision_time']
        if not pd.DatetimeIndex(decisions).equals(grid):
            raise ValueError('incomplete four-hour feature decision grid')
        if not pd.api.types.is_bool_dtype(selected.feature_valid.dtype) or selected.feature_valid.isna().any():
            raise ValueError('invalid feature readiness flags')
        ready = selected.loc[selected.feature_valid]
        available = pd.DatetimeIndex(ready.feature_available_time)
        if len(available) and (available.tz is None or available.hasnans or
                              any(t.utcoffset().total_seconds() != 0 for t in available) or
                              (available > pd.DatetimeIndex(ready.decision_time)).any()):
            raise ValueError('valid feature exposes future or unavailable history')
        output[symbol] = selected
    return output

"""九个固定特征只消费已可获得的小时观察，按缺口重新预热。"""

import numpy as np
import pandas as pd

HOUR = pd.Timedelta(1, unit='h')
BASE_FEATURE_NAMES = ['return_1h', 'return_4h', 'return_24h', 'return_72h',
                      'volatility_24h', 'range_fraction', 'quote_volume_change',
                      'ema24_distance', 'ema72_distance']
FUNDING_FEATURE_NAMES = ['funding_rate_latest', 'funding_rate_ma3', 'funding_rate_zscore']
ALL_FEATURE_NAMES = BASE_FEATURE_NAMES + FUNDING_FEATURE_NAMES
FEATURE_NAMES = BASE_FEATURE_NAMES


def build_features(frame, funding_df=None):
    required = {'symbol', 'open_time', 'close', 'high', 'low', 'quote_volume',
                'available_time', 'market_state', 'row_role', 'source_id'}
    if not required <= set(frame.columns) or frame.empty:
        raise ValueError('missing feature input fields')
    frame = frame.reset_index(drop=True)
    times = pd.DatetimeIndex(frame.open_time)
    if times.tz is None or times[0].utcoffset().total_seconds() != 0 or times[0] != times[0].floor('h'):
        raise ValueError('requires UTC hourly calendar')
    if not times.equals(pd.date_range(times[0], times[-1], freq='h')) or frame.symbol.nunique() != 1:
        raise ValueError('invalid feature calendar or symbols')
    if not frame.market_state.isin(['observed', 'no_trade', 'halt']).all():
        raise ValueError('unknown market state')
    decisions = frame.open_time + HOUR
    observed = (frame.market_state == 'observed') & (frame.row_role != 'boundary') & (frame.available_time == decisions)
    segments = (~observed).cumsum()
    counts = observed.groupby(segments).cumsum().astype('int64')
    output = pd.DataFrame(dict(symbol=frame.symbol, feature_open_time=frame.open_time,
                               decision_time=decisions, feature_available_time=frame.available_time,
                               source_id=frame.source_id, history_count=counts))
    for name in BASE_FEATURE_NAMES:
        output[name] = np.nan
    # Segmentation derives exclusively from the just-closed history. No current
    # execution candle's final market state is an input to these features.
    for _, part in frame.loc[observed].groupby(segments[observed], sort=False):
        close, high, low, volume = [pd.to_numeric(part[name], errors='coerce').astype(float)
                                    for name in ['close', 'high', 'low', 'quote_volume']]
        values = pd.DataFrame(index=part.index)
        with np.errstate(divide='ignore', invalid='ignore'):
            for horizon in [1, 4, 24, 72]:
                values[f'return_{horizon}h'] = close / close.shift(horizon) - 1
            values['volatility_24h'] = values['return_1h'].rolling(24, min_periods=24).std(ddof=1)
            values['range_fraction'] = (high - low) / close
            values['quote_volume_change'] = volume / volume.shift(1).rolling(24, min_periods=24).mean() - 1
            values['ema24_distance'] = close / close.ewm(span=24, adjust=False).mean() - 1
            values['ema72_distance'] = close / close.ewm(span=72, adjust=False).mean() - 1
        output.loc[part.index, BASE_FEATURE_NAMES] = values[BASE_FEATURE_NAMES]

    active_features = list(BASE_FEATURE_NAMES)
    if funding_df is not None:
        from cryptoquant.data.funding import align_funding_to_hourly_bars
        aligned = align_funding_to_hourly_bars(output, funding_df)
        for col in FUNDING_FEATURE_NAMES:
            output[col] = aligned[col].to_numpy()
        active_features = list(ALL_FEATURE_NAMES)

    finite = np.isfinite(output[active_features].to_numpy()).all(axis=1)
    output['feature_valid'] = observed & (counts >= 744) & finite
    output['invalid_reason'] = ''
    output.loc[observed & (counts < 744), 'invalid_reason'] = 'insufficient_history'
    output.loc[observed & (counts >= 744) & ~finite, 'invalid_reason'] = 'non_finite_feature'
    output.loc[~observed, 'invalid_reason'] = 'unavailable_close'
    output.loc[frame.market_state != 'observed', 'invalid_reason'] = frame.market_state
    output.loc[frame.row_role == 'boundary', 'invalid_reason'] = 'boundary'
    return output

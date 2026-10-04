"""离线训练标签独立于历史特征；不把答案送入交易决策。"""

import pandas as pd

from cryptoquant.data.calendar import can_execute
from cryptoquant.models.features import build_features, FEATURE_NAMES, HOUR
from cryptoquant.models.labels import GROSS_POLICY, label_values

METADATA = ['symbol', 'feature_open_time', 'decision_time', 'feature_available_time',
            'source_id', 'history_count']
SAMPLE_COLUMNS = METADATA + FEATURE_NAMES + ['label_start', 'label_end', 'label_return', 'label']
EXCLUDED_COLUMNS = ['symbol', 'feature_open_time', 'decision_time', 'label_end', 'reason']


def build_training_samples(frame, start, end, funding_df=None):
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    if any(t.tz is None or t.utcoffset().total_seconds() != 0 or t != t.floor('h') for t in [start, end]) or start >= end:
        raise ValueError('invalid sample period')
    features = build_features(frame, funding_df=funding_df)
    active_feature_names = [col for col in features.columns if col not in METADATA and col not in {'feature_valid', 'invalid_reason'}]
    sample_columns = METADATA + active_feature_names + ['label_start', 'label_end', 'label_return', 'label']
    quotes = {row['open_time']: row for row in frame.to_dict('records')}
    candidates = features[(features.decision_time >= start) & (features.decision_time < end) &
                          (features.decision_time.dt.hour % 4 == 0)]
    samples, excluded = [], []
    for row in candidates.to_dict('records'):
        entry = row['decision_time']
        exit_time = entry + 4 * HOUR
        reason = None
        if not row['feature_valid']:
            reason = 'feature_' + row['invalid_reason']
        elif exit_time >= end:
            reason = 'label_crosses_boundary'
        else:
            window = [quotes.get(entry + n * HOUR) for n in range(5)]
            if not all(quote is not None and can_execute(quote) for quote in window):
                reason = 'label_unavailable_window'
        if reason:
            excluded.append(dict(symbol=row['symbol'], feature_open_time=row['feature_open_time'],
                                 decision_time=entry, label_end=exit_time, reason=reason))
            continue
        values = label_values(quotes[entry]['open'], quotes[exit_time]['open'], GROSS_POLICY)
        sample = {name: row[name] for name in METADATA + active_feature_names}
        sample.update(label_start=entry, label_end=exit_time, label_return=values['label_return'],
                      label=values['label'])
        samples.append(sample)
    return pd.DataFrame(samples, columns=sample_columns), pd.DataFrame(excluded, columns=EXCLUDED_COLUMNS)

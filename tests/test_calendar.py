from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from cryptoquant.data.calendar import can_execute, label_window_is_observed, policy_info, valid_close
from cryptoquant.data.quality import audit, partition_data
from test_quality import rows
from types import SimpleNamespace

HALT = datetime(2023, 3, 24, 13, tzinfo=timezone.utc)
POLICY = 'halt_aware_v1'


def halted_rows(after=746):
    frame = rows(after + 3)
    shift = HALT - timedelta(hours=2) - frame.open_time.iloc[0].to_pydatetime()
    for column in ['open_time', 'close_time', 'available_time']:
        frame[column] += shift
    return frame[frame.open_time != HALT].reset_index(drop=True)


def checked(frame=None):
    frame = halted_rows() if frame is None else frame
    return audit(frame, frame.open_time.min(), frame.open_time.max() + timedelta(hours=1), HALT + timedelta(days=40), policy=POLICY)


@pytest.mark.parametrize('symbol,opened,closed', [
    ('BTCUSDT', '2021-12-24T04:00:00Z', '2021-12-24T04:59:54.362Z'),
    ('ETHUSDT', '2021-12-24T04:00:00Z', '2021-12-24T04:59:56.158Z'),
    ('BTCUSDT', '2023-03-24T12:00:00Z', '2023-03-24T12:39:41.646Z'),
    ('ETHUSDT', '2023-03-24T12:00:00Z', '2023-03-24T12:39:43.061Z'),
    ('SOLUSDT', '2023-03-24T12:00:00Z', '2023-03-24T12:39:46.948Z'),
])
def test_only_exact_verified_close_pairs_are_allowed(symbol, opened, closed):
    opened, closed = pd.Timestamp(opened), pd.Timestamp(closed)
    assert valid_close(symbol, opened, closed, POLICY)
    assert not valid_close(symbol, opened, closed, 'strict_v0')
    assert not valid_close(symbol, opened, closed + pd.Timedelta(1, unit='ms'), POLICY)
    assert not valid_close(symbol, opened + pd.Timedelta(1, unit='h'), closed, POLICY)


def test_policy_contains_hash_and_verified_evidence():
    policy, sha = policy_info(POLICY)
    assert policy['version'] == POLICY and len(sha) == 64
    assert len(policy['evidence']) == 6
    assert len(policy['early_closes']) == 5
    with pytest.raises(ValueError, match='policy'):
        policy_info('allow_all_gaps')


def test_v2_selects_daily_sources_and_does_not_accept_cross_hour_close():
    policy, sha = policy_info('halt_aware_v2')
    old, old_sha = policy_info('halt_aware_v1')
    assert sha != old_sha and policy['early_closes'] == old['early_closes']
    assert policy['source_preferences'][0]['symbol'] == 'SOLUSDT'
    assert policy['source_preferences'][0]['month'] == '2021-12'
    assert not valid_close('SOLUSDT', pd.Timestamp('2021-12-24T04:00:00Z'), pd.Timestamp('2021-12-24T05:00:00.475Z'), 'halt_aware_v2')


def v2_rows():
    frame = halted_rows()
    before = rows(3)
    shift = HALT - timedelta(hours=5) - before.open_time.iloc[0].to_pydatetime()
    for column in ['open_time', 'close_time', 'available_time']:
        before[column] += shift
    frame = pd.concat([before, frame], ignore_index=True)
    mask = frame.open_time == HALT - timedelta(hours=1)
    frame.loc[mask, ['open', 'high', 'low', 'close']] = '11'
    frame.loc[mask, ['volume', 'quote_volume']] = '0'
    frame.loc[mask, 'trade_count'] = 0
    frame.loc[mask, 'close_time'] = pd.Timestamp('2023-03-24T12:39:41.646Z')
    return frame


def test_v2_zero_trade_record_is_preserved_but_not_executable_or_label_price():
    frame = v2_rows()
    clean, report = audit(frame, frame.open_time.min(), frame.open_time.max() + timedelta(hours=1), HALT + timedelta(days=40), policy='halt_aware_v2')
    noon = clean[clean.open_time == HALT - timedelta(hours=1)].iloc[0]
    assert noon.market_state == 'no_trade' and noon['open'] == '11'
    assert noon.history_count == 0 and not noon.history_ready and noon.is_nonstandard_close
    assert not can_execute(noon)
    assert not label_window_is_observed(clean, HALT - timedelta(hours=5))
    control = clean.copy()
    control.loc[control.open_time == noon.open_time, 'market_state'] = 'observed'
    assert label_window_is_observed(control, HALT - timedelta(hours=5))
    assert report['archive_rows'] == len(frame)
    assert report['observed_rows'] == len(frame) - 1 and report['no_trade_rows'] == 1
    bad = frame.copy()
    bad.loc[bad.open_time == noon.open_time, 'trade_count'] = 1
    with pytest.raises(ValueError, match='no.trade'):
        audit(bad, bad.open_time.min(), bad.open_time.max() + timedelta(hours=1), HALT + timedelta(days=40), policy='halt_aware_v2')


def test_known_halt_is_calendar_only_and_readiness_resets():
    clean, report = checked()
    halt = clean[clean.open_time == HALT].iloc[0]
    assert halt.market_state == 'halt' and halt.history_count == 0 and not halt.history_ready
    for column in ['open', 'high', 'low', 'close', 'volume', 'quote_volume', 'trade_count', 'source_id', 'close_time', 'available_time']:
        assert pd.isna(halt[column]), column
    resumed = clean[clean.open_time > HALT]
    assert resumed.iloc[0].history_count == 1
    assert not resumed.iloc[742].history_ready
    assert resumed.iloc[743].history_ready
    assert resumed.iloc[0].segment_id != clean.iloc[0].segment_id
    assert report['rows'] == len(clean) and report['observed_rows'] == len(clean) - 1
    assert report['missing_hours'] == report['known_halt_hours'] == 1
    assert report['unexplained_missing_hours'] == 0


def test_unknown_gap_still_fails_and_halt_with_actual_row_fails():
    frame = halted_rows()
    with pytest.raises(ValueError, match='grid'):
        checked(frame.drop(index=5))
    actual_halt = frame.iloc[[0]].copy()
    for column in ['open_time', 'close_time', 'available_time']:
        actual_halt[column] += timedelta(hours=2)
    with pytest.raises(ValueError, match='halt'):
        checked(pd.concat([frame, actual_halt]))


def test_known_early_close_is_reported_with_original_source():
    frame = halted_rows()
    frame.loc[frame.open_time == HALT - timedelta(hours=1), 'close_time'] = pd.Timestamp('2023-03-24T12:39:41.646Z')
    clean, report = checked(frame)
    assert clean.iloc[1].close_time == pd.Timestamp('2023-03-24T12:39:41.646Z')
    assert clean.iloc[1].available_time == HALT
    assert len(report['nonstandard_closes']) == 1
    assert report['nonstandard_close_count'] == 1
    assert clean.iloc[1].is_nonstandard_close and not clean.iloc[0].is_nonstandard_close
    assert pd.isna(clean[clean.open_time == HALT].iloc[0].is_nonstandard_close)
    assert report['nonstandard_closes'][0]['source_id'] == 'b'
    frame.loc[1, 'close_time'] += pd.Timedelta(1, unit='ms')
    with pytest.raises(ValueError, match='close'):
        checked(frame)


def test_labels_use_calendar_hours_and_no_halt_execution():
    clean, _ = checked()
    assert not label_window_is_observed(clean, HALT - timedelta(hours=1))
    assert label_window_is_observed(clean, HALT + timedelta(hours=1))
    assert not label_window_is_observed(clean, clean.open_time.max() - timedelta(hours=2))
    assert not label_window_is_observed(clean.drop(index=6), HALT + timedelta(hours=1))
    assert not label_window_is_observed(pd.concat([clean, clean.iloc[[4]]]), HALT + timedelta(hours=1))
    assert not can_execute(clean[clean.open_time == HALT].iloc[0])
    assert can_execute(clean[clean.open_time == HALT + timedelta(hours=1)].iloc[0])


def test_halt_boundary_and_parquet_preserve_nulls_and_state(tmp_path):
    clean, _ = checked()
    config = SimpleNamespace(**{period + '_start': HALT - timedelta(hours=1) for period in ['development', 'validation', 'test']}, **{period + '_end': HALT for period in ['development', 'validation', 'test']})
    part = partition_data(clean, config)['development']
    boundary = part.iloc[-1]
    assert boundary.row_role == 'boundary' and boundary.market_state == 'halt'
    assert not can_execute(boundary)
    assert pd.isna(boundary.history_ready) and pd.isna(boundary.history_count)
    path = tmp_path / 'calendar.parquet'
    clean.to_parquet(path, index=False)
    loaded = pd.read_parquet(path)
    assert pd.isna(loaded[loaded.open_time == HALT].iloc[0]['open'])
    assert str(loaded.open_time.dt.tz) == 'UTC'

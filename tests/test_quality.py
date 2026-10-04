from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pandas as pd
import pytest

from cryptoquant.data.quality import audit, partition_data

START = datetime(2025, 1, 1, tzinfo=timezone.utc)


def rows(count=4):
    times = pd.date_range(START, periods=count, freq="h")
    return pd.DataFrame({"symbol": "BTCUSDT", "open_time": times, "close_time": times + pd.Timedelta(1, unit="h") - pd.Timedelta(1, unit="ms"), "available_time": times + pd.Timedelta(1, unit="h"), "open": "10", "high": "12", "low": "9", "close": "11", "volume": "2", "quote_volume": "21", "trade_count": 3, "source_id": "b"})


def test_exact_duplicates_merge_with_stable_source_and_report():
    frame = rows()
    duplicate = frame.iloc[[0]].copy()
    duplicate["source_id"] = "a"
    cleaned, report = audit(pd.concat([frame, duplicate]), START, START + timedelta(hours=4), START + timedelta(days=2))
    assert len(cleaned) == 4 and report["duplicates_removed"] == 1
    assert cleaned.iloc[0]["source_id"] == "a"


def test_conflicting_duplicate_is_never_silently_selected():
    frame = rows()
    duplicate = frame.iloc[[0]].copy()
    duplicate["close"] = "10"
    with pytest.raises(ValueError, match="conflict"):
        audit(pd.concat([frame, duplicate]), START, START + timedelta(hours=4), START + timedelta(days=2))


@pytest.mark.parametrize("problem", ["gap", "bad_ohlc", "negative_volume", "unclosed", "wrong_availability", "cross_range"])
def test_quality_errors_stop_processing(problem):
    frame = rows()
    now = START + timedelta(days=2)
    if problem == "gap":
        frame = frame.drop(index=2)
    elif problem == "bad_ohlc":
        frame.loc[1, "high"] = "8"
    elif problem == "negative_volume":
        frame.loc[1, "volume"] = "-1"
    elif problem == "unclosed":
        now = START + timedelta(hours=2)
    elif problem == "wrong_availability":
        frame.loc[1, "available_time"] = START
    else:
        frame.loc[0, "open_time"] = START - timedelta(hours=1)
    with pytest.raises(ValueError):
        audit(frame, START, START + timedelta(hours=4), now)


def test_disordered_input_is_reported_and_sorted():
    cleaned, report = audit(rows().iloc[::-1], START, START + timedelta(hours=4), START + timedelta(days=2))
    assert cleaned.open_time.is_monotonic_increasing
    assert report["input_was_ordered"] is False


def test_partition_boundary_contains_only_open_and_warmup_is_marked():
    config = SimpleNamespace(development_start=START + timedelta(hours=1), development_end=START + timedelta(hours=2), validation_start=START + timedelta(hours=2), validation_end=START + timedelta(hours=3), test_start=START + timedelta(hours=3), test_end=START + timedelta(hours=4))
    parts = partition_data(rows(5), config)
    development = parts["development"]
    assert development.row_role.tolist() == ["warmup", "evaluation", "boundary"]
    boundary = development.iloc[-1]
    assert boundary["open"] == "10" and pd.isna(boundary["close"]) and pd.isna(boundary["available_time"])


def test_parquet_preserves_decimal_strings_and_utc(tmp_path):
    path = tmp_path / "data.parquet"
    frame = rows()
    frame.to_parquet(path, index=False)
    loaded = pd.read_parquet(path)
    assert loaded.iloc[0]["open"] == "10"
    assert str(loaded.open_time.dt.tz) == "UTC"

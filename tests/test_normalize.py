from datetime import datetime, timezone
from zipfile import ZipFile

import pytest

from cryptoquant.data.normalize import parse_archive_timestamp, read_archive

ROW = "1735689600000,10,12,9,11,2,1735693199999,21,3,1,10,0"


def make_zip(tmp_path, text=ROW, member="BTCUSDT-1h-2025-01-01.csv"):
    path = tmp_path / "BTCUSDT-1h-2025-01-01.zip"
    with ZipFile(path, "w") as zipped:
        zipped.writestr(member, text)
    return path


def test_ms_and_us_resolve_to_same_utc_boundary():
    expected = datetime(2025, 1, 1, tzinfo=timezone.utc)
    assert parse_archive_timestamp("1735689600000") == expected
    assert parse_archive_timestamp("1735689600000000") == expected


@pytest.mark.parametrize("value", ["1735689600", "1.7356896e12", "-1735689600000", "abc"])
def test_unsupported_timestamp_is_rejected(value):
    with pytest.raises(ValueError):
        parse_archive_timestamp(value)


def test_values_remain_decimal_text_and_availability_is_next_hour(tmp_path):
    frame = read_archive(make_zip(tmp_path), "BTCUSDT", "source", "BTCUSDT-1h-2025-01-01.zip")
    assert frame.iloc[0]["open"] == "10"
    assert frame.iloc[0]["available_time"] == datetime(2025, 1, 1, 1, tzinfo=timezone.utc)
    assert frame.iloc[0]["trade_count"] == 3


def test_recognized_header_is_supported(tmp_path):
    header = "open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n"
    assert len(read_archive(make_zip(tmp_path, header + ROW), "BTCUSDT", "s", "BTCUSDT-1h-2025-01-01.zip")) == 1


@pytest.mark.parametrize("text", [ROW.replace(",10,12", ",nan,12"), ROW.replace(",2,173", ",-2,173"), ROW.replace(",3,1,", ",3.2,1,"), ROW + ",extra", ROW.replace("1735693199999", "1735689600000"), ROW.replace("1735689600000", "1735776000000")])
def test_bad_fields_close_time_and_archive_dates_fail(tmp_path, text):
    with pytest.raises(ValueError):
        read_archive(make_zip(tmp_path, text), "BTCUSDT", "s", "BTCUSDT-1h-2025-01-01.zip")


def test_zip_path_is_never_extracted(tmp_path):
    with pytest.raises(ValueError):
        read_archive(make_zip(tmp_path, member="../BTCUSDT-1h-2025-01-01.csv"), "BTCUSDT", "s", "BTCUSDT-1h-2025-01-01.zip")


def test_verified_early_close_is_preserved_only_under_new_policy(tmp_path):
    filename = 'BTCUSDT-1h-2023-03-24.zip'
    path = tmp_path / filename
    raw = ROW.replace('1735689600000', '1679659200000').replace('1735693199999', '1679661581646')
    with ZipFile(path, 'w') as zipped:
        zipped.writestr(filename[:-4] + '.csv', raw)
    with pytest.raises(ValueError, match='close'):
        read_archive(path, 'BTCUSDT', 'verified-source', filename)
    frame = read_archive(path, 'BTCUSDT', 'verified-source', filename, policy='halt_aware_v1')
    assert frame.iloc[0].close_time == datetime(2023, 3, 24, 12, 39, 41, 646000, tzinfo=timezone.utc)
    assert frame.iloc[0].available_time == datetime(2023, 3, 24, 13, tzinfo=timezone.utc)

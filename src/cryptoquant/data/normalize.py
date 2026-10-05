"""保留十进制原文，精确区分毫秒和微秒，不提前暴露整根行情。"""

import csv
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from io import TextIOWrapper
import re
from zipfile import ZipFile

from cryptoquant.data.calendar import valid_close

EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
HOUR = timedelta(hours=1)
FIELDS = ["symbol", "open_time", "close_time", "available_time", "open", "high", "low", "close", "volume", "quote_volume", "trade_count", "source_id"]
HEADERS = {
    ("open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "count", "taker_buy_volume", "taker_buy_quote_volume", "ignore"),
    ("open_time", "open", "high", "low", "close", "volume", "close_time", "quote_asset_volume", "number_of_trades", "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"),
}


def parse_archive_timestamp(value):
    if not re.fullmatch(r"(?:[0-9]{13}|[0-9]{16})", value):
        raise ValueError("timestamp must be integer milliseconds or microseconds")
    micros = int(value) * 1000 if len(value) == 13 else int(value)
    return EPOCH + timedelta(microseconds=micros)


def numeric_text(value, positive=False):
    if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value) or (positive and Decimal(value) <= 0):
        raise ValueError("invalid decimal field")
    return value


def read_archive(path, symbol, source_id, filename, policy="strict_v0"):
    import pandas as pd

    match = re.fullmatch(re.escape(symbol) + r"-1h-([0-9]{4}-[0-9]{2}(?:-[0-9]{2})?)\.zip", filename)
    if not match:
        raise ValueError("invalid archive filename")
    stamp = match[1]
    start = datetime.strptime(stamp, "%Y-%m-%d" if len(stamp) == 10 else "%Y-%m").replace(tzinfo=timezone.utc)
    end = start + timedelta(days=1) if len(stamp) == 10 else start.replace(year=start.year + (start.month == 12), month=start.month % 12 + 1, day=1)
    rows = []
    previous = None
    with ZipFile(path) as zipped:
        member = filename[:-4] + ".csv"
        if zipped.namelist() != [member] or zipped.getinfo(member).file_size > 50 * 1024 * 1024:
            raise ValueError("unexpected ZIP member or expanded size")
        with zipped.open(member) as stream:
            reader = csv.reader(TextIOWrapper(stream, encoding="utf-8-sig", newline=""))
            for index, raw in enumerate(reader):
                values = [item.strip() for item in raw]
                if index == 0 and tuple(values) in HEADERS:
                    continue
                if len(values) != 12:
                    raise ValueError(f"invalid column count: {filename}:{index + 1}")
                opened, closed = parse_archive_timestamp(values[0]), parse_archive_timestamp(values[6])
                available = opened + HOUR
                if not start <= opened < end or any([opened.minute, opened.second, opened.microsecond]):
                    raise ValueError("hour outside archive date or off grid")
                if not valid_close(symbol, opened, closed, policy):
                    raise ValueError("invalid hourly close timestamp")
                if previous is not None and opened < previous:
                    raise ValueError("out-of-order rows inside archive")
                previous = opened
                for column in [1, 2, 3, 4]:
                    numeric_text(values[column], positive=True)
                for column in [5, 7, 9, 10, 11]:
                    numeric_text(values[column])
                if not re.fullmatch(r"[0-9]+", values[8]):
                    raise ValueError("trade count must be nonnegative integer")
                rows.append([symbol, opened, closed, available, *values[1:6], values[7], int(values[8]), source_id])
    if not rows:
        raise ValueError("empty archive")
    return pd.DataFrame(rows, columns=FIELDS)

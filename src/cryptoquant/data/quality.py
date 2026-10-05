"""数据质量检查失败即停止；不造价、不填缺口。"""

from datetime import timedelta
from decimal import Decimal, InvalidOperation

import pandas as pd

from cryptoquant.data.calendar import add_calendar, known_halts, known_no_trade_bars, valid_close, STANDARD_DELTAS, HOUR

PRICE_COLUMNS = ["open", "high", "low", "close"]
VOLUME_COLUMNS = ["volume", "quote_volume"]


def audit(frame, start, end, now, policy="strict_v0"):
    if frame.empty or frame.symbol.nunique() != 1:
        raise ValueError("empty or mixed-symbol dataset")
    ordered = bool(frame.open_time.is_monotonic_increasing)
    data = frame.copy()
    for column in ["open_time", "close_time", "available_time"]:
        if not isinstance(data[column].dtype, pd.DatetimeTZDtype) or str(data[column].dt.tz) != "UTC" or data[column].isna().any():
            raise ValueError("timestamps must be non-null UTC")
    for column in PRICE_COLUMNS + VOLUME_COLUMNS:
        try:
            numbers = data[column].map(Decimal)
            if not numbers.map(lambda x: x.is_finite() and (x > 0 if column in PRICE_COLUMNS else x >= 0)).all():
                raise ValueError("invalid price or volume")
        except (TypeError, InvalidOperation) as exc:
            raise ValueError("invalid decimal data") from exc
        data[column] = numbers
    if not ((data.low <= data.open) & (data.low <= data.close) & (data.high >= data.open) & (data.high >= data.close) & (data.high >= data.low)).all():
        raise ValueError("invalid OHLC relationship")
    if not ((data.trade_count >= 0) & (data.trade_count % 1 == 0)).all():
        raise ValueError("invalid trade count")
    if not (data.available_time == data.open_time + pd.Timedelta(1, unit="h")).all():
        raise ValueError("invalid availability timestamp")
    if not all(valid_close(row.symbol, row.open_time, row.close_time, policy) for row in data.itertuples()):
        raise ValueError("invalid close timestamp")
    if not ((data.open_time >= start) & (data.open_time < end)).all() or not (data.available_time <= now).all():
        raise ValueError("out-of-range or unclosed bar")
    comparison = [x for x in data.columns if x != "source_id"]
    duplicate_mask = data.duplicated("open_time", keep=False)
    for _, group in data.loc[duplicate_mask].groupby("open_time", sort=False):
        if len(group[comparison].drop_duplicates()) != 1:
            raise ValueError("conflicting duplicate records")
    # Lexicographic source_id is an explicit stable priority, independent of input order.
    data = data.sort_values(["open_time", "source_id"], kind="stable").drop_duplicates("open_time", keep="first")
    expected = pd.date_range(start, end, freq="h", inclusive="left")
    actual = pd.DatetimeIndex(data.open_time)
    missing = expected.difference(actual)
    extras = actual.difference(expected)
    halted = known_halts(str(frame.symbol.iloc[0]), start, end, policy)
    if len(actual.intersection(halted)):
        raise ValueError("actual record contradicts known halt")
    if len(extras) or not missing.equals(halted):
        raise ValueError(f"hour grid mismatch: missing={len(missing)}, extra={len(extras)}, first_missing={list(missing[:5])}")
    indexed = data.set_index("open_time")
    for timestamp in known_no_trade_bars(str(frame.symbol.iloc[0]), start, end, policy):
        row = indexed.loc[timestamp]
        if row.trade_count != 0 or row.volume != 0 or row.quote_volume != 0 or len({row[column] for column in PRICE_COLUMNS}) != 1:
            raise ValueError("record contradicts known no-trade bar")
        previous = timestamp - HOUR
        if previous in indexed.index and row.open != indexed.loc[previous, "close"]:
            raise ValueError("no-trade bar does not match previous close")
    # Retain original decimal spellings, not float conversions used by indicators later.
    selected = frame.set_index(["open_time", "source_id"])
    keys = pd.MultiIndex.from_frame(data[["open_time", "source_id"]])
    selected = selected.loc[~selected.index.duplicated(keep="first")]
    cleaned = selected.loc[keys].reset_index()
    cleaned = cleaned[frame.columns].reset_index(drop=True)
    observed_rows = len(cleaned)
    nonstandard = cleaned[~(cleaned.available_time - cleaned.close_time).isin(STANDARD_DELTAS)]
    details = [{"open_time": row.open_time.isoformat(), "close_time": row.close_time.isoformat(), "source_id": row.source_id} for row in nonstandard.itertuples()]
    cleaned = add_calendar(cleaned, expected, policy)
    report = {"symbol": str(frame.symbol.iloc[0]), "status": "passed", "input_rows": len(frame), "rows": len(cleaned), "archive_rows": observed_rows, "observed_rows": int((cleaned.market_state == "observed").sum()), "no_trade_rows": int((cleaned.market_state == "no_trade").sum()), "expected_rows": len(expected), "duplicates_removed": len(frame) - observed_rows, "input_was_ordered": ordered, "start_utc": start.isoformat(), "end_exclusive_utc": end.isoformat(), "missing_hours": len(missing), "known_halt_hours": len(halted), "unexplained_missing_hours": 0, "nonstandard_close_count": len(details), "nonstandard_closes": details, "conflicting_duplicates": 0, "unclosed_bars": 0}
    return cleaned, report


def partition_data(frame, config):
    result = {}
    for period in ["development", "validation", "test"]:
        start, end = getattr(config, period + "_start"), getattr(config, period + "_end")
        part = frame[(frame.open_time >= start - timedelta(hours=744)) & (frame.open_time <= end)].copy()
        if not (part.open_time == end).any():
            raise ValueError(f"missing terminal open: {period}")
        part["row_role"] = "evaluation"
        part.loc[part.open_time < start, "row_role"] = "warmup"
        boundary = part.open_time == end
        part.loc[boundary, "row_role"] = "boundary"
        # Physically remove forbidden future fields instead of relying only on a flag.
        for column in part.columns:
            if column not in {"symbol", "open_time", "open", "source_id", "row_role", "market_state"}:
                part.loc[boundary, column] = pd.NaT if column in {"close_time", "available_time"} else None
        result[period] = part.reset_index(drop=True)
    return result

"""有限数据例外与日历窗口；没有行情时不产生价格或成交。"""

from functools import lru_cache
import hashlib
from importlib.resources import files
import json

import pandas as pd

HOUR = pd.Timedelta(1, unit="h")
STANDARD_DELTAS = {pd.Timedelta(1, unit="ms"), pd.Timedelta(1, unit="us")}


def policy_info(policy):
    if policy == "strict_v0":
        raw = b'{"version":"strict_v0","warmup_hours":744,"halts":[],"early_closes":[],"evidence":[]}'
    elif policy in {"halt_aware_v1", "halt_aware_v2"}:
        name = "market_calendar.json" if policy == "halt_aware_v1" else "market_calendar_v2.json"
        raw = files("cryptoquant.data").joinpath(name).read_bytes()
    else:
        raise ValueError("unsupported data policy")
    data = json.loads(raw)
    if data["version"] != policy:
        raise ValueError("data policy version mismatch")
    return data, hashlib.sha256(raw).hexdigest()


@lru_cache(maxsize=2)
def _exceptions(policy):
    data, _ = policy_info(policy)
    early = {(x["symbol"], pd.Timestamp(x["open_time"]), pd.Timestamp(x["close_time"])) for x in data["early_closes"]}
    halted = {(x["symbol"], pd.Timestamp(x["open_time"])) for x in data["halts"]}
    return early, halted


def valid_close(symbol, opened, closed, policy="strict_v0"):
    early, _ = _exceptions(policy)
    return opened < closed < opened + HOUR and (opened + HOUR - closed in STANDARD_DELTAS or (symbol, opened, closed) in early)


def known_halts(symbol, start, end, policy):
    _, halted = _exceptions(policy)
    return pd.DatetimeIndex(sorted(t for s, t in halted if s == symbol and start <= t < end), tz="UTC")


def known_no_trade_bars(symbol, start, end, policy):
    items = policy_info(policy)[0].get("no_trade_bars", [])
    return pd.DatetimeIndex(sorted(pd.Timestamp(x["open_time"]) for x in items if x["symbol"] == symbol and start <= pd.Timestamp(x["open_time"]) < end), tz="UTC")


def add_calendar(frame, expected, policy):
    """仅在 audit 已证明 missing 与白名单相等后调用。"""
    observed = pd.DatetimeIndex(frame.open_time)
    data = frame.set_index("open_time").reindex(expected).rename_axis("open_time").reset_index()
    missing = ~data.open_time.isin(observed)
    data["symbol"] = str(frame.symbol.iloc[0])
    data["market_state"] = "observed"
    data.loc[missing, "market_state"] = "halt"
    no_trade = known_no_trade_bars(str(frame.symbol.iloc[0]), expected[0], expected[-1] + HOUR, policy)
    data.loc[data.open_time.isin(no_trade), "market_state"] = "no_trade"
    data["is_nonstandard_close"] = pd.Series(pd.NA, index=data.index, dtype="boolean")
    delta = data.available_time - data.close_time
    data.loc[~missing, "is_nonstandard_close"] = ~delta[~missing].isin(STANDARD_DELTAS)
    unavailable = data.market_state != "observed"
    segments = unavailable.cumsum()
    data["segment_id"] = segments.astype("Int64")
    data["history_count"] = (~unavailable).groupby(segments).cumsum().astype("Int64")
    data["history_ready"] = (data.history_count >= policy_info(policy)[0]["warmup_hours"]).astype("boolean")
    return data


def can_execute(row):
    return row.get("market_state") == "observed" and pd.notna(row.get("open"))


def label_window_is_observed(frame, entry_time, horizon=4):
    """标签专用：按绝对日历检查入口、途中和出口，不能作为实时特征。"""
    entry = pd.Timestamp(entry_time)
    if entry.tz is None or entry.utcoffset().total_seconds() != 0 or entry != entry.floor("h"):
        return False
    if type(horizon) is not int or horizon < 1:
        raise ValueError("horizon must be a positive number of hours")
    expected = pd.date_range(entry, periods=horizon + 1, freq="h")
    window = frame[frame.open_time.isin(expected)].sort_values("open_time")
    return pd.DatetimeIndex(window.open_time).equals(expected) and all(can_execute(row) for _, row in window.iterrows())

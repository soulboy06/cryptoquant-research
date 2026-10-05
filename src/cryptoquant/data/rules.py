"""市价订单规则快照解析；仅用于粗粒度历史模拟。"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR
from math import lcm

from cryptoquant.config import decimal_text


@dataclass(frozen=True)
class MarketRules:
    symbol: str
    step_size: Decimal
    min_quantity: Decimal
    max_quantity: Decimal | None
    min_notional: Decimal
    max_notional: Decimal | None
    average_price_minutes: tuple[int, ...]
    max_position: Decimal | None = None


def nonnegative(value):
    result = decimal_text(value)
    if result < 0:
        raise ValueError("negative rule value")
    return result


def flag(item, name):
    if type(item.get(name)) is not bool:
        raise ValueError(f"missing or invalid market flag: {name}")
    return item[name]


def parse_market_rules(symbol_info, minimum_notional=Decimal("10")):
    if symbol_info.get("status") != "TRADING" or symbol_info.get("isSpotTradingAllowed") is not True:
        raise ValueError("symbol not available for spot trading")
    minimum_notional = nonnegative(str(minimum_notional))
    steps, minimums, maximums = [], [], []
    low_notionals, high_notionals, averages = [minimum_notional], [], []
    max_position = None
    seen = set()
    # These filters apply to priced, outstanding, iceberg, algo or amend orders.
    # This simulator submits immediate MARKET fills, never those order types.
    irrelevant = {"PRICE_FILTER", "PERCENT_PRICE", "PERCENT_PRICE_BY_SIDE", "ICEBERG_PARTS", "MAX_NUM_ORDERS", "MAX_NUM_ALGO_ORDERS", "MAX_NUM_ICEBERG_ORDERS", "TRAILING_DELTA", "MAX_NUM_ORDER_AMENDS", "MAX_NUM_ORDER_LISTS"}
    try:
        for item in symbol_info["filters"]:
            kind = item["filterType"]
            if kind in seen:
                raise ValueError("duplicate filter")
            seen.add(kind)
            if kind in {"LOT_SIZE", "MARKET_LOT_SIZE"}:
                minimums.append(nonnegative(item["minQty"]))
                maximum = nonnegative(item["maxQty"])
                step = nonnegative(item["stepSize"])
                if maximum:
                    maximums.append(maximum)
                if step:
                    steps.append(step)
            elif kind in {"MIN_NOTIONAL", "NOTIONAL"}:
                average = item["avgPriceMins"]
                if type(average) is not int or average < 0:
                    raise ValueError("invalid average price minutes")
                averages.append(average)
                if flag(item, "applyToMarket" if kind == "MIN_NOTIONAL" else "applyMinToMarket"):
                    low_notionals.append(nonnegative(item["minNotional"]))
                if kind == "NOTIONAL" and flag(item, "applyMaxToMarket"):
                    value = nonnegative(item["maxNotional"])
                    if value:
                        high_notionals.append(value)
            elif kind == "MAX_POSITION":
                max_position = nonnegative(item["maxPosition"])
            elif kind not in irrelevant:
                raise ValueError(f"unsupported market-affecting filter: {kind}")
    except (KeyError, TypeError) as exc:
        raise ValueError("incomplete rule snapshot") from exc
    if "LOT_SIZE" not in seen or not steps:
        raise ValueError("missing quantity grid")
    places = max(max(0, -step.as_tuple().exponent) for step in steps)
    scale = Decimal(10) ** places
    step_size = Decimal(lcm(*(int(step * scale) for step in steps))) / scale
    min_quantity, max_quantity = max(minimums), min(maximums) if maximums else None
    min_notional, max_notional = max(low_notionals), min(high_notionals) if high_notionals else None
    if max_quantity is not None and (min_quantity > max_quantity or (max_quantity / step_size).to_integral_value(rounding=ROUND_FLOOR) * step_size < min_quantity):
        raise ValueError("inconsistent quantity bounds")
    if max_notional is not None and min_notional > max_notional:
        raise ValueError("inconsistent notional bounds")
    return MarketRules(symbol_info["symbol"], step_size, min_quantity, max_quantity, min_notional, max_notional, tuple(averages), max_position)


def round_market_quantity(qty, rules):
    if not isinstance(qty, Decimal) or not qty.is_finite() or qty < 0:
        raise ValueError("quantity must be nonnegative Decimal")
    return (qty / rules.step_size).to_integral_value(rounding=ROUND_FLOOR) * rules.step_size

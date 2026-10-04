"""集中校验研究配置；金额坚持使用十进制字符串。"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import hashlib
import tomllib


def decimal_text(value):
    if not isinstance(value, str):
        raise ValueError("amounts must be decimal strings")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("invalid decimal") from exc
    if not result.is_finite():
        raise ValueError("non-finite decimal")
    return result


def utc_hour(value):
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid UTC time") from exc
    if result.utcoffset() != timedelta(0) or any([result.minute, result.second, result.microsecond]):
        raise ValueError("time must be an exact UTC hour")
    return result.astimezone(timezone.utc)


@dataclass(frozen=True)
class Cost:
    fee: Decimal
    adverse_price: Decimal


@dataclass(frozen=True)
class Config:
    symbols: tuple[str, ...]
    download_start: datetime
    download_end: datetime
    development_start: datetime
    development_end: datetime
    validation_start: datetime
    validation_end: datetime
    test_start: datetime
    test_end: datetime
    initial_cash: Decimal
    equity_floor: Decimal
    weight_per_symbol: Decimal
    stop_loss: Decimal
    cooldown_hours: int
    minimum_order_notional: Decimal
    costs: dict[str, Cost]
    config_hash: str
    data_policy: str = "strict_v0"
    feature_policy: str = "kline_only"
    model_family: str = "logistic_regression"

    @property
    def expected_hours(self):
        return int((self.download_end - self.download_start).total_seconds() // 3600)


def load_config(path):
    raw = Path(path).read_bytes()
    values = tomllib.loads(raw.decode("utf-8-sig"))
    if values.pop("mode", None) != "simulation" or values.pop("interval", None) != "1h":
        raise ValueError("only simulation with 1h bars is supported")
    symbols = values.pop("symbols", [])
    data_policy = values.pop("data_policy", "strict_v0")
    if data_policy not in {"strict_v0", "halt_aware_v1", "halt_aware_v2"}:
        raise ValueError("unsupported data policy")
    feature_policy = values.pop("feature_policy", "kline_only")
    if feature_policy not in {"kline_only", "kline_and_funding"}:
        raise ValueError("unsupported feature policy")
    model_family = values.pop("model_family", "logistic_regression")
    if model_family not in {"logistic_regression", "lightgbm"}:
        raise ValueError("unsupported model family")
    if not symbols or len(symbols) != len(set(symbols)) or not set(symbols) <= {"BTCUSDT", "ETHUSDT", "SOLUSDT"}:
        raise ValueError("unsupported or duplicate symbols")
    time_keys = ["download_start", "download_end", "development_start", "development_end", "validation_start", "validation_end", "test_start", "test_end"]
    try:
        times = {key: utc_hour(values.pop(key)) for key in time_keys}
        amounts = {key: decimal_text(values.pop(key)) for key in ["initial_cash", "equity_floor", "weight_per_symbol", "stop_loss", "minimum_order_notional"]}
        cooldown = values.pop("cooldown_hours")
        raw_costs = values.pop("costs")
        costs = {name: Cost(decimal_text(item["fee"]), decimal_text(item["adverse_price"])) for name, item in raw_costs.items()}
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("missing or invalid configuration field") from exc
    if values or set(costs) != {"base", "higher_execution", "strict"} or any(set(x) != {"fee", "adverse_price"} for x in raw_costs.values()):
        raise ValueError("unknown configuration field or missing cost scenario")
    ordered = [times[k] for k in ["download_start", "development_start", "development_end", "validation_end", "test_start", "test_end", "download_end"]]
    if any(a >= b for a, b in zip(ordered, ordered[1:])) or times["development_end"] != times["validation_start"]:
        raise ValueError("invalid period ordering")
    if times["development_start"] - times["download_start"] < timedelta(hours=744) or times["test_start"] - times["validation_end"] != timedelta(hours=4):
        raise ValueError("requires 744-hour warmup and four-hour freeze window")
    if not (0 <= amounts["equity_floor"] < amounts["initial_cash"]) or amounts["minimum_order_notional"] <= 0:
        raise ValueError("invalid capital or notional")
    if not (0 < amounts["weight_per_symbol"] * len(symbols) <= 1) or not (0 < amounts["stop_loss"] < 1):
        raise ValueError("invalid exposure or stop loss")
    if type(cooldown) is not int or cooldown < 0 or any(not (0 <= x.fee < 1 and 0 <= x.adverse_price < 1) for x in costs.values()):
        raise ValueError("invalid cooldown or costs")
    return Config(tuple(symbols), **times, **amounts, cooldown_hours=cooldown, costs=costs, config_hash=hashlib.sha256(raw).hexdigest(), data_policy=data_policy, feature_policy=feature_policy, model_family=model_family)

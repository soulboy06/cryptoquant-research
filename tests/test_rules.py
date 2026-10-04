from decimal import Decimal as D
from copy import deepcopy

import pytest

from cryptoquant.data.rules import parse_market_rules, round_market_quantity


def info():
    return {"symbol": "BTCUSDT", "status": "TRADING", "isSpotTradingAllowed": True, "filters": [
        {"filterType": "LOT_SIZE", "minQty": "0.002", "maxQty": "12", "stepSize": "0.002"},
        {"filterType": "MARKET_LOT_SIZE", "minQty": "0", "maxQty": "6", "stepSize": "0.003"},
        {"filterType": "MIN_NOTIONAL", "minNotional": "5", "applyToMarket": True, "avgPriceMins": 5},
        {"filterType": "NOTIONAL", "minNotional": "12", "maxNotional": "1000", "applyMinToMarket": True, "applyMaxToMarket": True, "avgPriceMins": 0},
    ]}


def test_market_filter_intersection_uses_lcm_not_max_step():
    rules = parse_market_rules(info())
    assert rules.step_size == D("0.006")
    assert round_market_quantity(D("0.011"), rules) == D("0.006")
    assert rules.min_quantity == D("0.002") and rules.max_quantity == D("6")
    assert rules.min_notional == D("12") and rules.max_notional == D("1000")
    assert rules.average_price_minutes == (5, 0)


def test_disabled_zero_market_step_keeps_lot_step():
    item = info()
    item["filters"][1].update(stepSize="0", maxQty="0")
    assert parse_market_rules(item).step_size == D("0.002")
    assert parse_market_rules(item).max_quantity == D("12")


def test_notional_market_flags_and_experiment_floor_apply():
    item = info()
    item["filters"][2]["applyToMarket"] = False
    item["filters"][3].update(applyMinToMarket=False, applyMaxToMarket=False)
    rules = parse_market_rules(item)
    assert rules.min_notional == D("10") and rules.max_notional is None


@pytest.mark.parametrize("change", ["status", "unknown", "bad_number", "bad_flag", "inconsistent", "no_lot", "not_spot"])
def test_unusable_rules_are_rejected(change):
    item = deepcopy(info())
    if change == "status":
        item["status"] = "BREAK"
    elif change == "unknown":
        item["filters"].append({"filterType": "FUTURE_MARKET_RULE"})
    elif change == "bad_number":
        item["filters"][0]["stepSize"] = "nan"
    elif change == "bad_flag":
        item["filters"][2]["applyToMarket"] = "false"
    elif change == "inconsistent":
        item["filters"][0]["minQty"] = "20"
    elif change == "no_lot":
        item["filters"] = item["filters"][1:]
    else:
        item["isSpotTradingAllowed"] = False
    with pytest.raises(ValueError):
        parse_market_rules(item)

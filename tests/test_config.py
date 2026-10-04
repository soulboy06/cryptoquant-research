from pathlib import Path
from decimal import Decimal

import pytest

from cryptoquant.config import load_config

DEFAULT = Path(__file__).parents[1] / "configs/first_experiment.toml"


def test_default_config_has_shared_budget_and_utc_dates():
    config = load_config(DEFAULT)
    assert config.initial_cash == Decimal("100")
    assert config.equity_floor == Decimal("50")
    assert config.download_start.utcoffset().total_seconds() == 0
    assert config.expected_hours == 42384
    assert config.costs["base"].fee == Decimal("0.001")


def test_data_policy_is_versioned_and_old_config_remains_strict(tmp_path):
    text = DEFAULT.read_text(encoding='utf-8')
    path = tmp_path / 'policy.toml'
    path.write_text('\n'.join(line for line in text.splitlines() if not line.startswith('data_policy =')), encoding='utf-8')
    assert load_config(path).data_policy == 'strict_v0'
    path.write_text(text + '\n', encoding='utf-8')
    assert load_config(path).data_policy == 'halt_aware_v2'
    path.write_text(text.replace('halt_aware_v2', 'ignore_errors'), encoding='utf-8')
    with pytest.raises(ValueError, match='policy'):
        load_config(path)


@pytest.mark.parametrize("before,after", [
    ('mode = "simulation"', 'mode = "live"'),
    ('initial_cash = "100"', 'initial_cash = "-1"'),
    ('equity_floor = "50"', 'equity_floor = "100"'),
    ('weight_per_symbol = "0.30"', 'weight_per_symbol = "0.40"'),
    ('stop_loss = "0.08"', 'stop_loss = "nan"'),
    ('fee = "0.001"', 'fee = "-0.001"'),
    ('adverse_price = "0.0005"', 'adverse_price = "1"'),
    ('2021-12-01T00:00:00Z', '2027-12-01T00:00:00Z'),
    ('2021-12-01T00:00:00Z', '2021-12-01T00:00:00'),
    ('2021-12-01T00:00:00Z', '2021-12-01T00:00:00+08:00'),
    ('2021-12-01T00:00:00Z', '2021-12-01T00:00:01Z'),
    ('symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]', 'symbols = ["BTCUSDT", "BTCUSDT"]'),
    ('cooldown_hours = 4', 'cooldown_hours = -1'),
    ('initial_cash = "100"', 'initial_cash = 100.0'),
])
def test_invalid_config_is_rejected(tmp_path, before, after):
    path = tmp_path / "invalid.toml"
    path.write_text(DEFAULT.read_text().replace(before, after), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)

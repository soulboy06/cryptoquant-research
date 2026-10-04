"""第五轮的有限研究参数；原执行Config与时间分区不改写。"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
from pathlib import Path
from types import MappingProxyType
import tomllib

from cryptoquant.config import Config, Cost, load_config
from cryptoquant.models.labels import LABEL_POLICIES


def _utc(text):
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class ResearchWindow:
    name: str
    period: str
    fit_start: datetime
    fit_end: datetime
    start: datetime
    end: datetime


RESEARCH_WINDOWS = MappingProxyType({
    name: ResearchWindow(name, period, _utc('2022-01-01'), _utc(start), _utc(start), _utc(end))
    for name, period, start, end in [
        ('W1', 'development', '2023-01-01', '2024-01-01'),
        ('W2', 'development', '2024-01-01', '2025-01-01'),
        ('R2025', 'validation', '2025-01-01', '2025-12-31T20:00:00')]
})
_FIXED_VALUES_V5 = dict(execution_config='second_experiment.toml', label_policies=list(LABEL_POLICIES),
                        C='0.1', thresholds=['0.40', '0.50', '0.60', '0.64'], weekly_target='0.015',
                        max_account_runs=30, windows=list(RESEARCH_WINDOWS))
_FIXED_VALUES_V6 = dict(execution_config='second_experiment.toml', label_policies=['net_positive_base_v1'],
                        C='0.1', thresholds=['0.50'], weekly_target='0.015',
                        max_account_runs=30, windows=list(RESEARCH_WINDOWS),
                        exit_variants=['C0', 'C1', 'C2', 'C3'])


@dataclass(frozen=True)
class ResearchConfig:
    execution_config: Config
    execution_config_path: Path
    research_config_path: Path
    execution_config_hash: str
    research_config_hash: str
    label_policies: tuple[str, ...]
    C: Decimal
    thresholds: tuple[Decimal, ...]
    weekly_target: Decimal
    max_account_runs: int
    windows: tuple[str, ...]
    exit_variants: tuple[str, ...] = ('C0', 'C1', 'C2', 'C3')


def load_research_config(path, root=None):
    path = Path(path).resolve()
    root = Path(root).resolve() if root is not None else path.parent.parent
    configs = root / 'configs'
    if not path.is_relative_to(configs):
        raise ValueError('research config must be inside project configs')
    raw = path.read_bytes()
    values = tomllib.loads(raw.decode('utf-8-sig'))
    if values == _FIXED_VALUES_V5:
        exit_variants = ('C0', 'C1', 'C2', 'C3')
    elif values == _FIXED_VALUES_V6:
        exit_variants = tuple(values['exit_variants'])
    else:
        raise ValueError('research fields or candidates differ from fixed research scope')
    execution_path = (path.parent / values['execution_config']).resolve()
    if not execution_path.is_relative_to(configs):
        raise ValueError('execution config must remain inside project configs')
    execution = load_config(execution_path)
    fixed_costs = {'base': Cost(Decimal('.001'), Decimal('.0005')),
                   'higher_execution': Cost(Decimal('.001'), Decimal('.001')),
                   'strict': Cost(Decimal('.002'), Decimal('.001'))}
    if not (execution.symbols == ('BTCUSDT', 'ETHUSDT', 'SOLUSDT') and
            execution.feature_policy == 'kline_and_funding' and execution.model_family == 'logistic_regression' and
            execution.data_policy == 'halt_aware_v2' and execution.initial_cash == Decimal('100') and
            execution.equity_floor == Decimal('50') and execution.weight_per_symbol == Decimal('.30') and
            execution.stop_loss == Decimal('.08') and execution.cooldown_hours == 4 and
            execution.minimum_order_notional == Decimal('10') and execution.costs == fixed_costs):
        raise ValueError('execution model, features, capital, risk or costs differ from frozen scope')
    if not (execution.development_start == RESEARCH_WINDOWS['W1'].fit_start and
            execution.development_end == RESEARCH_WINDOWS['W2'].end and
            execution.validation_start == RESEARCH_WINDOWS['R2025'].start and
            execution.validation_end == RESEARCH_WINDOWS['R2025'].end):
        raise ValueError('execution partition boundaries differ from fixed research windows')
    return ResearchConfig(execution, execution_path, path, execution.config_hash, hashlib.sha256(raw).hexdigest(),
                          tuple(values['label_policies']), Decimal(values['C']),
                          tuple(Decimal(x) for x in values['thresholds']), Decimal(values['weekly_target']),
                          values['max_account_runs'], tuple(values['windows']), exit_variants)

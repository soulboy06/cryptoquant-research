"""第五轮的有限研究参数；原执行Config与时间分区不改写。"""

from dataclasses import dataclass
from collections.abc import Mapping
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
_FIXED_REGIME_PARAMETERS = dict(symbol='BTCUSDT', adx_period=14, adx_min=20,
                                ema_period=72, slope_hours=24, history_hours=744)
_FIXED_VALUES_V7 = dict(execution_config='second_experiment.toml', label_policies=['net_positive_base_v1'],
                        C='0.1', thresholds=['0.50'], weekly_target='0.015',
                        max_account_runs=9, windows=list(RESEARCH_WINDOWS), exit_variants=['C2'],
                        regime_variants=['R0', 'R1'], regime=dict(_FIXED_REGIME_PARAMETERS))
_FIXED_DYNAMIC_VARIANTS = {
    'R2': dict(name='dynamic_threshold', favorable_threshold='0.50', favorable_weight='0.30',
               weak_threshold='0.60', weak_weight='0.30'),
    'R3': dict(name='dynamic_sizing', favorable_threshold='0.50', favorable_weight='0.30',
               weak_threshold='0.50', weak_weight='0.10'),
    'R4': dict(name='dual_synergy', favorable_threshold='0.50', favorable_weight='0.30',
               weak_threshold='0.60', weak_weight='0.15'),
}
_FIXED_VALUES_V8 = dict(execution_config='second_experiment.toml', label_policies=['net_positive_base_v1'],
                        C='0.1', thresholds=['0.50', '0.60'], weekly_target='0.015',
                        max_account_runs=16, windows=list(RESEARCH_WINDOWS), exit_variants=['C2'],
                        dynamic_variants=['R2', 'R3', 'R4'], regime=dict(_FIXED_REGIME_PARAMETERS),
                        variants=dict(_FIXED_DYNAMIC_VARIANTS))
_FIXED_ALPHA_VARIANTS = {
    'R5': dict(name='alpha_decoupled_20', favorable_weight='0.30',
               weak_alpha_weight='0.20', weak_ordinary_weight='0.10', threshold='0.50'),
    'R6': dict(name='alpha_decoupled_25', favorable_weight='0.30',
               weak_alpha_weight='0.25', weak_ordinary_weight='0.10', threshold='0.50'),
    'R7': dict(name='alpha_multi_horizon', favorable_weight='0.30',
               weak_alpha_accelerating_weight='0.25', weak_alpha_decelerating_weight='0.15',
               weak_ordinary_weight='0.10', threshold='0.50'),
}
_FIXED_VALUES_V9 = dict(execution_config='second_experiment.toml', label_policies=['net_positive_base_v1'],
                        C='0.1', thresholds=['0.50'], weekly_target='0.015',
                        max_account_runs=16, windows=list(RESEARCH_WINDOWS), exit_variants=['C2'],
                        alpha_variants=['R5', 'R6', 'R7'], regime=dict(_FIXED_REGIME_PARAMETERS),
                        variants=dict(_FIXED_ALPHA_VARIANTS))


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
    regime_variants: tuple[str, ...] = ()
    regime_parameters: Mapping[str, str | int] | None = None
    dynamic_variants: tuple[str, ...] = ()
    variant_parameters: Mapping[str, Mapping[str, str | int]] | None = None
    alpha_variants: tuple[str, ...] = ()


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
    elif values == _FIXED_VALUES_V7:
        exit_variants = tuple(values['exit_variants'])
    elif values == _FIXED_VALUES_V8:
        exit_variants = tuple(values['exit_variants'])
    elif values == _FIXED_VALUES_V9:
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
                          values['max_account_runs'], tuple(values['windows']), exit_variants,
                          tuple(values.get('regime_variants', ())),
                          MappingProxyType(dict(values['regime'])) if 'regime' in values else None,
                          tuple(values.get('dynamic_variants', ())),
                          MappingProxyType({k: MappingProxyType(v) for k, v in values['variants'].items()}) if 'variants' in values else None,
                          tuple(values.get('alpha_variants', ())))


"""第八轮动态阈值调节与自适应仓位响应模块。

消费模型预测概率与已闭合 BTC 市场状态（EXP-122），在每个 4h 决策点根据
当前市场状态（Favorable / Weak）动态确定准入阈值与目标仓位权重。
严格因果对齐：输入状态仅截至 t-1h，严禁未来信息泄露。
"""
from decimal import Decimal
import numpy as np
import pandas as pd

from cryptoquant.trading.ledger import ZERO


DYNAMIC_VARIANTS = ('R2', 'R3', 'R4')
DYNAMIC_TARGET_COLUMNS = ['symbol', 'decision_time', 'probability', 'target_weight']
AUDIT_TARGET_COLUMNS = [
    'symbol', 'decision_time', 'probability', 'target_weight',
    'regime_state', 'applied_threshold', 'applied_weight'
]

VARIANT_SPECS = {
    'R2': {
        'name': 'dynamic_threshold',
        'favorable': {'threshold': 0.50, 'weight': Decimal('0.30')},
        'weak': {'threshold': 0.60, 'weight': Decimal('0.30')},
    },
    'R3': {
        'name': 'dynamic_sizing',
        'favorable': {'threshold': 0.50, 'weight': Decimal('0.30')},
        'weak': {'threshold': 0.50, 'weight': Decimal('0.10')},
    },
    'R4': {
        'name': 'dual_synergy',
        'favorable': {'threshold': 0.50, 'weight': Decimal('0.30')},
        'weak': {'threshold': 0.60, 'weight': Decimal('0.15')},
    },
}


def _validate_inputs(probabilities, regime_states, variant):
    if variant not in DYNAMIC_VARIANTS:
        raise ValueError(f"unsupported variant: {variant}, must be one of {DYNAMIC_VARIANTS}")
    
    expected_prob_cols = ['symbol', 'decision_time', 'probability']
    if list(probabilities.columns) != expected_prob_cols:
        raise ValueError(f"probabilities must have columns {expected_prob_cols}, got {list(probabilities.columns)}")
    
    required_regime_cols = {'decision_time', 'available_time', 'state_valid', 'allow_buy'}
    if not required_regime_cols.issubset(set(regime_states.columns)):
        raise ValueError(f"regime_states missing required columns: {required_regime_cols - set(regime_states.columns)}")
    
    prob_times = pd.DatetimeIndex(probabilities['decision_time'])
    regime_times = pd.DatetimeIndex(regime_states['decision_time'])
    
    if str(getattr(prob_times.dtype, 'tz', None)) != 'UTC' or str(getattr(regime_times.dtype, 'tz', None)) != 'UTC':
        raise ValueError("decision_time in both tables must be UTC")
    
    avail_times = pd.DatetimeIndex(regime_states['available_time'])
    if (avail_times > regime_times).any():
        raise ValueError("regime available_time cannot be in the future of decision_time")
    
    if regime_states['decision_time'].duplicated().any():
        raise ValueError("duplicate decision_time in regime_states")
    
    unique_prob_times = set(probabilities['decision_time'].unique())
    regime_time_set = set(regime_states['decision_time'])
    if not unique_prob_times.issubset(regime_time_set):
        missing = unique_prob_times - regime_time_set
        raise ValueError(f"probabilities decision_times not fully covered by regime_states, missing: {len(missing)}")


def build_dynamic_decision_targets(probabilities, regime_states, variant):
    """根据市场状态生成符合引擎要求的决策目标表与详细审计表。
    
    返回 (decision_targets, audit_targets)：
    - decision_targets: 四列 ['symbol', 'decision_time', 'probability', 'target_weight']，供交易引擎消费；
    - audit_targets: 包含 regime_state、applied_threshold 与 applied_weight 的审计对账表。
    """
    _validate_inputs(probabilities, regime_states, variant)
    spec = VARIANT_SPECS[variant]
    
    regime_lookup = {}
    for row in regime_states.itertuples(index=False):
        t = row.decision_time
        is_favorable = bool(row.state_valid and row.allow_buy)
        regime_type = 'favorable' if is_favorable else 'weak'
        rules = spec[regime_type]
        regime_lookup[t] = {
            'regime_state': regime_type,
            'threshold': rules['threshold'],
            'weight': rules['weight'],
        }
    
    records = []
    audit_records = []
    
    for row in probabilities.itertuples(index=False):
        sym = row.symbol
        t = row.decision_time
        prob = row.probability
        state_info = regime_lookup[t]
        thresh = state_info['threshold']
        target_w = state_info['weight']
        regime_name = state_info['regime_state']
        
        if pd.isna(prob):
            weight = None
        elif prob >= thresh:
            weight = target_w
        else:
            weight = ZERO
        
        records.append({
            'symbol': sym,
            'decision_time': t,
            'probability': prob,
            'target_weight': weight,
        })
        audit_records.append({
            'symbol': sym,
            'decision_time': t,
            'probability': prob,
            'target_weight': weight,
            'regime_state': regime_name,
            'applied_threshold': thresh,
            'applied_weight': target_w,
        })
    
    targets_df = pd.DataFrame(records, columns=DYNAMIC_TARGET_COLUMNS)
    audit_df = pd.DataFrame(audit_records, columns=AUDIT_TARGET_COLUMNS)
    return targets_df, audit_df

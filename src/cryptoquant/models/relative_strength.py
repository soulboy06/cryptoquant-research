"""第九轮多币种相对强弱解耦与自适应配仓响应模块。

消费模型预测概率、已闭合 BTC 市场状态（EXP-122）与标的相对强弱（Alpha），
在每个 4h 决策点根据大盘状态与标的自身超额动量动态确定目标仓位权重。
严格因果对齐：输入状态与超额特征仅截至 t-1h，严禁未来信息泄露。
"""
from decimal import Decimal
import numpy as np
import pandas as pd

from cryptoquant.trading.ledger import ZERO


ALPHA_VARIANTS = ('R5', 'R6', 'R7')
ALPHA_TARGET_COLUMNS = ['symbol', 'decision_time', 'probability', 'target_weight']
ALPHA_AUDIT_COLUMNS = [
    'symbol', 'decision_time', 'probability', 'target_weight',
    'regime_state', 'is_alpha_leader', 'is_accelerating', 'applied_weight'
]

VARIANT_SPECS = {
    'R5': {
        'name': 'alpha_decoupled_20',
        'threshold': 0.50,
        'favorable_weight': Decimal('0.30'),
        'weak_alpha_weight': Decimal('0.20'),
        'weak_ordinary_weight': Decimal('0.10'),
    },
    'R6': {
        'name': 'alpha_decoupled_25',
        'threshold': 0.50,
        'favorable_weight': Decimal('0.30'),
        'weak_alpha_weight': Decimal('0.25'),
        'weak_ordinary_weight': Decimal('0.10'),
    },
    'R7': {
        'name': 'alpha_multi_horizon',
        'threshold': 0.50,
        'favorable_weight': Decimal('0.30'),
        'weak_alpha_accelerating_weight': Decimal('0.25'),
        'weak_alpha_decelerating_weight': Decimal('0.15'),
        'weak_ordinary_weight': Decimal('0.10'),
    },
}


def compute_relative_strength_map(features_by_symbol):
    """计算各标的在每个决策时刻对 BTC 的相对强弱与多周期动量加速状态。
    
    返回 dict 映射: (symbol, decision_time) -> dict(is_alpha_leader, is_accelerating)
    """
    if 'BTCUSDT' not in features_by_symbol:
        raise ValueError("features_by_symbol must contain BTCUSDT")
    
    btc_df = features_by_symbol['BTCUSDT']
    if 'decision_time' not in btc_df.columns or 'return_72h' not in btc_df.columns or 'return_24h' not in btc_df.columns:
        raise ValueError("BTCUSDT features missing required columns (decision_time, return_72h, return_24h)")
    
    btc_lookup = {}
    for row in btc_df.itertuples(index=False):
        btc_lookup[row.decision_time] = {
            'r72': float(row.return_72h) if pd.notna(row.return_72h) else 0.0,
            'r24': float(row.return_24h) if pd.notna(row.return_24h) else 0.0,
        }
    
    alpha_map = {}
    for sym, df in features_by_symbol.items():
        for row in df.itertuples(index=False):
            t = row.decision_time
            r72 = float(row.return_72h) if pd.notna(row.return_72h) else 0.0
            r24 = float(row.return_24h) if pd.notna(row.return_24h) else 0.0
            
            btc_data = btc_lookup.get(t, {'r72': 0.0, 'r24': 0.0})
            btc_r72 = btc_data['r72']
            btc_r24 = btc_data['r24']
            
            excess_r72 = r72 - btc_r72
            excess_r24 = r24 - btc_r24
            
            is_leader = bool(excess_r72 > 0 and r72 > 0)
            is_accelerating = bool(is_leader and excess_r24 > 0 and r24 > 0)
            
            alpha_map[(sym, t)] = {
                'is_alpha_leader': is_leader,
                'is_accelerating': is_accelerating,
                'return_72h': r72,
                'excess_return_72h': excess_r72,
            }
            
    return alpha_map


def _validate_inputs(probabilities, regime_states, variant):
    if variant not in ALPHA_VARIANTS:
        raise ValueError(f"unsupported variant: {variant}, must be one of {ALPHA_VARIANTS}")
    
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


def build_alpha_decision_targets(probabilities, regime_states, alpha_map, variant):
    """根据大盘状态与标的自身相对强弱生成符合引擎要求的决策目标表与详细审计表。
    
    返回 (decision_targets, audit_targets)：
    - decision_targets: 四列 ['symbol', 'decision_time', 'probability', 'target_weight']，供交易引擎消费；
    - audit_targets: 包含 regime_state、is_alpha_leader、is_accelerating 与 applied_weight 的审计表。
    """
    _validate_inputs(probabilities, regime_states, variant)
    if isinstance(alpha_map, dict) and 'BTCUSDT' in alpha_map and hasattr(alpha_map['BTCUSDT'], 'columns'):
        alpha_map = compute_relative_strength_map(alpha_map)
    spec = VARIANT_SPECS[variant]
    threshold = spec['threshold']
    
    regime_lookup = {}
    for row in regime_states.itertuples(index=False):
        t = row.decision_time
        is_favorable = bool(row.state_valid and row.allow_buy)
        regime_lookup[t] = 'favorable' if is_favorable else 'weak'
    
    records = []
    audit_records = []
    
    for row in probabilities.itertuples(index=False):
        sym = row.symbol
        t = row.decision_time
        prob = row.probability
        
        regime_type = regime_lookup[t]
        alpha_info = alpha_map.get((sym, t), {'is_alpha_leader': False, 'is_accelerating': False})
        is_leader = alpha_info['is_alpha_leader']
        is_accel = alpha_info['is_accelerating']
        
        target_w = ZERO
        if regime_type == 'favorable':
            target_w = spec['favorable_weight']
        else:
            if variant == 'R5':
                target_w = spec['weak_alpha_weight'] if is_leader else spec['weak_ordinary_weight']
            elif variant == 'R6':
                target_w = spec['weak_alpha_weight'] if is_leader else spec['weak_ordinary_weight']
            elif variant == 'R7':
                if is_accel:
                    target_w = spec['weak_alpha_accelerating_weight']
                elif is_leader:
                    target_w = spec['weak_alpha_decelerating_weight']
                else:
                    target_w = spec['weak_ordinary_weight']
        
        if pd.isna(prob):
            final_weight = None
        elif prob >= threshold:
            final_weight = target_w
        else:
            final_weight = ZERO
        
        records.append({
            'symbol': sym,
            'decision_time': t,
            'probability': prob,
            'target_weight': final_weight,
        })
        audit_records.append({
            'symbol': sym,
            'decision_time': t,
            'probability': prob,
            'target_weight': final_weight,
            'regime_state': regime_type,
            'is_alpha_leader': is_leader,
            'is_accelerating': is_accel,
            'applied_weight': target_w,
        })
        
    targets_df = pd.DataFrame(records, columns=ALPHA_TARGET_COLUMNS)
    audit_df = pd.DataFrame(audit_records, columns=ALPHA_AUDIT_COLUMNS)
    
    targets_df.sort_values(by=['decision_time', 'symbol'], inplace=True, ignore_index=True)
    audit_df.sort_values(by=['decision_time', 'symbol'], inplace=True, ignore_index=True)
    
    return targets_df, audit_df

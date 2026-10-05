from datetime import datetime, timezone
from decimal import Decimal
import pandas as pd
import pytest

from cryptoquant.models.relative_strength import (
    ALPHA_VARIANTS,
    build_alpha_decision_targets,
    compute_relative_strength_map,
)
from cryptoquant.models.research_config import load_research_config
from cryptoquant.trading.ledger import ZERO


def test_ninth_experiment_config_loading():
    cfg = load_research_config('configs/ninth_experiment.toml')
    assert cfg.alpha_variants == ('R5', 'R6', 'R7')
    assert cfg.thresholds == (Decimal('0.50'),)
    assert cfg.weekly_target == Decimal('0.015')
    assert cfg.max_account_runs == 16
    assert cfg.exit_variants == ('C2',)
    assert cfg.variant_parameters is not None
    assert 'R5' in cfg.variant_parameters
    assert cfg.variant_parameters['R5']['weak_alpha_weight'] == '0.20'
    assert cfg.variant_parameters['R6']['weak_alpha_weight'] == '0.25'
    assert cfg.variant_parameters['R7']['weak_alpha_accelerating_weight'] == '0.25'
    assert cfg.variant_parameters['R7']['weak_alpha_decelerating_weight'] == '0.15'


def test_compute_relative_strength_map():
    t1 = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    t2 = datetime(2024, 1, 1, 4, 0, tzinfo=timezone.utc)
    
    btc_df = pd.DataFrame([
        {'decision_time': t1, 'return_72h': 0.05, 'return_24h': 0.01},
        {'decision_time': t2, 'return_72h': -0.02, 'return_24h': -0.01},
    ])
    eth_df = pd.DataFrame([
        {'decision_time': t1, 'return_72h': 0.02, 'return_24h': 0.00},  # Underperforming BTC
        {'decision_time': t2, 'return_72h': 0.01, 'return_24h': 0.01},   # Outperforming BTC (0.01 > -0.02, r72 > 0)
    ])
    sol_df = pd.DataFrame([
        {'decision_time': t1, 'return_72h': 0.15, 'return_24h': 0.05},  # Outperforming BTC (0.15 > 0.05, 0.05 > 0.01) -> Accelerating
        {'decision_time': t2, 'return_72h': 0.10, 'return_24h': -0.02},  # Outperforming BTC (0.10 > -0.02), but decel (-0.02 < -0.01)
    ])
    
    alpha_map = compute_relative_strength_map({
        'BTCUSDT': btc_df,
        'ETHUSDT': eth_df,
        'SOLUSDT': sol_df,
    })
    
    # t1 checks
    assert alpha_map[('ETHUSDT', t1)]['is_alpha_leader'] is False
    assert alpha_map[('SOLUSDT', t1)]['is_alpha_leader'] is True
    assert alpha_map[('SOLUSDT', t1)]['is_accelerating'] is True
    
    # t2 checks
    assert alpha_map[('ETHUSDT', t2)]['is_alpha_leader'] is True
    assert alpha_map[('SOLUSDT', t2)]['is_alpha_leader'] is True
    assert alpha_map[('SOLUSDT', t2)]['is_accelerating'] is False


def test_build_alpha_decision_targets_weights():
    t1 = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    
    # BTC state: Weak (state_valid=True, allow_buy=False)
    regime = pd.DataFrame([{
        'decision_time': t1,
        'available_time': t1,
        'state_valid': True,
        'allow_buy': False,
    }])
    
    probs = pd.DataFrame([
        {'symbol': 'BTCUSDT', 'decision_time': t1, 'probability': 0.60},
        {'symbol': 'ETHUSDT', 'decision_time': t1, 'probability': 0.60},
        {'symbol': 'SOLUSDT', 'decision_time': t1, 'probability': 0.60},
        {'symbol': 'SOLUSDT', 'decision_time': t1, 'probability': 0.45},  # Low prob
    ])
    # Drop duplicate for clean join
    probs = pd.DataFrame([
        {'symbol': 'BTCUSDT', 'decision_time': t1, 'probability': 0.60},
        {'symbol': 'ETHUSDT', 'decision_time': t1, 'probability': 0.60},
        {'symbol': 'SOLUSDT', 'decision_time': t1, 'probability': 0.60},
    ])
    
    alpha_map = {
        ('BTCUSDT', t1): {'is_alpha_leader': False, 'is_accelerating': False},
        ('ETHUSDT', t1): {'is_alpha_leader': False, 'is_accelerating': False},
        ('SOLUSDT', t1): {'is_alpha_leader': True, 'is_accelerating': True},
    }
    
    # R5: SOL gets 0.20, others get 0.10
    targets_r5, audit_r5 = build_alpha_decision_targets(probs, regime, alpha_map, 'R5')
    weights_r5 = dict(zip(targets_r5['symbol'], targets_r5['target_weight']))
    assert weights_r5['SOLUSDT'] == Decimal('0.20')
    assert weights_r5['ETHUSDT'] == Decimal('0.10')
    assert weights_r5['BTCUSDT'] == Decimal('0.10')
    
    # R6: SOL gets 0.25, others get 0.10
    targets_r6, audit_r6 = build_alpha_decision_targets(probs, regime, alpha_map, 'R6')
    weights_r6 = dict(zip(targets_r6['symbol'], targets_r6['target_weight']))
    assert weights_r6['SOLUSDT'] == Decimal('0.25')
    assert weights_r6['ETHUSDT'] == Decimal('0.10')
    
    # R7: Accelerating SOL gets 0.25
    targets_r7, audit_r7 = build_alpha_decision_targets(probs, regime, alpha_map, 'R7')
    weights_r7 = dict(zip(targets_r7['symbol'], targets_r7['target_weight']))
    assert weights_r7['SOLUSDT'] == Decimal('0.25')
    
    # Now test decelerating leader in R7
    alpha_map[('SOLUSDT', t1)]['is_accelerating'] = False
    targets_r7_decel, _ = build_alpha_decision_targets(probs, regime, alpha_map, 'R7')
    weights_r7_decel = dict(zip(targets_r7_decel['symbol'], targets_r7_decel['target_weight']))
    assert weights_r7_decel['SOLUSDT'] == Decimal('0.15')


def test_build_alpha_decision_targets_favorable_regime():
    t1 = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
    regime = pd.DataFrame([{
        'decision_time': t1,
        'available_time': t1,
        'state_valid': True,
        'allow_buy': True,  # Favorable
    }])
    probs = pd.DataFrame([
        {'symbol': 'SOLUSDT', 'decision_time': t1, 'probability': 0.55},
        {'symbol': 'ETHUSDT', 'decision_time': t1, 'probability': 0.40},  # Below 0.50
    ])
    alpha_map = {
        ('SOLUSDT', t1): {'is_alpha_leader': False, 'is_accelerating': False},
        ('ETHUSDT', t1): {'is_alpha_leader': True, 'is_accelerating': True},
    }
    targets, _ = build_alpha_decision_targets(probs, regime, alpha_map, 'R5')
    weights = dict(zip(targets['symbol'], targets['target_weight']))
    assert weights['SOLUSDT'] == Decimal('0.30')
    assert weights['ETHUSDT'] == ZERO

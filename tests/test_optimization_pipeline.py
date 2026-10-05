from decimal import Decimal
import pandas as pd
import pytest

from cryptoquant.optimization.engine import (
    build_candidate_regression_targets,
    build_candidate_targets,
    calculate_fitness_score,
)
from cryptoquant.optimization.search_space import (
    SizingScheme,
)
from cryptoquant.optimization.walk_forward import (
    FOLDS,
)


def test_walk_forward_fold_invariants():
    """Verify walk-forward fold definitions enforce strict time causality and seal 2026."""
    assert len(FOLDS) == 3
    assert set(FOLDS.keys()) == {'W1', 'W2', 'R2025'}
    
    for fold_name, fold in FOLDS.items():
        assert fold.train_start < fold.train_end
        assert fold.eval_start < fold.eval_end
        # Train strictly precedes or ends at eval_start
        assert fold.train_end <= fold.eval_start
        # 2026 strictly forbidden in train or eval
        assert fold.train_start.year < 2026
        assert fold.train_end.year < 2026
        assert fold.eval_start.year < 2026
        # eval_end can be 2026-01-01 00:00 (the final point of 2025), but not later
        assert fold.eval_end <= pd.Timestamp('2026-01-01 00:00:00', tz='UTC')


def test_target_generation_logic():
    """Verify target generation respects regime, alpha leader status, and entry threshold."""
    symbols = ('BTCUSDT', 'ETHUSDT', 'SOLUSDT')
    timestamps = pd.date_range('2023-01-01', periods=10, freq='4h', tz='UTC')
    
    # Combined probabilities dataframe
    prob_records = []
    for t in timestamps:
        prob_records.append({'symbol': 'BTCUSDT', 'decision_time': t, 'probability': 0.60})
        prob_records.append({'symbol': 'ETHUSDT', 'decision_time': t, 'probability': 0.45})
        prob_records.append({'symbol': 'SOLUSDT', 'decision_time': t, 'probability': 0.60})
    prob_df = pd.DataFrame(prob_records)
    
    # Regime: first 5 rows favorable (allow_buy=True), last 5 rows weak (allow_buy=False)
    regime_records = []
    for i, t in enumerate(timestamps):
        regime_records.append({
            'decision_time': t,
            'state_valid': True,
            'allow_buy': bool(i < 5),
            'close': 16500.0,
            'ma_short': 16500.0,
            'ma_long': 16000.0,
        })
    regime_df = pd.DataFrame(regime_records)
    
    # Momentum: SOL is alpha leader (72h ret > 0 and > BTC)
    mom_records = []
    for t in timestamps:
        mom_records.append({'decision_time': t, 'symbol': 'BTCUSDT', 'return_72h': 0.01, 'history_valid': True})
        mom_records.append({'decision_time': t, 'symbol': 'ETHUSDT', 'return_72h': -0.02, 'history_valid': True})
        mom_records.append({'decision_time': t, 'symbol': 'SOLUSDT', 'return_72h': 0.05, 'history_valid': True})
    mom_df = pd.DataFrame(mom_records)
    
    sizing = SizingScheme(
        name='test_sizing',
        favorable_weight=Decimal('0.30'),
        weak_alpha_weight=Decimal('0.25'),
        weak_ordinary_weight=Decimal('0.00'),
    )
    
    targets = build_candidate_targets(prob_df, regime_df, mom_df, sizing, threshold=0.50, symbols=symbols)
    
    assert len(targets) == 30  # 10 timestamps * 3 symbols
    
    # Map for easy assertion: (decision_time, symbol) -> target_weight
    target_map = targets.set_index(['decision_time', 'symbol'])['target_weight'].to_dict()
    
    for i, t in enumerate(timestamps):
        if i < 5:
            # Favorable regime
            assert target_map[(t, 'BTCUSDT')] == Decimal('0.30')
            assert target_map[(t, 'ETHUSDT')] == Decimal('0.00')  # prob 0.45 < 0.50
            assert target_map[(t, 'SOLUSDT')] == Decimal('0.30')
        else:
            # Weak regime
            assert target_map[(t, 'BTCUSDT')] == Decimal('0.00')  # ordinary coin
            assert target_map[(t, 'ETHUSDT')] == Decimal('0.00')  # ordinary + low prob
            assert target_map[(t, 'SOLUSDT')] == Decimal('0.25')  # alpha leader!


def test_fitness_score_monotonicity():
    """Verify composite fitness penalizes drawdown and floor triggers, rewards g_week."""
    # Base candidate
    s1 = calculate_fitness_score(
        g_week=0.0010, worst_mdd=0.10, ret_2025=-0.02,
        min_cycles=35, floor_triggers=0
    )
    # Higher weekly return should have higher fitness
    s2 = calculate_fitness_score(
        g_week=0.0015, worst_mdd=0.10, ret_2025=-0.02,
        min_cycles=35, floor_triggers=0
    )
    assert s2 > s1
    
    # Higher MDD should have lower fitness
    s3 = calculate_fitness_score(
        g_week=0.0010, worst_mdd=0.20, ret_2025=-0.02,
        min_cycles=35, floor_triggers=0
    )
    assert s3 < s1
    
    # Floor trigger should incur massive penalty
    s4 = calculate_fitness_score(
        g_week=0.0010, worst_mdd=0.10, ret_2025=-0.02,
        min_cycles=35, floor_triggers=1
    )
    assert s4 < s1 - 50.0


def test_regression_target_generation_logic():
    """Verify continuous net return regression target generation respects margin hurdles."""
    symbols = ('BTCUSDT', 'ETHUSDT', 'SOLUSDT')
    timestamps = pd.date_range('2023-01-01', periods=10, freq='4h', tz='UTC')
    
    # Combined regression predictions dataframe (expected net returns)
    pred_records = []
    for t in timestamps:
        pred_records.append({'symbol': 'BTCUSDT', 'decision_time': t, 'expected_net_return': 0.005})
        pred_records.append({'symbol': 'ETHUSDT', 'decision_time': t, 'expected_net_return': -0.002})
        pred_records.append({'symbol': 'SOLUSDT', 'decision_time': t, 'expected_net_return': 0.003})
    pred_df = pd.DataFrame(pred_records)
    
    regime_records = []
    for i, t in enumerate(timestamps):
        regime_records.append({
            'decision_time': t,
            'state_valid': True,
            'allow_buy': bool(i < 5),
            'close': 16500.0,
            'ma_short': 16500.0,
            'ma_long': 16000.0,
        })
    regime_df = pd.DataFrame(regime_records)
    
    mom_records = []
    for t in timestamps:
        mom_records.append({'decision_time': t, 'symbol': 'BTCUSDT', 'return_72h': 0.01, 'history_valid': True})
        mom_records.append({'decision_time': t, 'symbol': 'ETHUSDT', 'return_72h': -0.02, 'history_valid': True})
        mom_records.append({'decision_time': t, 'symbol': 'SOLUSDT', 'return_72h': 0.05, 'history_valid': True})
    mom_df = pd.DataFrame(mom_records)
    
    sizing = SizingScheme(
        name='test_sizing',
        favorable_weight=Decimal('0.30'),
        weak_alpha_weight=Decimal('0.25'),
        weak_ordinary_weight=Decimal('0.00'),
    )
    
    # Margin = +0.001 (requires expected net return >= +0.1%)
    targets = build_candidate_regression_targets(pred_df, regime_df, mom_df, sizing, margin=0.001, symbols=symbols)
    
    assert len(targets) == 30
    assert (targets['probability'] >= 0.0).all() and (targets['probability'] <= 1.0).all()
    
    target_map = targets.set_index(['decision_time', 'symbol'])['target_weight'].to_dict()
    for i, t in enumerate(timestamps):
        if i < 5:
            # Favorable
            assert target_map[(t, 'BTCUSDT')] == Decimal('0.30')
            assert target_map[(t, 'ETHUSDT')] == Decimal('0.00')  # -0.002 < 0.001
            assert target_map[(t, 'SOLUSDT')] == Decimal('0.30')
        else:
            # Weak
            assert target_map[(t, 'BTCUSDT')] == Decimal('0.00')  # ordinary
            assert target_map[(t, 'ETHUSDT')] == Decimal('0.00')  # ordinary + below margin
            assert target_map[(t, 'SOLUSDT')] == Decimal('0.25')  # alpha leader!


from decimal import Decimal
import pandas as pd
import pytest

from cryptoquant.models.dynamic_regime import (
    DYNAMIC_VARIANTS,
    build_dynamic_decision_targets,
)
from cryptoquant.models.research_config import load_research_config
from cryptoquant.trading.ledger import ZERO


def test_eighth_experiment_config_loading():
    cfg = load_research_config('configs/eighth_experiment.toml')
    assert cfg.dynamic_variants == ('R2', 'R3', 'R4')
    assert cfg.thresholds == (Decimal('0.50'), Decimal('0.60'))
    assert cfg.weekly_target == Decimal('0.015')
    assert cfg.max_account_runs == 16
    assert cfg.exit_variants == ('C2',)
    assert cfg.variant_parameters is not None
    assert 'R2' in cfg.variant_parameters
    assert cfg.variant_parameters['R2']['weak_threshold'] == '0.60'
    assert cfg.variant_parameters['R3']['weak_weight'] == '0.10'
    assert cfg.variant_parameters['R4']['weak_weight'] == '0.15'


def _sample_fixtures():
    times = pd.date_range('2024-01-01 00:00:00', periods=4, freq='4h', tz='UTC')
    regime_df = pd.DataFrame({
        'decision_time': times,
        'available_time': times,
        'state_valid': [True, True, True, False],
        'allow_buy': [True, False, False, False],
    })
    # Times 0: Favorable
    # Times 1: Weak (allow_buy=False)
    # Times 2: Weak (allow_buy=False)
    # Times 3: Weak (state_valid=False)

    prob_records = []
    # Test probabilities: 0.45 (below all), 0.55 (between 0.50 and 0.60), 0.65 (above all)
    probs = [0.45, 0.55, 0.65]
    for t in times:
        for s, p in zip(['BTCUSDT', 'ETHUSDT', 'SOLUSDT'], probs):
            prob_records.append({'symbol': s, 'decision_time': t, 'probability': p})
    prob_df = pd.DataFrame(prob_records)
    return prob_df, regime_df, times


def test_r2_dynamic_threshold():
    prob_df, regime_df, times = _sample_fixtures()
    targets, audit = build_dynamic_decision_targets(prob_df, regime_df, 'R2')
    
    # Check columns
    assert list(targets.columns) == ['symbol', 'decision_time', 'probability', 'target_weight']
    assert len(targets) == 12

    # At time 0 (Favorable): T=0.50, W=0.30
    # 0.45 -> 0, 0.55 -> 0.30, 0.65 -> 0.30
    t0_targets = targets[targets.decision_time == times[0]].set_index('symbol')['target_weight']
    assert t0_targets['BTCUSDT'] == ZERO
    assert t0_targets['ETHUSDT'] == Decimal('0.30')
    assert t0_targets['SOLUSDT'] == Decimal('0.30')

    # At time 1 (Weak): T=0.60, W=0.30
    # 0.45 -> 0, 0.55 -> 0 (filtered!), 0.65 -> 0.30 (allowed!)
    t1_targets = targets[targets.decision_time == times[1]].set_index('symbol')['target_weight']
    assert t1_targets['BTCUSDT'] == ZERO
    assert t1_targets['ETHUSDT'] == ZERO
    assert t1_targets['SOLUSDT'] == Decimal('0.30')


def test_r3_dynamic_sizing():
    prob_df, regime_df, times = _sample_fixtures()
    targets, audit = build_dynamic_decision_targets(prob_df, regime_df, 'R3')

    # At time 0 (Favorable): T=0.50, W=0.30
    t0_targets = targets[targets.decision_time == times[0]].set_index('symbol')['target_weight']
    assert t0_targets['ETHUSDT'] == Decimal('0.30')

    # At time 1 (Weak): T=0.50, W=0.10
    # 0.45 -> 0, 0.55 -> 0.10 (sized down!), 0.65 -> 0.10
    t1_targets = targets[targets.decision_time == times[1]].set_index('symbol')['target_weight']
    assert t1_targets['BTCUSDT'] == ZERO
    assert t1_targets['ETHUSDT'] == Decimal('0.10')
    assert t1_targets['SOLUSDT'] == Decimal('0.10')


def test_r4_dual_synergy():
    prob_df, regime_df, times = _sample_fixtures()
    targets, audit = build_dynamic_decision_targets(prob_df, regime_df, 'R4')

    # At time 0 (Favorable): T=0.50, W=0.30
    t0_targets = targets[targets.decision_time == times[0]].set_index('symbol')['target_weight']
    assert t0_targets['ETHUSDT'] == Decimal('0.30')
    assert t0_targets['SOLUSDT'] == Decimal('0.30')

    # At time 1 (Weak): T=0.60, W=0.15
    # 0.45 -> 0, 0.55 -> 0 (filtered by threshold!), 0.65 -> 0.15 (sized down!)
    t1_targets = targets[targets.decision_time == times[1]].set_index('symbol')['target_weight']
    assert t1_targets['BTCUSDT'] == ZERO
    assert t1_targets['ETHUSDT'] == ZERO
    assert t1_targets['SOLUSDT'] == Decimal('0.15')


def test_validation_errors():
    prob_df, regime_df, times = _sample_fixtures()

    with pytest.raises(ValueError, match="unsupported variant"):
        build_dynamic_decision_targets(prob_df, regime_df, 'R99')

    with pytest.raises(ValueError, match="probabilities must have columns"):
        build_dynamic_decision_targets(prob_df.drop(columns=['probability']), regime_df, 'R2')

    with pytest.raises(ValueError, match="missing required columns"):
        build_dynamic_decision_targets(prob_df, regime_df.drop(columns=['allow_buy']), 'R2')

    # Future available time
    bad_regime = regime_df.copy()
    bad_regime['available_time'] = bad_regime['decision_time'] + pd.Timedelta(1, unit='h')
    with pytest.raises(ValueError, match="cannot be in the future"):
        build_dynamic_decision_targets(prob_df, bad_regime, 'R2')

    # Incomplete coverage
    with pytest.raises(ValueError, match="not fully covered"):
        build_dynamic_decision_targets(prob_df, regime_df.iloc[:2], 'R2')

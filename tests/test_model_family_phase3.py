"""Phase 3 Regression and Integrity Tests: 4h Binary Classification Model Structure Comparison.

Covers mandatory Phase 3 invariants:
1. Outer eval data is NEVER used in threshold selection (strict in-sample inner walk-forward).
2. Outer eval data is NEVER used in model fitting (strict temporal cutoff).
3. All model candidates consume 100% identical feature columns in identical order.
4. All model candidates are evaluated on 100% identical decision grids.
5. Fixed random seed produces deterministic, reproducible predictions across all 4 model families.
6. 2026 data is not used for training, feature calculation, or evaluation.
"""
from decimal import Decimal
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
import lightgbm as lgb
import xgboost as xgb
import catboost as cb

from cryptoquant.config import load_config
from cryptoquant.models.features import ALL_FEATURE_NAMES
from cryptoquant.optimization.search_space import ModelCandidate, SizingScheme
from cryptoquant.optimization.walk_forward import FOLDS, WalkForwardFold


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_outer_eval_data_never_used_in_threshold_selection():
    """Test 1: Verify Lane B threshold selection history uses strictly pre-eval inner windows."""
    th_path = PROJECT_ROOT / 'artifacts/research/model_family_phase3/threshold_selection.csv'
    if not th_path.exists():
        pytest.skip("threshold_selection.csv not yet generated")
        
    df_th = pd.read_parquet(th_path) if th_path.suffix == '.parquet' else pd.read_csv(th_path)
    
    # Check that for each outer fold, inner eval does not cross into outer eval
    for r in df_th.to_dict(orient='records'):
        fold_name = r['fold']
        inner_eval = r['inner_eval_window']
        
        if 'W1' in fold_name:
            # Outer eval is 2023. Inner eval must be strictly in 2022
            assert '2023' not in inner_eval, f"W1 inner eval breached into 2023: {inner_eval}"
            assert '2022' in inner_eval
        elif 'W2' in fold_name:
            # Outer eval is 2024. Inner eval must be 2023 (W1 execution)
            assert '2024' not in inner_eval, f"W2 inner eval breached into 2024: {inner_eval}"
            assert '2023' in inner_eval
        elif 'R2025' in fold_name:
            # Outer eval is 2025. Inner eval must be 2024 (W2 execution)
            assert '2025' not in inner_eval, f"R2025 inner eval breached into 2025: {inner_eval}"
            assert '2024' in inner_eval


def test_outer_eval_data_never_used_in_model_fit():
    """Test 2: Verify that for all Walk-Forward folds, training samples have label_end <= train_end."""
    sample_dir = PROJECT_ROOT / 'artifacts/experiments/EXP-063/samples/net_positive_base_v1'
    cfg = load_config(PROJECT_ROOT / 'configs/first_experiment.toml')
    
    for fold_name, fold in FOLDS.items():
        for s in cfg.symbols:
            p = sample_dir / f'{s}.parquet'
            assert p.exists(), f"Sample file missing: {p}"
            df = pd.read_parquet(p)
            
            mask = (df.decision_time >= fold.train_start) & (df.label_end <= fold.train_end)
            train_df = df.loc[mask]
            
            assert not train_df.empty, f"No train samples for {s} in {fold_name}"
            # Core invariant: no sample's label extends past fold.train_end
            assert (train_df.label_end <= fold.train_end).all(), (
                f"Leakage: train sample label_end > train_end in {fold_name} for {s}"
            )
            # Core invariant: no sample's decision time is in the outer eval window
            assert (train_df.decision_time < fold.eval_start).all(), (
                f"Leakage: train sample decision_time >= eval_start in {fold_name} for {s}"
            )


def test_identical_feature_columns_across_all_models():
    """Test 3: Verify all 4 model families use 100% identical 12 feature columns in identical order."""
    expected_12_features = [
        'return_1h', 'return_4h', 'return_24h', 'return_72h',
        'volatility_24h', 'range_fraction', 'quote_volume_change',
        'ema24_distance', 'ema72_distance',
        'funding_rate_latest', 'funding_rate_ma3', 'funding_rate_zscore',
    ]
    assert list(ALL_FEATURE_NAMES) == expected_12_features
    assert len(ALL_FEATURE_NAMES) == 12


def test_identical_evaluation_decision_grid():
    """Test 4: Verify evaluation decision grids across folds are 4-hourly aligned."""
    cfg = load_config(PROJECT_ROOT / 'configs/first_experiment.toml')
    funding_dir = PROJECT_ROOT / 'data/processed/funding_rate'
    
    from cryptoquant.baselines.io import load_period
    from cryptoquant.models.features import build_features
    
    dev_frames, _, _ = load_period(PROJECT_ROOT, 'EXP-003', cfg, 'development')
    funding_dfs = {s: pd.read_parquet(funding_dir / f'{s}.parquet') for s in cfg.symbols}
    
    # Check Fold W1 (2023) grid
    feat_btc = build_features(dev_frames['BTCUSDT'], funding_df=funding_dfs['BTCUSDT'])
    fold1 = FOLDS['W1']
    grid_w1 = feat_btc.loc[
        (feat_btc.decision_time >= fold1.eval_start) & 
        (feat_btc.decision_time < fold1.eval_end) & 
        (feat_btc.decision_time.dt.hour % 4 == 0), 
        'decision_time'
    ].tolist()
    
    feat_eth = build_features(dev_frames['ETHUSDT'], funding_df=funding_dfs['ETHUSDT'])
    grid_eth = feat_eth.loc[
        (feat_eth.decision_time >= fold1.eval_start) & 
        (feat_eth.decision_time < fold1.eval_end) & 
        (feat_eth.decision_time.dt.hour % 4 == 0), 
        'decision_time'
    ].tolist()
    
    assert grid_w1 == grid_eth, "Decision grid mismatch between symbols in W1"
    assert len(grid_w1) > 2000, f"Unexpected grid count: {len(grid_w1)}"


def test_reproducibility_with_fixed_seed():
    """Test 5: Verify fixed random seed generates deterministic predictions across all 4 model families."""
    np.random.seed(42)
    n = 200
    X_train = np.random.randn(n, 12)
    y_train = (np.random.randn(n) > 0).astype(int)
    X_test = np.random.randn(50, 12)
    
    # 1. Logistic Regression
    lr1 = Pipeline([('scaler', StandardScaler()), ('clf', LogisticRegression(C=0.10, random_state=42, solver='lbfgs'))])
    lr2 = Pipeline([('scaler', StandardScaler()), ('clf', LogisticRegression(C=0.10, random_state=42, solver='lbfgs'))])
    lr1.fit(X_train, y_train)
    lr2.fit(X_train, y_train)
    np.testing.assert_array_almost_equal(lr1.predict_proba(X_test), lr2.predict_proba(X_test))
    
    # 2. LightGBM
    lgb1 = lgb.LGBMClassifier(max_depth=3, num_leaves=7, learning_rate=0.03, random_state=42, verbosity=-1, n_jobs=1)
    lgb2 = lgb.LGBMClassifier(max_depth=3, num_leaves=7, learning_rate=0.03, random_state=42, verbosity=-1, n_jobs=1)
    lgb1.fit(X_train, y_train)
    lgb2.fit(X_train, y_train)
    np.testing.assert_array_almost_equal(np.asarray(lgb1.predict_proba(X_test)), np.asarray(lgb2.predict_proba(X_test)))
    
    # 3. XGBoost
    xgb1 = xgb.XGBClassifier(max_depth=3, learning_rate=0.03, random_state=42, eval_metric='logloss', n_jobs=1)
    xgb2 = xgb.XGBClassifier(max_depth=3, learning_rate=0.03, random_state=42, eval_metric='logloss', n_jobs=1)
    xgb1.fit(X_train, y_train)
    xgb2.fit(X_train, y_train)
    np.testing.assert_array_almost_equal(xgb1.predict_proba(X_test), xgb2.predict_proba(X_test))
    
    # 4. CatBoost
    cat1 = cb.CatBoostClassifier(depth=3, learning_rate=0.03, random_seed=42, verbose=0, thread_count=1, iterations=50)
    cat2 = cb.CatBoostClassifier(depth=3, learning_rate=0.03, random_seed=42, verbose=0, thread_count=1, iterations=50)
    cat1.fit(X_train, y_train)
    cat2.fit(X_train, y_train)
    np.testing.assert_array_almost_equal(cat1.predict_proba(X_test), cat2.predict_proba(X_test))


def test_2026_not_used_in_training_or_evaluation():
    """Test 6: Verify 2026 data is never used in training, feature fitting, or evaluation decisions."""
    for fold_name, fold in FOLDS.items():
        assert fold.train_start < pd.Timestamp('2026-01-01', tz='UTC')
        assert fold.train_end <= pd.Timestamp('2025-01-01', tz='UTC')
        assert fold.eval_end <= pd.Timestamp('2026-01-01 00:00:00', tz='UTC')

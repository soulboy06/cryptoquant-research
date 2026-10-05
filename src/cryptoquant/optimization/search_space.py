"""Search space definitions for models, thresholds, and position sizing."""
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class ModelCandidate:
    name: str
    family: str  # 'logistic_regression' or 'lightgbm'
    params: dict[str, Any]


@dataclass(frozen=True)
class SizingScheme:
    name: str
    favorable_weight: Decimal
    weak_alpha_weight: Decimal
    weak_ordinary_weight: Decimal


# 1. Model Candidates: Logistic Regression & LightGBM
MODEL_CANDIDATES = [
    # Logistic Regression variants
    ModelCandidate('LR_C0.01', 'logistic_regression', {'C': 0.01}),
    ModelCandidate('LR_C0.05', 'logistic_regression', {'C': 0.05}),
    ModelCandidate('LR_C0.10', 'logistic_regression', {'C': 0.10}),  # Baseline
    ModelCandidate('LR_C0.50', 'logistic_regression', {'C': 0.50}),
    ModelCandidate('LR_C1.00', 'logistic_regression', {'C': 1.00}),
    ModelCandidate('LR_C5.00', 'logistic_regression', {'C': 5.00}),
    ModelCandidate('LR_C10.0', 'logistic_regression', {'C': 10.0}),

    # LightGBM tree variants (controlled complexity)
    ModelCandidate('LGB_shallow', 'lightgbm', {
        'max_depth': 2, 'num_leaves': 4, 'min_child_samples': 80,
        'learning_rate': 0.03, 'n_estimators': 60, 'subsample': 0.8,
        'colsample_bytree': 0.8, 'random_state': 42, 'verbosity': -1, 'n_jobs': 1
    }),
    ModelCandidate('LGB_medium', 'lightgbm', {
        'max_depth': 3, 'num_leaves': 7, 'min_child_samples': 60,
        'learning_rate': 0.03, 'n_estimators': 80, 'subsample': 0.8,
        'colsample_bytree': 0.8, 'random_state': 42, 'verbosity': -1, 'n_jobs': 1
    }),
    ModelCandidate('LGB_deep', 'lightgbm', {
        'max_depth': 4, 'num_leaves': 12, 'min_child_samples': 50,
        'learning_rate': 0.03, 'n_estimators': 100, 'subsample': 0.8,
        'colsample_bytree': 0.8, 'random_state': 42, 'verbosity': -1, 'n_jobs': 1
    }),
    ModelCandidate('LGB_conservative', 'lightgbm', {
        'max_depth': 2, 'num_leaves': 3, 'min_child_samples': 100,
        'learning_rate': 0.02, 'n_estimators': 50, 'subsample': 0.8,
        'colsample_bytree': 0.8, 'random_state': 42, 'verbosity': -1, 'n_jobs': 1
    }),
    ModelCandidate('LGB_fast', 'lightgbm', {
        'max_depth': 3, 'num_leaves': 6, 'min_child_samples': 60,
        'learning_rate': 0.05, 'n_estimators': 60, 'subsample': 0.8,
        'colsample_bytree': 0.8, 'random_state': 42, 'verbosity': -1, 'n_jobs': 1
    }),
]

# 2. Decision Thresholds
THRESHOLDS = [0.48, 0.50, 0.52, 0.54, 0.56, 0.58, 0.60, 0.62]

# 3. Position Sizing Schemes
# Format: SizingScheme(name, favorable_weight, weak_alpha_weight, weak_ordinary_weight)
# Must conform to engine allowed weights: {0, 0.10, 0.15, 0.20, 0.25, 0.30}
SIZING_SCHEMES = [
    # Baseline R6 scheme
    SizingScheme('R6_default', Decimal('0.30'), Decimal('0.25'), Decimal('0.10')),
    # Pure defense: zero exposure on weak ordinary coins
    SizingScheme('pure_defense_25', Decimal('0.30'), Decimal('0.25'), Decimal('0.00')),
    SizingScheme('pure_defense_20', Decimal('0.30'), Decimal('0.20'), Decimal('0.00')),
    SizingScheme('pure_defense_30', Decimal('0.30'), Decimal('0.30'), Decimal('0.00')),
    # Moderate defense: 15% on ordinary
    SizingScheme('moderate_ord15', Decimal('0.30'), Decimal('0.25'), Decimal('0.15')),
    # Equalized alpha: 20% on alpha, 10% on ordinary
    SizingScheme('alpha_equal20', Decimal('0.30'), Decimal('0.20'), Decimal('0.10')),
    # Aggressive alpha: 30% on alpha, 10% on ordinary
    SizingScheme('alpha_high30', Decimal('0.30'), Decimal('0.30'), Decimal('0.10')),
    # Conservative overall: 25% on favorable, 20% on alpha, 0% on ordinary
    SizingScheme('conservative_overall', Decimal('0.25'), Decimal('0.20'), Decimal('0.00')),
]


# 4. Continuous Net Return Regression Model Candidates (Phase 1)
@dataclass(frozen=True)
class RegressionModelCandidate:
    name: str
    family: str  # 'ridge', 'elastic_net', 'lightgbm_regressor'
    params: dict[str, Any]


REGRESSION_MODELS = [
    # Ridge regression variants (L2 regularization)
    RegressionModelCandidate('Ridge_a1.0', 'ridge', {'alpha': 1.0}),
    RegressionModelCandidate('Ridge_a10.0', 'ridge', {'alpha': 10.0}),
    RegressionModelCandidate('Ridge_a100.0', 'ridge', {'alpha': 100.0}),
    # ElasticNet variants (L1 + L2 regularization)
    RegressionModelCandidate('ElasticNet_a0.001', 'elastic_net', {'alpha': 0.001, 'l1_ratio': 0.5, 'max_iter': 2000, 'random_state': 42}),
    # LightGBM Regressor variants (controlled depth tree regression)
    RegressionModelCandidate('LGB_Reg_shallow', 'lightgbm_regressor', {
        'max_depth': 2, 'num_leaves': 4, 'min_child_samples': 80,
        'learning_rate': 0.03, 'n_estimators': 60, 'subsample': 0.8,
        'colsample_bytree': 0.8, 'random_state': 42, 'verbosity': -1, 'n_jobs': 1
    }),
    RegressionModelCandidate('LGB_Reg_conservative', 'lightgbm_regressor', {
        'max_depth': 2, 'num_leaves': 3, 'min_child_samples': 100,
        'learning_rate': 0.02, 'n_estimators': 50, 'subsample': 0.8,
        'colsample_bytree': 0.8, 'random_state': 42, 'verbosity': -1, 'n_jobs': 1
    }),
]

# 5. Regression Decision Margins (Hurdles on expected net return)
# 0.000 = 0.0% expected net return, 0.001 = +0.1%, 0.002 = +0.2%
REGRESSION_MARGINS = [0.000, 0.001, 0.002]


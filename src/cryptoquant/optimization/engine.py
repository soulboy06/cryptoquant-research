"""Optimization execution engine: model fitting, target building, and portfolio backtest."""
from decimal import Decimal
import warnings

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from cryptoquant.baselines.engine import run_backtest
from cryptoquant.baselines.reporting import summarize
from cryptoquant.models.features import ALL_FEATURE_NAMES
from cryptoquant.models.regime_reporting import combined_weekly
from cryptoquant.models.research_reporting import compute_weekly_statistics
from cryptoquant.optimization.search_space import (
    ModelCandidate,
    RegressionModelCandidate,
    SizingScheme,
)
from cryptoquant.optimization.walk_forward import WalkForwardFold


def fit_and_predict_fold(
    fold: WalkForwardFold,
    model_candidate: ModelCandidate,
    train_samples: dict[str, pd.DataFrame],
    eval_features: dict[str, pd.DataFrame],
    symbols: tuple[str, ...],
) -> pd.DataFrame:
    """Train models on the fold training slice and predict probabilities on evaluation features."""
    feature_cols = ALL_FEATURE_NAMES
    records = []
    
    for s in symbols:
        train_df = train_samples[s]
        X_train = train_df.loc[:, feature_cols].astype('float64')
        y_train = train_df['label'].astype('int64')
        
        eval_df = eval_features[s]
        ready = eval_df['feature_valid'].astype(bool) if 'feature_valid' in eval_df else pd.Series(True, index=eval_df.index)
        probs_series = pd.Series(np.nan, index=eval_df.index, dtype='float64')
        
        if ready.any():
            X_eval_ready = eval_df.loc[ready, feature_cols].astype('float64')
            if model_candidate.family == 'logistic_regression':
                model = Pipeline([
                    ('scaler', StandardScaler()),
                    ('classifier', LogisticRegression(
                        C=model_candidate.params['C'],
                        l1_ratio=0.0,
                        solver='lbfgs',
                        max_iter=1000,
                        random_state=42,
                        tol=1e-4,
                    )),
                ])
                with warnings.catch_warnings(), threadpool_limits(limits=1):
                    warnings.simplefilter('ignore', ConvergenceWarning)
                    model.fit(X_train, y_train)
                    probs_series.loc[ready] = model.predict_proba(X_eval_ready)[:, 1]
                    
            elif model_candidate.family == 'lightgbm':
                from lightgbm import LGBMClassifier
                model = LGBMClassifier(**model_candidate.params)
                with threadpool_limits(limits=1):
                    model.fit(X_train, y_train)
                    probs_series.loc[ready] = model.predict_proba(X_eval_ready)[:, 1]
            else:
                raise ValueError(f"Unknown model family: {model_candidate.family}")
                
        for t, p in zip(eval_df['decision_time'], probs_series):
            records.append({'symbol': s, 'decision_time': t, 'probability': float(p) if pd.notna(p) else np.nan})
            
    df_probs = pd.DataFrame(records)
    return df_probs.sort_values(['decision_time', 'symbol']).reset_index(drop=True)


def build_candidate_targets(
    probabilities: pd.DataFrame,
    regime_states: pd.DataFrame,
    momentum: pd.DataFrame,
    sizing: SizingScheme,
    threshold: float,
    symbols: tuple[str, ...],
) -> pd.DataFrame:
    """Build exact 4-column decision targets dataframe for engine consumption."""
    state_map = regime_states.set_index('decision_time')
    mom_map = momentum.set_index(['decision_time', 'symbol'])
    
    records = []
    for time, group in probabilities.groupby('decision_time', sort=True):
        state = state_map.loc[time]
        favorable = bool(state.state_valid and state.allow_buy)
        full_history = bool(state.state_valid and all(mom_map.loc[(time, s)].history_valid for s in symbols))
        btc_mom = float(mom_map.loc[(time, 'BTCUSDT')].return_72h)
        
        for row in group.itertuples(index=False):
            sym = row.symbol
            prob = row.probability
            
            sym_mom = float(mom_map.loc[(time, sym)].return_72h)
            is_alpha_leader = full_history and sym_mom > 0 and sym_mom > btc_mom
            
            if pd.isna(prob):
                target_w = None
            elif prob < threshold:
                target_w = Decimal('0')
            elif favorable:
                target_w = sizing.favorable_weight
            else:
                target_w = sizing.weak_alpha_weight if is_alpha_leader else sizing.weak_ordinary_weight
                
            records.append({
                'symbol': sym,
                'decision_time': time,
                'probability': prob,
                'target_weight': target_w,
            })
            
    return pd.DataFrame(records, columns=['symbol', 'decision_time', 'probability', 'target_weight'])


def evaluate_window_simulation(
    view,
    rules,
    cfg,
    targets,
    window,
    period,
    cost='base',
    *,
    max_holding_hours: int | None = None,
    breakeven_activation: Decimal | None = Decimal('0.0120'),
    breakeven_ratio: Decimal | None = Decimal('0.0025'),
    exit_variant: str | None = None,
):
    """Simulate a single window backtest and return structured results."""
    if max_holding_hours is not None:
        result = run_backtest(
            view, rules, cfg, 'logistic_regression', cost, period,
            decision_targets=targets, window=window, exit_variant=None,
            max_holding_hours=max_holding_hours,
            breakeven_activation=breakeven_activation,
            breakeven_ratio=breakeven_ratio,
            dust_policy='retain_mark_to_market',
        )
    else:
        var = exit_variant if exit_variant is not None else 'C2'
        result = run_backtest(
            view, rules, cfg, 'logistic_regression', cost, period,
            decision_targets=targets, window=window, exit_variant=var,
            dust_policy='retain_mark_to_market',
        )
    summary, _ = summarize(result, cfg)
    weekly = compute_weekly_statistics(result.equity, summary['start_utc'], summary['end_utc'])
    summary.update({k: v for k, v in weekly.items() if k != 'weekly_records'})
    summary['status'] = 'complete'

    # Compute cycle durations from fills
    durations = []
    open_times = {}
    for fill in result.fills:
        s = fill['symbol']
        if fill['side'] == 'BUY':
            if s not in open_times:
                open_times[s] = fill['time']
        elif fill['side'] == 'SELL':
            if s in open_times:
                durations.append((fill['time'] - open_times[s]).total_seconds() / 3600.0)
                del open_times[s]
    summary['avg_holding_hours'] = float(sum(durations) / len(durations)) if durations else 0.0
    summary['holding_durations'] = durations
    return summary


def calculate_fitness_score(
    g_week: float | None,
    worst_mdd: float,
    ret_2025: float,
    min_cycles: int,
    floor_triggers: int,
) -> float:
    """Calculate composite multi-objective fitness score."""
    g_pct = float(g_week) * 100 if g_week is not None else -999.0
    dd_penalty = max(0.0, worst_mdd - 0.05) * 50.0  # steep penalty if MDD > 5%
    ret25_penalty = max(0.0, -ret_2025) * 50.0       # penalty for losing money in 2025
    cycle_penalty = 10.0 if min_cycles < 30 else 0.0
    floor_penalty = 100.0 if floor_triggers > 0 else 0.0
    return g_pct - dd_penalty - ret25_penalty - cycle_penalty - floor_penalty


def evaluate_candidate_walk_forward(
    candidate_id: str,
    model_name: str,
    threshold: float,
    sizing_name: str,
    sizing: SizingScheme,
    fold_probs: dict[str, pd.DataFrame],
    fold_eval_data: dict[str, dict],
    cfg,
    *,
    max_holding_hours: int | None = None,
) -> dict:
    """Run full walk-forward evaluation across all 3 folds for a candidate parameter set."""
    window_results = {}
    
    for fold_name in ('W1', 'W2', 'R2025'):
        eval_data = fold_eval_data[fold_name]
        probs = fold_probs[fold_name]
        
        targets = build_candidate_targets(
            probs,
            eval_data['regime_states'],
            eval_data['momentum'],
            sizing,
            threshold,
            cfg.symbols,
        )
        
        period = 'validation' if fold_name == 'R2025' else 'development'
        summary = evaluate_window_simulation(
            eval_data['view'],
            eval_data['rules'],
            cfg,
            targets,
            fold_name,
            period,
            cost='base',
            max_holding_hours=max_holding_hours,
        )
        window_results[fold_name] = summary
        
    # Aggregate cross-window metrics
    g_week = combined_weekly(window_results)
    
    ret_w1 = float(window_results['W1']['net_return'])
    ret_w2 = float(window_results['W2']['net_return'])
    ret_25 = float(window_results['R2025']['net_return'])
    
    mdd_w1 = float(window_results['W1']['max_drawdown'])
    mdd_w2 = float(window_results['W2']['max_drawdown'])
    mdd_25 = float(window_results['R2025']['max_drawdown'])
    worst_mdd = max(mdd_w1, mdd_w2, mdd_25)
    
    cyc_w1 = window_results['W1']['closed_cycles']
    cyc_w2 = window_results['W2']['closed_cycles']
    cyc_25 = window_results['R2025']['closed_cycles']
    min_cycles = min(cyc_w1, cyc_w2, cyc_25)
    tot_cycles = cyc_w1 + cyc_w2 + cyc_25
    
    floor_hits = sum(w['floor_triggers'] for w in window_results.values())
    total_fees = float(sum(w['fees_usdt'] for w in window_results.values()))
    total_turnover = float(sum(w['turnover_usdt'] for w in window_results.values()))
    
    all_durations = []
    for w in window_results.values():
        all_durations.extend(w.get('holding_durations', []))
    avg_holding = float(sum(all_durations) / len(all_durations)) if all_durations else 0.0
    
    fitness = calculate_fitness_score(
        g_week=float(g_week) if g_week is not None else None,
        worst_mdd=worst_mdd,
        ret_2025=ret_25,
        min_cycles=min_cycles,
        floor_triggers=floor_hits,
    )
    
    return {
        'candidate_id': candidate_id,
        'model_name': model_name,
        'threshold': threshold,
        'sizing_name': sizing_name,
        'max_holding_hours': max_holding_hours,
        'favorable_weight': float(sizing.favorable_weight),
        'weak_alpha_weight': float(sizing.weak_alpha_weight),
        'weak_ordinary_weight': float(sizing.weak_ordinary_weight),
        'g_week': float(g_week) if g_week is not None else None,
        'fitness': fitness,
        'ret_w1': ret_w1,
        'ret_w2': ret_w2,
        'ret_2025': ret_25,
        'mdd_w1': mdd_w1,
        'mdd_w2': mdd_w2,
        'mdd_2025': mdd_25,
        'worst_mdd': worst_mdd,
        'cyc_w1': cyc_w1,
        'cyc_w2': cyc_w2,
        'cyc_2025': cyc_25,
        'total_cycles': tot_cycles,
        'min_cycles': min_cycles,
        'total_fees_usdt': total_fees,
        'total_turnover_usdt': total_turnover,
        'avg_holding_hours': avg_holding,
        'floor_triggers': floor_hits,
        'window_results': window_results,
    }


def fit_and_predict_regression_fold(
    fold: WalkForwardFold,
    model_candidate: RegressionModelCandidate,
    train_samples: dict[str, pd.DataFrame],
    eval_features: dict[str, pd.DataFrame],
    symbols: tuple[str, ...],
) -> pd.DataFrame:
    """Train continuous regression model on fold training slice and predict expected net returns."""
    feature_cols = ALL_FEATURE_NAMES
    records = []
    
    for s in symbols:
        train_df = train_samples[s]
        X_train = train_df.loc[:, feature_cols].astype('float64')
        y_train = train_df['label_net_return_text'].astype('float64')
        
        eval_df = eval_features[s]
        ready = eval_df['feature_valid'].astype(bool) if 'feature_valid' in eval_df else pd.Series(True, index=eval_df.index)
        preds_series = pd.Series(np.nan, index=eval_df.index, dtype='float64')
        
        if bool(ready.any()):
            X_eval_ready = eval_df.loc[ready, feature_cols].astype('float64')
            if model_candidate.family == 'ridge':
                from sklearn.linear_model import Ridge
                model = Pipeline([
                    ('scaler', StandardScaler()),
                    ('regressor', Ridge(**model_candidate.params)),
                ])
                with threadpool_limits(limits=1):
                    model.fit(X_train, y_train)
                    preds_series.loc[ready] = model.predict(X_eval_ready)
            elif model_candidate.family == 'elastic_net':
                from sklearn.linear_model import ElasticNet
                model = Pipeline([
                    ('scaler', StandardScaler()),
                    ('regressor', ElasticNet(**model_candidate.params)),
                ])
                with threadpool_limits(limits=1):
                    model.fit(X_train, y_train)
                    preds_series.loc[ready] = model.predict(X_eval_ready)
            elif model_candidate.family == 'lightgbm_regressor':
                from lightgbm import LGBMRegressor
                model = LGBMRegressor(**model_candidate.params)
                with threadpool_limits(limits=1):
                    model.fit(X_train, y_train)
                    preds_series.loc[ready] = model.predict(X_eval_ready)
            else:
                raise ValueError(f"Unknown regression family: {model_candidate.family}")
                
        for t, p in zip(eval_df['decision_time'], preds_series):
            records.append({
                'symbol': s,
                'decision_time': t,
                'expected_net_return': float(p) if pd.notna(p) else np.nan,
            })
            
    df_preds = pd.DataFrame(records)
    return df_preds.sort_values(['decision_time', 'symbol']).reset_index(drop=True)


def build_candidate_regression_targets(
    predictions: pd.DataFrame,
    regime_states: pd.DataFrame,
    momentum: pd.DataFrame,
    sizing: SizingScheme,
    margin: float,
    symbols: tuple[str, ...],
) -> pd.DataFrame:
    """Build exact 4-column decision targets from continuous net return regression predictions."""
    state_map = regime_states.set_index('decision_time')
    mom_map = momentum.set_index(['decision_time', 'symbol'])
    
    records = []
    for time, group in predictions.groupby('decision_time', sort=True):
        state = state_map.loc[time]
        favorable = bool(state.state_valid and state.allow_buy)
        full_history = bool(state.state_valid and all(mom_map.loc[(time, s)].history_valid for s in symbols))
        btc_mom = float(mom_map.loc[(time, 'BTCUSDT')].return_72h)
        
        for row in group.itertuples(index=False):
            sym = row.symbol
            exp_ret = row.expected_net_return
            
            sym_mom = float(mom_map.loc[(time, sym)].return_72h)
            is_alpha_leader = full_history and sym_mom > 0 and sym_mom > btc_mom
            
            if pd.isna(exp_ret):
                target_w = None
                prob_val = np.nan
            else:
                # Continuous monotonic mapping into (0, 1) for engine interface:
                # exp_ret = 0.0 -> 0.50; exp_ret > 0 -> > 0.50
                prob_val = float(1.0 / (1.0 + np.exp(-np.clip(exp_ret * 100.0, -10.0, 10.0))))
                if exp_ret < margin:
                    target_w = Decimal('0')
                elif favorable:
                    target_w = sizing.favorable_weight
                else:
                    target_w = sizing.weak_alpha_weight if is_alpha_leader else sizing.weak_ordinary_weight
                    
            records.append({
                'symbol': sym,
                'decision_time': time,
                'probability': prob_val,
                'target_weight': target_w,
            })
            
    return pd.DataFrame(records, columns=['symbol', 'decision_time', 'probability', 'target_weight'])


def evaluate_candidate_regression_walk_forward(
    candidate_id: str,
    model_name: str,
    margin: float,
    sizing_name: str,
    sizing: SizingScheme,
    fold_preds: dict[str, pd.DataFrame],
    fold_eval_data: dict[str, dict],
    cfg,
) -> dict:
    """Run full walk-forward evaluation across all 3 folds for a regression candidate parameter set."""
    window_results = {}
    
    for fold_name in ('W1', 'W2', 'R2025'):
        eval_data = fold_eval_data[fold_name]
        preds = fold_preds[fold_name]
        
        targets = build_candidate_regression_targets(
            preds,
            eval_data['regime_states'],
            eval_data['momentum'],
            sizing,
            margin,
            cfg.symbols,
        )
        
        period = 'validation' if fold_name == 'R2025' else 'development'
        summary = evaluate_window_simulation(
            eval_data['view'],
            eval_data['rules'],
            cfg,
            targets,
            fold_name,
            period,
            cost='base',
        )
        window_results[fold_name] = summary
        
    # Aggregate cross-window metrics
    g_week = combined_weekly(window_results)
    
    ret_w1 = float(window_results['W1']['net_return'])
    ret_w2 = float(window_results['W2']['net_return'])
    ret_25 = float(window_results['R2025']['net_return'])
    
    mdd_w1 = float(window_results['W1']['max_drawdown'])
    mdd_w2 = float(window_results['W2']['max_drawdown'])
    mdd_25 = float(window_results['R2025']['max_drawdown'])
    worst_mdd = max(mdd_w1, mdd_w2, mdd_25)
    
    cyc_w1 = window_results['W1']['closed_cycles']
    cyc_w2 = window_results['W2']['closed_cycles']
    cyc_25 = window_results['R2025']['closed_cycles']
    min_cycles = min(cyc_w1, cyc_w2, cyc_25)
    
    floor_hits = sum(w['floor_triggers'] for w in window_results.values())
    
    fitness = calculate_fitness_score(
        g_week=float(g_week) if g_week is not None else None,
        worst_mdd=worst_mdd,
        ret_2025=ret_25,
        min_cycles=min_cycles,
        floor_triggers=floor_hits,
    )
    
    return {
        'candidate_id': candidate_id,
        'model_name': model_name,
        'margin': margin,
        'sizing_name': sizing_name,
        'favorable_weight': float(sizing.favorable_weight),
        'weak_alpha_weight': float(sizing.weak_alpha_weight),
        'weak_ordinary_weight': float(sizing.weak_ordinary_weight),
        'g_week': float(g_week) if g_week is not None else None,
        'fitness': fitness,
        'ret_w1': ret_w1,
        'ret_w2': ret_w2,
        'ret_2025': ret_25,
        'mdd_w1': mdd_w1,
        'mdd_w2': mdd_w2,
        'mdd_2025': mdd_25,
        'worst_mdd': worst_mdd,
        'cyc_w1': cyc_w1,
        'cyc_w2': cyc_w2,
        'cyc_2025': cyc_25,
        'min_cycles': min_cycles,
        'floor_triggers': floor_hits,
        'window_results': window_results,
    }


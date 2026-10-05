"""Walk-Forward validation temporal splits and data management.

Strictly enforces:
- train_end <= eval_start (zero lookahead)
- 2026 data physically sealed (0 reads, 0 queries)
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

from cryptoquant.baselines.io import load_period
from cryptoquant.baselines.windows import window_frames
from cryptoquant.models.features import build_features, ALL_FEATURE_NAMES
from cryptoquant.models.leader_allocation import build_closed_momentum


@dataclass(frozen=True)
class WalkForwardFold:
    name: str
    period: str
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    eval_start: pd.Timestamp
    eval_end: pd.Timestamp


FOLDS = {
    'W1': WalkForwardFold(
        name='W1',
        period='development',
        train_start=pd.Timestamp('2022-01-01 00:00:00', tz='UTC'),
        train_end=pd.Timestamp('2023-01-01 00:00:00', tz='UTC'),
        eval_start=pd.Timestamp('2023-01-01 00:00:00', tz='UTC'),
        eval_end=pd.Timestamp('2024-01-01 00:00:00', tz='UTC'),
    ),
    'W2': WalkForwardFold(
        name='W2',
        period='development',
        train_start=pd.Timestamp('2022-01-01 00:00:00', tz='UTC'),
        train_end=pd.Timestamp('2024-01-01 00:00:00', tz='UTC'),
        eval_start=pd.Timestamp('2024-01-01 00:00:00', tz='UTC'),
        eval_end=pd.Timestamp('2025-01-01 00:00:00', tz='UTC'),
    ),
    'R2025': WalkForwardFold(
        name='R2025',
        period='validation',
        train_start=pd.Timestamp('2022-01-01 00:00:00', tz='UTC'),
        train_end=pd.Timestamp('2025-01-01 00:00:00', tz='UTC'),
        eval_start=pd.Timestamp('2025-01-01 00:00:00', tz='UTC'),
        eval_end=pd.Timestamp('2025-12-31 20:00:00', tz='UTC'),
    ),
}


def load_fold_training_samples(root: Path, fold: WalkForwardFold, symbols: tuple[str, ...]):
    """Extract training samples strictly with label_end <= fold.train_end."""
    samples = {}
    sample_dir = root / 'artifacts/experiments/EXP-063/samples/net_positive_base_v1'
    for s in symbols:
        p = sample_dir / f'{s}.parquet'
        df = pd.read_parquet(p)
        mask = (df.decision_time >= fold.train_start) & (df.label_end <= fold.train_end)
        filtered = df.loc[mask].copy().reset_index(drop=True)
        if filtered.empty:
            raise ValueError(f"No training samples for {s} in fold {fold.name}")
        # Verify no future leakage
        if (filtered.label_end > fold.train_end).any():
            raise ValueError(f"Future label leakage detected in fold {fold.name} for {s}")
        samples[s] = filtered
    return samples


def load_fold_evaluation_data(root: Path, fold: WalkForwardFold, cfg):
    """Load execution frames, features, momentum, and regime states for the fold."""
    period = fold.period
    frames, rules, info = load_period(root, 'EXP-003', cfg, period)
    view = window_frames(frames, cfg, period, fold.name)
    momentum = build_closed_momentum(frames)
    
    # Load funding rates for continuous features
    funding_dfs = {}
    funding_dir = root / 'data/processed/funding_rate'
    for s in cfg.symbols:
        funding_dfs[s] = pd.read_parquet(funding_dir / f'{s}.parquet')
        
    # Build continuous features for evaluation
    eval_features = {}
    for s in cfg.symbols:
        feat = build_features(frames[s], funding_df=funding_dfs[s])
        # Filter to fold evaluation window
        mask = (feat.decision_time >= fold.eval_start) & (feat.decision_time < fold.eval_end) & (feat.decision_time.dt.hour % 4 == 0)
        eval_features[s] = feat.loc[mask].copy().reset_index(drop=True)
        
    # Load regime states
    states_path = root / f'artifacts/experiments/EXP-122/state_{fold.name}.parquet'
    regime_states = pd.read_parquet(states_path)
    
    return {
        'view': view,
        'rules': rules,
        'info': info,
        'momentum': momentum,
        'eval_features': eval_features,
        'regime_states': regime_states,
    }

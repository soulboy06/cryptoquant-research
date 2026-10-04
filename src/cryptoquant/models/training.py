"""固定九特征、训练专用标准化及不重新拟合的逐行预测。"""

import json
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from threadpoolctl import threadpool_limits

from cryptoquant.baselines.io import experiment_id
from cryptoquant.data.archive import sha_file
from cryptoquant.models.features import FEATURE_NAMES, ALL_FEATURE_NAMES, HOUR
from cryptoquant.models.labels import GROSS_POLICY, validate_label_metadata

C_VALUES = (.1, 1., 10.)
THRESHOLDS = (.55, .60, .61, .62, .63, .64, .65)
MODEL_PARAMETERS = dict(l1_ratio=0., solver='lbfgs', max_iter=1000,
                        class_weight=None, random_state=42, tol=1e-4, fit_intercept=True)

LIGHTGBM_CANDIDATE_PARAMS = {
    0.1: dict(max_depth=2, num_leaves=4, min_child_samples=100, n_estimators=60,
              learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, random_state=42, verbosity=-1, n_jobs=1),
    1.0: dict(max_depth=3, num_leaves=7, min_child_samples=80, n_estimators=80,
              learning_rate=0.05, subsample=0.8, colsample_bytree=0.8, random_state=42, verbosity=-1, n_jobs=1),
    10.0: dict(max_depth=4, num_leaves=12, min_child_samples=60, n_estimators=100,
               learning_rate=0.03, subsample=0.8, colsample_bytree=0.8, random_state=42, verbosity=-1, n_jobs=1),
}


def feature_matrix(frame, feature_names=None):
    if feature_names is None:
        feature_names = ALL_FEATURE_NAMES if 'funding_rate_latest' in frame.columns else FEATURE_NAMES
    # Explicit selection excludes future labels and provenance/time metadata.
    if frame.columns.duplicated().any() or not set(feature_names) <= set(frame.columns):
        raise ValueError('missing or duplicate feature columns')
    features = frame.loc[:, feature_names].astype('float64')
    if features.empty or not np.isfinite(features.to_numpy()).all():
        raise ValueError('empty or non-finite features')
    return features


def fit_model(samples, C, feature_names=None, model_family="logistic_regression"):
    if C not in C_VALUES:
        raise ValueError('C outside predefined candidates')
    features = feature_matrix(samples, feature_names=feature_names)
    labels = samples['label']
    if set(labels.unique()) != {0, 1}:
        raise ValueError('training requires both classes 0 and 1')
    if model_family == "logistic_regression":
        model = Pipeline([('scaler', StandardScaler()),
                          ('classifier', LogisticRegression(C=C, **MODEL_PARAMETERS))])
        with warnings.catch_warnings(), threadpool_limits(limits=1):
            warnings.simplefilter('error', ConvergenceWarning)
            model.fit(features, labels.astype('int64'))
        return model
    elif model_family == "lightgbm":
        from lightgbm import LGBMClassifier
        params = LIGHTGBM_CANDIDATE_PARAMS[C]
        model = LGBMClassifier(**params)
        with threadpool_limits(limits=1):
            model.fit(features, labels.astype('int64'))
        return model
    else:
        raise ValueError(f"unsupported model family: {model_family}")


def predict_probabilities(model, frame):
    model_features = list(model.feature_names_in_)
    if model_features not in [FEATURE_NAMES, ALL_FEATURE_NAMES] or list(model.classes_) != [0, 1]:
        raise ValueError('model feature order or classes mismatch')
    with threadpool_limits(limits=1):
        probabilities = model.predict_proba(feature_matrix(frame, feature_names=model_features))[:, 1]
    if not (np.isfinite(probabilities).all() and ((probabilities >= 0) & (probabilities <= 1)).all()):
        raise ValueError('invalid predicted probabilities')
    return probabilities


def load_training_samples(root, sample_id, config):
    folder = (root / 'artifacts/experiments' / experiment_id(sample_id)).resolve()
    path = folder / 'sample_manifest.json'
    manifest = json.loads(path.read_text(encoding='utf-8'))
    label_card = validate_label_metadata(manifest, expected_policy=GROSS_POLICY)
    expected_features = ALL_FEATURE_NAMES if config.feature_policy == 'kline_and_funding' else FEATURE_NAMES
    if not (manifest.get('status') == 'complete' and manifest.get('type') == 'training_samples'
            and manifest.get('experiment_id') == sample_id and manifest.get('period') == 'development'
            and manifest.get('feature_names') == expected_features
            and pd.Timestamp(manifest['start_utc']) == config.development_start
            and pd.Timestamp(manifest['label_end_before_utc']) == config.development_end
            and set(manifest['symbols']) == set(config.symbols)):
        raise ValueError('training sample manifest does not match approved development config')
    frames, inputs = {}, {}
    for symbol in config.symbols:
        item = manifest['symbols'][symbol]
        sample_path = folder / 'training_samples' / (symbol + '.parquet')
        if sample_path.resolve() != sample_path or sample_path.resolve() != Path(item['samples_path']).resolve():
            raise ValueError('training samples path mismatch or symlink')
        if sha_file(sample_path) != item['samples_sha256']:
            raise ValueError(f'training sample SHA mismatch: {symbol}')
        frame = pd.read_parquet(sample_path)
        feature_matrix(frame, feature_names=expected_features)
        times = ['decision_time', 'feature_open_time', 'feature_available_time', 'label_start', 'label_end']
        if any(str(frame[name].dt.tz) != 'UTC' or frame[name].isna().any() for name in times):
            raise ValueError('sample times must be non-null UTC')
        decision = frame.decision_time
        if not (len(frame) == item['samples'] and (frame.symbol == symbol).all()
                and decision.is_monotonic_increasing and decision.is_unique
                and (decision == decision.dt.floor('4h')).all()
                and (decision >= config.development_start).all() and (decision < config.development_end).all()
                and (frame.label_start == decision).all() and (frame.label_end == decision + 4 * HOUR).all()
                and (frame.label_end < config.development_end).all()
                and (frame.feature_open_time + HOUR == decision).all()
                and (frame.feature_available_time <= decision).all()
                and (frame.history_count >= 744).all()
                and set(frame.label.unique()) == {0, 1}
                and int(frame.label.sum()) == item['label_1']
                and int((frame.label == 0).sum()) == item['label_0']):
            raise ValueError(f'invalid training counts, labels or time boundary: {symbol}; requires both classes')
        frames[symbol] = frame
        inputs[symbol] = dict(path=str(sample_path), sha256=item['samples_sha256'], samples=len(frame),
                              label_1=item['label_1'], label_0=item['label_0'],
                              first_decision_utc=decision.min(), last_decision_utc=decision.max(),
                              last_label_end_utc=frame.label_end.max())
    provenance = dict(sample_experiment_id=sample_id, sample_manifest_path=str(path),
                      sample_manifest_sha256=sha_file(path), sample_source_hash=manifest['source_hash'], inputs=inputs)
    provenance.update(label_card)
    return frames, provenance

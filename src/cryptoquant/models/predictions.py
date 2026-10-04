"""冻结模型只预测已可获得历史，事后标签单独用于诊断。"""

import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score

from cryptoquant.baselines.io import experiment_id
from cryptoquant.data.archive import sha_file
from cryptoquant.data.calendar import can_execute
from cryptoquant.data.workflow import environment
from cryptoquant.models.features import FEATURE_NAMES, ALL_FEATURE_NAMES, HOUR, build_features
from cryptoquant.models.training import C_VALUES, THRESHOLDS, MODEL_PARAMETERS, LIGHTGBM_CANDIDATE_PARAMS, predict_probabilities
from cryptoquant.models.labels import GROSS_POLICY, NET_POLICY, label_values, label_metadata, validate_label_metadata


def load_frozen_models(root, training_id, config):
    folder = (root / 'artifacts/experiments' / experiment_id(training_id)).resolve()
    path = folder / 'train_manifest.json'
    manifest = json.loads(path.read_text('utf-8'))
    label_card = validate_label_metadata(manifest, expected_policy=GROSS_POLICY)
    expected_features = ALL_FEATURE_NAMES if config.feature_policy == 'kline_and_funding' else FEATURE_NAMES
    if not (manifest.get('status') == 'complete' and manifest.get('type') == 'model_training'
            and manifest.get('experiment_id') == training_id and manifest.get('period') == 'development'
            and manifest.get('config_hash') == config.config_hash and manifest.get('feature_names') == expected_features
            and pd.Timestamp(manifest['start_utc']) == config.development_start
            and pd.Timestamp(manifest['label_end_before_utc']) == config.development_end
            and config.development_end <= config.validation_start):
        raise ValueError('frozen training manifest mismatch')
    model_family = manifest.get('model_family', 'logistic_regression')
    if model_family != config.model_family:
        raise ValueError('frozen model family does not match config')
    current = environment()
    pkg_list = ['numpy', 'scipy', 'scikit-learn', 'joblib', 'pandas']
    if model_family == 'lightgbm':
        pkg_list.append('lightgbm')
    for name in pkg_list:
        if manifest['environment']['packages'].get(name) != current['packages'].get(name):
            raise ValueError('frozen model dependency mismatch: ' + name)
    if manifest['environment']['python'] != current['python']:
        raise ValueError('frozen model Python version mismatch')
    expected = {(s, C) for C in C_VALUES for s in config.symbols}
    if len(manifest['models']) != len(expected) or {(x['symbol'], x['C']) for x in manifest['models']} != expected:
        raise ValueError('missing or duplicate predefined models')
    models, provenance = {C: {} for C in C_VALUES}, {C: [] for C in C_VALUES}
    for item in manifest['models']:
        model_path = (folder / item['model_path']).resolve()
        if item.get('status') != 'complete' or not item.get('reload_verified') or not model_path.is_relative_to(folder / 'models') or sha_file(model_path) != item['model_sha256']:
            raise ValueError('frozen model path, status or SHA mismatch')
        model = joblib.load(model_path)
        if model_family == 'logistic_regression':
            classifier, scaler = model.named_steps['classifier'], model.named_steps['scaler']
            if list(model.feature_names_in_) != expected_features or list(model.classes_) != [0, 1] or int(scaler.n_samples_seen_) != item['samples']:
                raise ValueError('frozen model feature order, classes or sample count mismatch')
            if any(classifier.get_params()[key] != value for key, value in MODEL_PARAMETERS.items()) or classifier.C != item['C']:
                raise ValueError('frozen model parameters mismatch')
        elif model_family == 'lightgbm':
            if list(model.feature_names_in_) != expected_features or list(model.classes_) != [0, 1]:
                raise ValueError('frozen model feature order or classes mismatch')
            expected_params = LIGHTGBM_CANDIDATE_PARAMS[item['C']]
            actual_params = model.get_params()
            if any(actual_params.get(k) != v for k, v in expected_params.items()):
                raise ValueError('frozen lightgbm model parameters mismatch')
        models[item['C']][item['symbol']] = model
        provenance[item['C']].append(dict(symbol=item['symbol'], C=item['C'], path=str(model_path), sha256=item['model_sha256']))
    return models, dict(training_experiment_id=training_id, training_manifest_sha256=sha_file(path),
                        training_source_hash=manifest['source_hash'], label_end_before_utc=manifest['label_end_before_utc'], models=provenance,
                        **label_card)


def build_probabilities(frames, models, start, end, funding_dfs=None):
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    records = []
    if set(models) != set(frames):
        raise ValueError('model symbol mismatch')
    for symbol in sorted(frames):
        funding_df = funding_dfs.get(symbol) if funding_dfs else None
        features = build_features(frames[symbol], funding_df=funding_df)
        selected = features[(features.decision_time >= start) & (features.decision_time < end) &
                            (features.decision_time.dt.hour % 4 == 0)]
        probabilities = pd.Series(np.nan, index=selected.index, dtype='float64')
        ready = selected.feature_valid
        if ready.any():
            probabilities.loc[ready] = predict_probabilities(models[symbol], selected.loc[ready])
        records.extend(dict(symbol=symbol, decision_time=selected.loc[index, 'decision_time'], probability=p)
                       for index, p in probabilities.items())
    return pd.DataFrame(records, columns=['symbol', 'decision_time', 'probability']).sort_values(['decision_time', 'symbol']).reset_index(drop=True)


def build_window_probabilities(feature_frames, models, config, period, *, window):
    """从已核验连续历史特征预测固定窗口；无效特征保留NaN概率。"""
    from cryptoquant.baselines.windows import select_window_features
    if set(models) != set(config.symbols):
        raise ValueError('model symbol mismatch')
    selected_frames = select_window_features(feature_frames, config, period, window)
    feature_names = ALL_FEATURE_NAMES if config.feature_policy == 'kline_and_funding' else FEATURE_NAMES
    records = []
    for symbol in sorted(selected_frames):
        model = models[symbol]
        if list(model.feature_names_in_) != feature_names:
            raise ValueError('window model feature order or policy mismatch')
        selected = selected_frames[symbol]
        if not set(feature_names) <= set(selected):
            raise ValueError('missing window feature columns')
        selected = selected.loc[selected.decision_time.dt.hour % 4 == 0]
        probabilities = pd.Series(np.nan, index=selected.index, dtype='float64')
        ready = selected.feature_valid
        if ready.any():
            probabilities.loc[ready] = predict_probabilities(model, selected.loc[ready, feature_names])
        records.extend(dict(symbol=symbol, decision_time=selected.loc[index, 'decision_time'], probability=p)
                       for index, p in probabilities.items())
    return pd.DataFrame(records, columns=['symbol', 'decision_time', 'probability']).sort_values(['decision_time', 'symbol']).reset_index(drop=True)


def decision_targets(probabilities, threshold, weight):
    if threshold not in THRESHOLDS or list(probabilities.columns) != ['symbol', 'decision_time', 'probability']:
        raise ValueError('invalid threshold or probability columns')
    output = probabilities.copy()
    output['target_weight'] = [None if pd.isna(p) else weight if p >= threshold else weight * 0
                               for p in output.probability]
    return output


def evaluation_labels(frames, probabilities, end, *, policy=GROSS_POLICY, fee=None, adverse=None):
    label_metadata(policy, fee, adverse)
    end = pd.Timestamp(end)
    quotes = {s: {r['open_time']: r for r in frame.to_dict('records')} for s, frame in frames.items()}
    rows = []
    for row in probabilities.to_dict('records'):
        entry, symbol = row['decision_time'], row['symbol']
        exit_time = entry + 4 * HOUR
        if pd.isna(row['probability']) or exit_time > end:
            continue
        window = [quotes[symbol].get(entry + n * HOUR) for n in range(5)]
        if not all(quote is not None and can_execute(quote) for quote in window):
            continue
        values = label_values(window[0]['open'], window[-1]['open'], policy, fee, adverse)
        rows.append(row | dict(label_start=entry, label_end=exit_time, **values))
    columns = ['symbol', 'decision_time', 'probability', 'label_start', 'label_end', 'label_return', 'label']
    if policy == NET_POLICY:
        columns.append('label_net_return_text')
    return pd.DataFrame(rows, columns=columns)


def prediction_diagnostics(labels, symbols, threshold):
    diagnostics = {}
    for symbol in symbols:
        frame = labels[labels.symbol == symbol]
        item = dict(samples=len(frame), label_1=int(frame.label.sum()), label_0=int((frame.label == 0).sum()),
                    accuracy=None, threshold_accuracy=None, roc_auc=None, brier=None)
        if len(frame):
            item.update(accuracy=float(accuracy_score(frame.label, frame.probability >= .5)),
                        threshold_accuracy=float(accuracy_score(frame.label, frame.probability >= threshold)),
                        brier=float(brier_score_loss(frame.label, frame.probability)),
                        last_label_end_utc=frame.label_end.max())
            if frame.label.nunique() == 2:
                item['roc_auc'] = float(roc_auc_score(frame.label, frame.probability))
            else:
                item['roc_auc_unavailable_reason'] = 'single class in evaluation answers'
        diagnostics[symbol] = item
    return diagnostics

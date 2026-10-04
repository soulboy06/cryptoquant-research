"""测试LightGBM树模型拟合、重载一致性与参数边界。"""

import joblib
import numpy as np
import pandas as pd
import pytest

from cryptoquant.models.features import ALL_FEATURE_NAMES, HOUR
from cryptoquant.models.training import (
    C_VALUES,
    LIGHTGBM_CANDIDATE_PARAMS,
    fit_model,
    predict_probabilities,
)


def sample_12_features(n=120):
    rng = np.random.default_rng(42)
    frame = pd.DataFrame(rng.normal(size=(n, 12)), columns=ALL_FEATURE_NAMES)
    frame['label'] = (frame.return_1h + rng.normal(size=n) > 0).astype('int64')
    frame['symbol'] = 'BTCUSDT'
    frame['decision_time'] = pd.date_range('2022-01-01', periods=n, freq='4h', tz='UTC')
    frame['feature_open_time'] = frame.decision_time - HOUR
    frame['feature_available_time'] = frame.decision_time
    frame['source_id'] = 'synthetic-test'
    frame['history_count'] = 744
    frame['label_start'] = frame.decision_time
    frame['label_end'] = frame.decision_time + 4 * HOUR
    frame['label_return'] = np.where(frame.label == 1, 0.01, -0.01)
    return frame


def test_lightgbm_fit_reload_consistency():
    frame = sample_12_features()
    model = fit_model(frame, 1.0, feature_names=ALL_FEATURE_NAMES, model_family="lightgbm")
    
    assert list(model.classes_) == [0, 1]
    assert list(model.feature_names_in_) == ALL_FEATURE_NAMES
    assert len(model.feature_importances_) == 12
    
    proba = predict_probabilities(model, frame)
    assert len(proba) == len(frame)
    assert (proba >= 0.0).all() and (proba <= 1.0).all()
    assert np.isfinite(proba).all()
    
    # Reload verification
    import io
    buf = io.BytesIO()
    joblib.dump(model, buf)
    buf.seek(0)
    reloaded = joblib.load(buf)
    proba_reloaded = predict_probabilities(reloaded, frame)
    np.testing.assert_array_equal(proba, proba_reloaded)


def test_lightgbm_candidates_grid():
    frame = sample_12_features()
    for C in C_VALUES:
        model = fit_model(frame, C, feature_names=ALL_FEATURE_NAMES, model_family="lightgbm")
        params = LIGHTGBM_CANDIDATE_PARAMS[C]
        actual = model.get_params()
        for k, v in params.items():
            assert actual[k] == v
        proba = predict_probabilities(model, frame)
        assert (proba >= 0.0).all() and (proba <= 1.0).all()


def test_lightgbm_single_class_failure():
    frame = sample_12_features()
    frame['label'] = 0
    with pytest.raises(ValueError, match="training requires both classes"):
        fit_model(frame, 1.0, feature_names=ALL_FEATURE_NAMES, model_family="lightgbm")

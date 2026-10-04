from datetime import datetime, timedelta, timezone
import pandas as pd
import pytest

from cryptoquant.data.funding import (
    plan_funding_months,
    compute_funding_features,
    align_funding_to_hourly_bars,
)


def test_plan_funding_months():
    start = datetime(2022, 1, 1, tzinfo=timezone.utc)
    end = datetime(2022, 4, 1, tzinfo=timezone.utc)
    months = plan_funding_months(start, end)
    assert months == ["2022-01", "2022-02", "2022-03"]


def test_funding_features_calculation():
    # 模拟 100 期资金费率数据（每 8 小时一期）
    times = pd.date_range("2023-01-01 00:00:00+00:00", periods=100, freq="8h")
    # 前 50 期 0.0001，后 50 期 0.0005
    rates = [0.0001] * 50 + [0.0005] * 50
    df = pd.DataFrame({
        "symbol": "BTCUSDT",
        "funding_time": times,
        "funding_rate": rates,
        "source_id": "test",
    })

    feat = compute_funding_features(df)
    assert "funding_rate_ma3" in feat.columns
    assert "funding_rate_zscore" in feat.columns
    # 检验前 3 期的均值
    assert pytest.approx(feat.loc[2, "funding_rate_ma3"]) == 0.0001
    # 检验第 51 期的均值 (0.0001 + 0.0005 + 0.0005)/3
    assert pytest.approx(feat.loc[51, "funding_rate_ma3"]) == (0.0001 + 0.0005 + 0.0005) / 3
    # 检验第 52 期的均值 0.0005
    assert pytest.approx(feat.loc[52, "funding_rate_ma3"]) == 0.0005


def test_align_funding_strict_no_lookahead():
    # 模拟资金费率结算：00:00, 08:00, 16:00
    times = pd.to_datetime(["2023-01-01 00:00:00+00:00", "2023-01-01 08:00:00+00:00", "2023-01-01 16:00:00+00:00"])
    f_df = pd.DataFrame({
        "symbol": "BTCUSDT",
        "funding_time": times,
        "funding_rate": [0.0001, 0.0002, 0.0003],
        "funding_rate_ma3": [0.0001, 0.00015, 0.0002],
        "funding_rate_zscore": [0.0, 1.0, 2.0],
    })

    # 模拟小时决策时刻：06:00, 07:00, 08:00, 09:00
    bars = pd.DataFrame({
        "symbol": "BTCUSDT",
        "decision_time": pd.to_datetime([
            "2023-01-01 06:00:00+00:00",
            "2023-01-01 07:00:00+00:00",
            "2023-01-01 08:00:00+00:00",
            "2023-01-01 09:00:00+00:00",
        ]),
    })

    aligned = align_funding_to_hourly_bars(bars, f_df)

    # 在 07:00 时刻，08:00 费率尚未结算，必须使用 00:00 的 0.0001
    assert aligned.loc[aligned.decision_time == "2023-01-01 07:00:00+00:00", "funding_rate_latest"].iloc[0] == 0.0001
    # 在 08:00 时刻，08:00 费率刚好结算可用，为 0.0002
    assert aligned.loc[aligned.decision_time == "2023-01-01 08:00:00+00:00", "funding_rate_latest"].iloc[0] == 0.0002
    # 在 09:00 时刻，继续沿用 08:00 的 0.0002
    assert aligned.loc[aligned.decision_time == "2023-01-01 09:00:00+00:00", "funding_rate_latest"].iloc[0] == 0.0002


def test_12_features_end_to_end_and_model_fit():
    import numpy as np
    from cryptoquant.models.features import build_features, ALL_FEATURE_NAMES, HOUR
    from cryptoquant.models.training import fit_model, predict_probabilities

    # 构造合规的 800 小时小时 K 线
    times = pd.date_range("2023-01-01 00:00:00+00:00", periods=800, freq="h")
    kline_df = pd.DataFrame({
        "symbol": "BTCUSDT",
        "open_time": times,
        "open": 20000.0 + np.sin(np.arange(800)) * 500,
        "high": 20600.0,
        "low": 19400.0,
        "close": 20000.0 + np.sin(np.arange(800)) * 500 + 10,
        "quote_volume": 100000.0,
        "available_time": times + HOUR,
        "market_state": "observed",
        "row_role": "interior",
        "source_id": "test",
    })

    # 构造资金费率
    f_times = pd.date_range("2023-01-01 00:00:00+00:00", periods=105, freq="8h")
    funding_df = pd.DataFrame({
        "symbol": "BTCUSDT",
        "funding_time": f_times,
        "funding_rate": np.random.uniform(-0.0005, 0.0005, size=105),
        "funding_rate_ma3": np.random.uniform(-0.0003, 0.0003, size=105),
        "funding_rate_zscore": np.random.uniform(-1.5, 1.5, size=105),
    })

    features = build_features(kline_df, funding_df=funding_df)
    for name in ALL_FEATURE_NAMES:
        assert name in features.columns

    # 预热 744 小时后，样本有效 (0 到 743 为 744 根，743 到 799 共 57 根)
    valid_slice = features[features.feature_valid].copy()
    assert len(valid_slice) == 57
    assert not np.isnan(valid_slice[ALL_FEATURE_NAMES].to_numpy()).any()

    # 构造虚拟标签测试拟合
    valid_slice["label"] = np.random.choice([0, 1], size=len(valid_slice))
    model = fit_model(valid_slice, C=1.0)
    assert list(model.feature_names_in_) == ALL_FEATURE_NAMES

    # 预测概率
    probs = predict_probabilities(model, valid_slice)
    assert len(probs) == len(valid_slice)
    assert (probs >= 0).all() and (probs <= 1).all()


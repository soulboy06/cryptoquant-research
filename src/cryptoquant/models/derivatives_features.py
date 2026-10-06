"""Phase 5A 衍生品特征工程：Open Interest + Taker Flow 特征构造与严格时序对齐。

严格约束：
1. 决策时点因果性：在 decision_time（即 available_time，每 4h 整点），仅使用刚刚闭合的历史数据；
2. 无未来信息泄露：rolling、zscore 严格使用仅含过去的滚动窗口，禁止 centered 窗口与 backward fill；
3. 2026 数据完全封存，不参与任何特征构建与评估。
"""
from pathlib import Path
import numpy as np
import pandas as pd

from cryptoquant.models.features import ALL_FEATURE_NAMES

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DERIVATIVES_DIR = PROJECT_ROOT / "data" / "processed" / "derivatives_flow"

BASE_12_FEATURES = list(ALL_FEATURE_NAMES)
OI_FEATURES = [
    "oi_change_4h",
    "oi_change_24h",
    "oi_zscore_72h",
]
FLOW_FEATURES = [
    "taker_imbalance_1h",
    "taker_imbalance_4h",
    "taker_imbalance_24h",
    "taker_imbalance_zscore_72h",
]

FEATURE_FAMILIES = {
    "BASE_12": BASE_12_FEATURES,
    "OI_ONLY": BASE_12_FEATURES + OI_FEATURES,
    "FLOW_ONLY": BASE_12_FEATURES + FLOW_FEATURES,
    "OI_FLOW": BASE_12_FEATURES + OI_FEATURES + FLOW_FEATURES,
}


def build_derivatives_features_for_symbol(symbol: str, data_dir: Path | None = None) -> pd.DataFrame:
    """计算单个币种的 3 项持仓量特征与 4 项主动买卖流特征，并按 decision_time 对齐。"""
    folder = data_dir or DERIVATIVES_DIR
    parquet_path = folder / f"{symbol}_flow_oi.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(f"Missing derivatives flow data: {parquet_path}")

    df = pd.read_parquet(parquet_path)
    df = df.sort_values("open_time").reset_index(drop=True)

    # 1. 主动成交流特征 (基于刚刚闭合的 1h K 线: open_time = decision_time - 1h)
    buy_vol = df["taker_buy_quote_volume"].astype(float)
    tot_vol = df["total_quote_volume"].astype(float)

    # taker_imbalance_1h
    df["taker_imbalance_1h"] = df["taker_imbalance"].astype(float)

    # taker_imbalance_4h (过去 4 小时多周期主动买卖失衡度)
    roll4_buy = buy_vol.rolling(4, min_periods=4).sum()
    roll4_tot = tot_vol.rolling(4, min_periods=4).sum()
    ratio_4h = np.where(roll4_tot > 0, roll4_buy / roll4_tot, 0.5)
    df["taker_imbalance_4h"] = 2.0 * ratio_4h - 1.0

    # taker_imbalance_24h (过去 24 小时大周期主动买卖失衡度)
    roll24_buy = buy_vol.rolling(24, min_periods=24).sum()
    roll24_tot = tot_vol.rolling(24, min_periods=24).sum()
    ratio_24h = np.where(roll24_tot > 0, roll24_buy / roll24_tot, 0.5)
    df["taker_imbalance_24h"] = 2.0 * ratio_24h - 1.0

    # taker_imbalance_zscore_72h (过去 72 小时滚动 Z-score)
    roll72_mean = df["taker_imbalance_1h"].rolling(72, min_periods=72).mean()
    roll72_std = df["taker_imbalance_1h"].rolling(72, min_periods=72).std(ddof=1)
    df["taker_imbalance_zscore_72h"] = np.where(
        roll72_std > 1e-8,
        (df["taker_imbalance_1h"] - roll72_mean) / roll72_std,
        0.0
    )

    # 2. 持仓量特征
    # 决策时刻 decision_time = open_time + 1h。
    # 在 df 中，每行 open_time 为 T，对应 5 分钟快照在 T:00:00；
    # 决策时点 T+1h 刚刚形成的持仓量快照正是下下一行的整点数值，即 shift(-1)
    oi_series = df["sum_open_interest_ffill"].shift(-1).astype(float)
    df["oi_decision"] = oi_series

    # oi_change_4h = OI_t / OI_{t-4h} - 1
    oi_shift4 = oi_series.shift(4)
    df["oi_change_4h"] = np.where(oi_shift4 > 0, oi_series / oi_shift4 - 1.0, 0.0)

    # oi_change_24h = OI_t / OI_{t-24h} - 1
    oi_shift24 = oi_series.shift(24)
    df["oi_change_24h"] = np.where(oi_shift24 > 0, oi_series / oi_shift24 - 1.0, 0.0)

    # oi_zscore_72h (过去 72 小时滚动 Z-score)
    oi_mean72 = oi_series.rolling(72, min_periods=72).mean()
    oi_std72 = oi_series.rolling(72, min_periods=72).std(ddof=1)
    df["oi_zscore_72h"] = np.where(
        oi_std72 > 1e-8,
        (oi_series - oi_mean72) / oi_std72,
        0.0
    )

    # 对齐至 decision_time
    df["decision_time"] = df["open_time"] + pd.Timedelta(hours=1)
    
    keep_cols = ["decision_time"] + OI_FEATURES + FLOW_FEATURES
    out = df[keep_cols].copy().sort_values("decision_time").reset_index(drop=True)
    return out


def attach_derivatives_features(
    base_df: pd.DataFrame,
    derivatives_df: pd.DataFrame,
) -> pd.DataFrame:
    """将衍生品特征合并到现有训练样本或评估特征 DataFrame 中。"""
    merged = pd.merge(base_df, derivatives_df, on="decision_time", how="left")
    return merged

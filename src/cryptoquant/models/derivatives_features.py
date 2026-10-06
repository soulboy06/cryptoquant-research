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

# Phase 5B 交互特征定义 (严格限额 8 项，禁止裸特征进入模型)
INTERACTION_8_FEATURES = [
    "price_oi_4h",
    "price_oi_24h",
    "price_flow_4h",
    "price_flow_24h",
    "oi_flow_confirmation_4h",
    "oi_flow_confirmation_24h",
    "trend_oi_confirmation",
    "volatility_flow",
]

PHASE5B_FEATURE_FAMILIES = {
    "BASE_12": BASE_12_FEATURES,
    "INTERACTION_PRICE_OI": BASE_12_FEATURES + ["price_oi_4h", "price_oi_24h"],
    "INTERACTION_PRICE_FLOW": BASE_12_FEATURES + ["price_flow_4h", "price_flow_24h"],
    "INTERACTION_OI_FLOW": BASE_12_FEATURES + ["oi_flow_confirmation_4h", "oi_flow_confirmation_24h"],
    "INTERACTION_CONTEXT": BASE_12_FEATURES + ["trend_oi_confirmation", "volatility_flow"],
    "INTERACTION_ALL": BASE_12_FEATURES + INTERACTION_8_FEATURES,
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
    df["decision_time"] = df["open_time"] + pd.to_timedelta(1, unit='h')
    
    keep_cols = ["decision_time"] + OI_FEATURES + FLOW_FEATURES
    res = pd.DataFrame(df[keep_cols])
    return res.sort_values("decision_time").reset_index(drop=True)


def attach_derivatives_features(
    base_df: pd.DataFrame,
    derivatives_df: pd.DataFrame,
) -> pd.DataFrame:
    """将衍生品特征合并到现有训练样本或评估特征 DataFrame 中。"""
    merged = pd.merge(base_df, derivatives_df, on="decision_time", how="left")
    return merged


def compute_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """计算 8 个冻结交互特征。
    
    输入 df 包含 base 特征与 derivatives 特征。
    """
    out = df.copy()
    ret_4h = out["return_4h"].astype(float)
    ret_24h = out["return_24h"].astype(float)
    oi_4h = out["oi_change_4h"].astype(float)
    oi_24h = out["oi_change_24h"].astype(float)
    flow_4h = out["taker_imbalance_4h"].astype(float)
    flow_24h = out["taker_imbalance_24h"].astype(float)
    ema24_dist = out["ema24_distance"].astype(float)
    vol_24h = out["volatility_24h"].astype(float)

    # 1. price_oi_4h = return_4h * oi_change_4h
    out["price_oi_4h"] = (ret_4h * oi_4h).fillna(0.0)

    # 2. price_oi_24h = return_24h * oi_change_24h
    out["price_oi_24h"] = (ret_24h * oi_24h).fillna(0.0)

    # 3. price_flow_4h = return_4h * taker_imbalance_4h
    out["price_flow_4h"] = (ret_4h * flow_4h).fillna(0.0)

    # 4. price_flow_24h = return_24h * taker_imbalance_24h
    out["price_flow_24h"] = (ret_24h * flow_24h).fillna(0.0)

    # 5. oi_flow_confirmation_4h = oi_change_4h * taker_imbalance_4h
    out["oi_flow_confirmation_4h"] = (oi_4h * flow_4h).fillna(0.0)

    # 6. oi_flow_confirmation_24h = oi_change_24h * taker_imbalance_24h
    out["oi_flow_confirmation_24h"] = (oi_24h * flow_24h).fillna(0.0)

    # 7. trend_oi_confirmation = ema24_distance * oi_change_4h
    out["trend_oi_confirmation"] = (ema24_dist * oi_4h).fillna(0.0)

    # 8. volatility_flow = volatility_24h * taker_imbalance_4h
    out["volatility_flow"] = (vol_24h * flow_4h).fillna(0.0)

    return out


def attach_interaction_features(
    base_df: pd.DataFrame,
    derivatives_df: pd.DataFrame,
) -> pd.DataFrame:
    """合并衍生品特征并直接计算 8 个交互特征。"""
    merged = attach_derivatives_features(base_df, derivatives_df)
    return compute_interaction_features(merged)

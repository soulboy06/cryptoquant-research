"""币安公开合约资金费率获取、校验与时序对齐。

只使用官方公开归档与公开只读接口；严格防范未来信息泄漏。
资金费率每 8 小时结算一次（UTC 00:00、08:00、16:00）。
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import time
from zipfile import ZipFile, BadZipFile

import pandas as pd
import requests

VISION_BASE_URL = "https://data.binance.vision/data/futures/um/monthly/fundingRate"
FAPI_URL = "https://fapi.binance.com/fapi/v1/fundingRate"
SUPPORTED_SYMBOLS = {"BTCUSDT", "ETHUSDT", "SOLUSDT"}


@dataclass(frozen=True)
class FundingRateRecord:
    symbol: str
    funding_time: datetime
    funding_rate: float
    source_id: str


def plan_funding_months(start: datetime, end: datetime):
    """规划需要下载的完整月度 YYYY-MM 列表（仅包含 next_month <= end 的整月）。"""
    months = []
    curr = datetime(start.year, start.month, 1, tzinfo=timezone.utc)
    while curr < end:
        next_year = curr.year + (1 if curr.month == 12 else 0)
        next_month_val = 1 if curr.month == 12 else curr.month + 1
        next_month = datetime(next_year, next_month_val, 1, tzinfo=timezone.utc)
        if next_month <= end:
            months.append(curr.strftime("%Y-%m"))
        curr = next_month
    return months


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_monthly_funding_zip(symbol: str, year_month: str, cache_root: Path, session: requests.Session):
    """下载并校验单个官方月度资金费率 ZIP 与 SHA-256。"""
    filename = f"{symbol}-fundingRate-{year_month}.zip"
    zip_url = f"{VISION_BASE_URL}/{symbol}/{filename}"
    checksum_url = zip_url + ".CHECKSUM"

    # 1. 获取官方 CHECKSUM
    cs_resp = session.get(checksum_url, timeout=(10, 20))
    if cs_resp.status_code != 200:
        cs_resp.close()
        raise requests.HTTPError(f"HTTP {cs_resp.status_code} for {checksum_url}")
    cs_text = cs_resp.text.strip()
    cs_resp.close()

    m = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?([^\s]+)\s*", cs_text)
    if not m or m[2] != filename:
        raise ValueError(f"invalid checksum format or filename for {filename}: {cs_text}")
    expected_sha = m[1].lower()

    # 2. 检查缓存
    folder = cache_root / symbol / filename
    folder.mkdir(parents=True, exist_ok=True)
    target_zip = folder / f"{expected_sha}.zip"
    target_cs = folder / f"{expected_sha}.CHECKSUM"

    if not (target_zip.exists() and sha256_of_file(target_zip) == expected_sha):
        resp = session.get(zip_url, timeout=(10, 30))
        if resp.status_code != 200:
            resp.close()
            raise requests.HTTPError(f"HTTP {resp.status_code} for {zip_url}")
        content = resp.content
        resp.close()

        actual_sha = sha256_of_bytes(content)
        if actual_sha != expected_sha:
            raise ValueError(f"SHA-256 mismatch for {filename}: expected {expected_sha}, got {actual_sha}")

        # 校验 ZIP 结构
        with ZipFile(io.BytesIO(content)) as zf:
            csv_name = f"{symbol}-fundingRate-{year_month}.csv"
            if zf.namelist() != [csv_name]:
                raise ValueError(f"unexpected zip content in {filename}: {zf.namelist()}")
            if zf.testzip() is not None:
                raise ValueError(f"corrupted zip in {filename}")

        # 原子写入
        with tempfile.NamedTemporaryFile(dir=folder, suffix=".part", delete=False) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, target_zip)

    if not target_cs.exists():
        target_cs.write_text(f"{expected_sha}  {filename}\n", encoding="ascii")

    return target_zip, expected_sha


def parse_funding_zip(zip_path: Path, expected_sha: str):
    """解析已核验的月度资金费率 CSV。"""
    records = []
    with ZipFile(zip_path) as zf:
        csv_name = zf.namelist()[0]
        with zf.open(csv_name) as f:
            lines = f.read().decode("utf-8").strip().split("\n")
            for idx, line in enumerate(lines):
                if idx == 0:
                    continue  # 跳过表头 calc_time,funding_interval_hours,last_funding_rate
                parts = line.strip().split(",")
                if len(parts) != 3:
                    continue
                calc_ms = int(parts[0])
                interval = int(parts[1])
                rate = float(parts[2])
                # 标准化为整点 UTC
                dt = datetime.fromtimestamp(calc_ms / 1000, tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
                records.append({
                    "funding_time": dt,
                    "funding_interval_hours": interval,
                    "funding_rate": rate,
                    "source_id": expected_sha[:16],
                })
    return records


def fetch_tail_funding_fapi(symbol: str, start: datetime, end: datetime, cache_root: Path, session: requests.Session):
    """对于最新月度归档尚未包含的尾部日期，通过官方只读公开接口获取。"""
    start_ms = int(start.timestamp() * 1000)
    end_ms = int(end.timestamp() * 1000)

    url = f"{FAPI_URL}?symbol={symbol}&startTime={start_ms}&endTime={end_ms}&limit=1000"
    resp = session.get(url, timeout=(10, 20))
    if resp.status_code != 200:
        resp.close()
        raise requests.HTTPError(f"HTTP {resp.status_code} for {url}")
    data = resp.json()
    resp.close()

    raw_bytes = json.dumps(data, sort_keys=True).encode("utf-8")
    api_sha = sha256_of_bytes(raw_bytes)

    folder = cache_root / symbol / "fapi_tail"
    folder.mkdir(parents=True, exist_ok=True)
    json_path = folder / f"{api_sha}.json"
    if not json_path.exists():
        json_path.write_bytes(raw_bytes)

    records = []
    for item in data:
        dt = datetime.fromtimestamp(item["fundingTime"] / 1000, tz=timezone.utc).replace(minute=0, second=0, microsecond=0)
        records.append({
            "funding_time": dt,
            "funding_interval_hours": 8,
            "funding_rate": float(item["fundingRate"]),
            "source_id": f"fapi_{api_sha[:10]}",
        })
    return records


def load_and_audit_funding_rates(symbol: str, start: datetime, end: datetime, raw_cache_dir: Path, session: requests.Session | None = None):
    """全量下载、核验并构建 8 小时资金费率严格时间序列。"""
    if symbol not in SUPPORTED_SYMBOLS:
        raise ValueError(f"unsupported symbol {symbol}")
    if session is None:
        session = requests.Session()

    months = plan_funding_months(start, end)
    all_records = []

    # 1. 批量加载月包
    for ym in months:
        zip_path, sha = fetch_monthly_funding_zip(symbol, ym, raw_cache_dir, session)
        recs = parse_funding_zip(zip_path, sha)
        all_records.extend(recs)

    # 2. 检查是否有尾部日期（如当月末端到 end）
    df_temp = pd.DataFrame(all_records)
    max_time = df_temp["funding_time"].max() if not df_temp.empty else start
    if max_time < end - timedelta(hours=8):
        tail_recs = fetch_tail_funding_fapi(symbol, max_time + timedelta(hours=1), end, raw_cache_dir, session)
        all_records.extend(tail_recs)

    # 3. 排序去重与 8 小时间隔质量核验
    df = pd.DataFrame(all_records)
    df["symbol"] = symbol
    df = df.drop_duplicates(subset=["funding_time"]).sort_values("funding_time").reset_index(drop=True)

    # 过滤严格范围 [start, end)
    df = df[(df["funding_time"] >= start) & (df["funding_time"] < end)].copy()

    # 检查期望的 8 小时网格（00:00, 08:00, 16:00）
    expected_grid = pd.date_range(start, end, freq="8h", inclusive="left")
    actual_grid = pd.DatetimeIndex(df["funding_time"])
    missing = expected_grid.difference(actual_grid)

    if len(missing) > 0:
        raise ValueError(f"funding rate grid missing {len(missing)} settlements for {symbol}: first={missing[:3]}")

    df = df.reset_index(drop=True)
    return df[["symbol", "funding_time", "funding_rate", "source_id"]]


def compute_funding_features(funding_df: pd.DataFrame):
    """在 8 小时离散费率序列上计算衍生特征（均值、滚动 Z-score）。"""
    df = funding_df.copy().sort_values("funding_time").reset_index(drop=True)
    rates = df["funding_rate"]

    # 1. ma3: 过去 3 次结算（24 小时）均值
    df["funding_rate_ma3"] = rates.rolling(window=3, min_periods=1).mean()

    # 2. zscore: 过去 90 次结算（30 天）滚动 Z 分数
    rolling_90_mean = rates.rolling(window=90, min_periods=10).mean()
    rolling_90_std = rates.rolling(window=90, min_periods=10).std(ddof=1)
    # std 为 0 或样本不足时填 0
    zscore = (rates - rolling_90_mean) / rolling_90_std
    df["funding_rate_zscore"] = zscore.fillna(0.0)

    return df


def align_funding_to_hourly_bars(bars_df: pd.DataFrame, funding_features_df: pd.DataFrame):
    """将已计算的资金费率特征严格按时间对齐至小时 K 线。

    严格无未来信息规则：
    在每小时决策时刻 decision_time（即 available_time）：
    只能使用满足 funding_time <= decision_time 的最新一期已结算资金费率。
    """
    bars = bars_df.copy()
    if "decision_time" not in bars.columns:
        bars["decision_time"] = bars["available_time"]

    aligned = pd.merge_asof(
        bars.sort_values("decision_time"),
        funding_features_df.sort_values("funding_time"),
        left_on="decision_time",
        right_on="funding_time",
        by="symbol",
        direction="backward"
    )

    # 填充缺失为 0
    for col in ["funding_rate", "funding_rate_ma3", "funding_rate_zscore"]:
        aligned[col] = aligned[col].fillna(0.0)
    aligned.rename(columns={"funding_rate": "funding_rate_latest"}, inplace=True)

    return aligned

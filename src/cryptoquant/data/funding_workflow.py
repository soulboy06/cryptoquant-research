"""资金费率下载与校验工作流。"""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pandas as pd
import requests

from cryptoquant.config import load_config
from cryptoquant.data.funding import load_and_audit_funding_rates, compute_funding_features


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def execute(args, cwd: Path):
    config = load_config(args.config)
    start = config.download_start
    end = config.download_end
    symbols = config.symbols

    raw_cache = cwd / "data/raw/funding_rate"
    proc_dir = cwd / "data/processed/funding_rate"
    manifest_dir = cwd / "data/manifests"

    raw_cache.mkdir(parents=True, exist_ok=True)
    proc_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "download_start_utc": start.isoformat(),
        "download_end_utc": end.isoformat(),
        "symbols": {},
    }

    print(f"Starting funding rate ingestion for {symbols} from {start.isoformat()} to {end.isoformat()}...")

    for symbol in symbols:
        print(f"-> Processing {symbol}...")
        df = load_and_audit_funding_rates(symbol, start, end, raw_cache, session=session)
        assert isinstance(df, pd.DataFrame)
        print(f"   Audited {len(df)} 8-hour settlements for {symbol}. Range: {df['funding_time'].min()} to {df['funding_time'].max()}")

        feat_df = compute_funding_features(df)
        parquet_path = proc_dir / f"{symbol}.parquet"
        feat_df.to_parquet(parquet_path, index=False)

        file_sha = sha256_of_file(parquet_path)
        manifest["symbols"][symbol] = {
            "records": len(feat_df),
            "min_time_utc": str(feat_df["funding_time"].min()),
            "max_time_utc": str(feat_df["funding_time"].max()),
            "sha256": file_sha,
            "bytes": parquet_path.stat().st_size,
            "parquet_file": str(parquet_path.relative_to(cwd)),
        }
        print(f"   Saved {parquet_path.name} (SHA-256: {file_sha[:16]}...)")

    manifest_path = manifest_dir / "funding_rate_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Funding rate ingestion complete. Manifest: {manifest_path.relative_to(cwd)}")
    return 0

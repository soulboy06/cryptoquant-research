"""数据实验的下载、公开规则和质量检查三个可恢复步骤。"""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version, PackageNotFoundError
import json
from pathlib import Path
import platform
import shutil

import pandas as pd
import requests

from cryptoquant.cli import write_json
from cryptoquant.data.archive import download_range, get_response, plan_archives, sha_file
from cryptoquant.data.calendar import policy_info
from cryptoquant.data.normalize import read_archive
from cryptoquant.data.quality import audit, partition_data
from cryptoquant.data.rules import parse_market_rules

RULES_URL = "https://data-api.binance.vision/api/v3/exchangeInfo"


def environment():
    packages = {}
    for name in ["numpy", "pandas", "pyarrow", "requests", "matplotlib", "pytest", "scikit-learn", "scipy", "joblib", "threadpoolctl", "narwhals", "cloudpickle"]:
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = "not installed"
    return {"python": platform.python_version(), "platform": platform.platform(), "packages": packages}


def snapshot_source(attempt, config_path):
    project = Path(__file__).resolve().parents[3]
    files = sorted(project.glob("src/**/*.py")) + sorted(project.glob("src/**/*.json")) + sorted(project.glob("tests/**/*.py"))
    files.extend(path for name in ["pyproject.toml", "requirements-lock.txt"] if (path := project / name).exists())
    snapshot = attempt / "source_snapshot"
    hashes = {}
    for path in files:
        relative = path.relative_to(project)
        destination = snapshot / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        hashes[str(relative).replace("\\", "/")] = sha_file(path)
    shutil.copyfile(config_path, attempt / "config.toml")
    digest = hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest()
    write_json(attempt / "source_manifest.json", {"source_hash": digest, "files": hashes, "git_commit": None})
    return digest


def prepare(config, root, attempt, source_hash):
    manifest = {"status": "preparing", "config_hash": config.config_hash, "source_hash": source_hash, "data_policy": config.data_policy, "data_policy_sha256": policy_info(config.data_policy)[1], "environment": environment(), "started_at_utc": datetime.now(timezone.utc).isoformat(), "symbols": {}, "archives": [], "monthly_fallbacks": []}
    preferences = policy_info(config.data_policy)[0].get("source_preferences", [])
    manifest["source_preferences"] = preferences
    progress_path = attempt / "downloads.jsonl"
    normalized_root = root / "data/processed/normalized" / attempt.parents[1].name / attempt.name
    normalized_root.mkdir(parents=True, exist_ok=False)
    session = requests.Session()
    try:
        for symbol in config.symbols:
            def record(item):
                row = {"symbol": symbol, "filename": item.request.filename, "kind": item.request.kind, "url": item.request.url, "checksum_url": item.request.url + ".CHECKSUM", "start_utc": item.request.start.isoformat(), "end_exclusive_utc": item.request.end.isoformat(), "path": str(item.path.resolve()), "sha256": item.sha256, "bytes": item.bytes, "fetched_at_utc": item.fetched_at, "cache_hit": item.cache_hit, "status": "verified"}
                manifest["archives"].append(row)
                with progress_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row, ensure_ascii=False) + "\n")
                print(f"verified {symbol}: {item.request.filename}", flush=True)
            daily_months = {item["month"] for item in preferences if item["symbol"] == symbol and item["kind"] == "daily"}
            verified = download_range(symbol, config.download_start, config.download_end, root / "data/raw", session, progress=record, force_daily_months=daily_months)
            present = {item.request.filename for item in verified}
            manifest["monthly_fallbacks"].extend({"symbol": symbol, "filename": item.filename, "http_status": 404, "action": "daily_fallback"} for item in plan_archives(symbol, config.download_start, config.download_end, force_daily_months=daily_months) if item.kind == "monthly" and item.filename not in present)
            frames = [read_archive(item.path, symbol, f"{item.request.filename}:{item.sha256}", item.request.filename, policy=config.data_policy) for item in verified]
            full = pd.concat(frames, ignore_index=True)
            path = normalized_root / f"{symbol}.parquet"
            full.to_parquet(path, index=False)
            manifest["symbols"][symbol] = {"path": str(path.resolve()), "sha256": sha_file(path), "rows_before_quality_check": len(full)}
            write_json(attempt / "manifest.in_progress.json", manifest)
    finally:
        session.close()
    manifest.update(status="prepared_not_quality_checked", ended_at_utc=datetime.now(timezone.utc).isoformat())
    path = attempt / "manifest.json"
    write_json(path, manifest)
    manifest_hash = sha_file(path)
    write_json(root / "data/manifests" / f"{manifest_hash}.json", manifest)
    return {"manifest": str(path.resolve()), "manifest_sha256": manifest_hash, "source_hash": source_hash}


def rules(config, root, attempt):
    session = requests.Session()
    try:
        response = get_response(session, RULES_URL + "?symbols=" + requests.utils.quote(json.dumps(config.symbols, separators=(",", ":"))))
        try:
            payload = response.content
        finally:
            response.close()
    finally:
        session.close()
    if len(payload) > 5 * 1024 * 1024:
        raise ValueError("exchangeInfo snapshot too large")
    raw_path = attempt / "exchangeInfo.json"
    raw_path.write_bytes(payload)
    data = json.loads(payload)
    by_symbol = {item["symbol"]: item for item in data["symbols"]}
    if set(by_symbol) != set(config.symbols) or len(data["symbols"]) != len(by_symbol):
        raise ValueError("exchangeInfo symbol mismatch")
    # Outstanding-order count limits cannot bind this immediate-fill model.
    for item in data.get("exchangeFilters", []):
        if item["filterType"] not in {"EXCHANGE_MAX_NUM_ORDERS", "EXCHANGE_MAX_NUM_ALGO_ORDERS", "EXCHANGE_MAX_NUM_ICEBERG_ORDERS", "EXCHANGE_MAX_NUM_ORDER_LISTS"}:
            raise ValueError("unsupported exchange-wide rule")
    if data.get("assetFilters"):
        raise ValueError("asset-level limits require a separate implementation")
    parsed = {symbol: asdict(parse_market_rules(by_symbol[symbol], config.minimum_order_notional)) for symbol in config.symbols}
    digest = hashlib.sha256(payload).hexdigest()
    snapshot = root / "data/rules" / f"{digest}.json"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    if snapshot.exists() and sha_file(snapshot) != digest:
        raise ValueError("saved rule snapshot corrupted")
    if not snapshot.exists():
        snapshot.write_bytes(payload)
    report = {"status": "passed", "source": RULES_URL, "fetched_at_utc": datetime.now(timezone.utc).isoformat(), "sha256": digest, "snapshot": str(snapshot.resolve()), "rules": parsed, "limitations": ["Current snapshot used for historical simulation, not historical daily rules.", "Market notional checks use simulated fill price, not reconstructed reference/VWAP/last price."]}
    path = attempt / "rules_report.json"
    write_json(path, report)
    return {"rules_report": str(path.resolve()), "rules_sha256": digest}


def check_data(config, root, experiment, attempt):
    state = json.loads((experiment / "step_state.json").read_text(encoding="utf-8"))
    prepared = state["steps"]["prepare"]["result"]
    manifest_path = Path(prepared["manifest"])
    if sha_file(manifest_path) != prepared["manifest_sha256"]:
        raise ValueError("data manifest changed")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    policy_sha = policy_info(config.data_policy)[1]
    if manifest.get("data_policy") != config.data_policy or manifest.get("data_policy_sha256") != policy_sha:
        raise ValueError("data policy changed after prepare")
    rule_result = state["steps"]["rules"]["result"]
    rule_report = json.loads(Path(rule_result["rules_report"]).read_text(encoding="utf-8"))
    if sha_file(rule_report["snapshot"]) != rule_result["rules_sha256"]:
        raise ValueError("rule snapshot changed")
    for item in manifest["archives"]:
        if sha_file(item["path"]) != item["sha256"]:
            raise ValueError(f"raw archive changed: {item['filename']}")
    report = {"status": "checking", "config_hash": config.config_hash, "data_policy": config.data_policy, "data_policy_sha256": policy_sha, "data_manifest": str(manifest_path), "data_manifest_sha256": prepared["manifest_sha256"], "rules_sha256": rule_result["rules_sha256"], "environment": environment(), "symbols": {}, "partitions": {period: {} for period in ["development", "validation", "test"]}, "total_rows": 0, "total_archive_rows": 0, "total_observed_rows": 0, "total_halt_hours": 0, "total_no_trade_rows": 0}
    now = datetime.now(timezone.utc)
    try:
        for symbol in config.symbols:
            item = manifest["symbols"][symbol]
            if sha_file(item["path"]) != item["sha256"]:
                raise ValueError(f"normalized file changed: {symbol}")
            cleaned, quality = audit(pd.read_parquet(item["path"]), config.download_start, config.download_end, now, policy=config.data_policy)
            report["symbols"][symbol] = quality
            report["total_rows"] += len(cleaned)
            report["total_observed_rows"] += quality["observed_rows"]
            report["total_archive_rows"] += quality["archive_rows"]
            report["total_halt_hours"] += quality["known_halt_hours"]
            report["total_no_trade_rows"] += quality["no_trade_rows"]
            parts = partition_data(cleaned, config)
            for period, frame in parts.items():
                folder = root / "data/processed" / period / experiment.name / attempt.name
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / f"{symbol}.parquet"
                if path.exists():
                    raise ValueError("refusing to overwrite a partition")
                frame.to_parquet(path, index=False)
                report["partitions"][period][symbol] = {"path": str(path.resolve()), "sha256": sha_file(path), "evaluation_rows": int((frame.row_role == "evaluation").sum()), "warmup_rows": int((frame.row_role == "warmup").sum()), "boundary_rows": int((frame.row_role == "boundary").sum())}
            write_json(attempt / "quality.in_progress.json", report)
        if report["total_rows"] != config.expected_hours * len(config.symbols):
            raise ValueError("total row count mismatch")
    except Exception as exc:
        report.update(status="failed", error=str(exc))
        write_json(attempt / "quality_report.json", report)
        raise
    report.update(status="passed", checked_at_utc=now.isoformat())
    path = attempt / "quality_report.json"
    write_json(path, report)
    lines = ["# 数据检查报告", "", f"状态：通过。实际归档 {report['total_archive_rows']:,} 条，可用观察 {report['total_observed_rows']:,} 条；日历 {report['total_rows']:,} 行。包含 {report['total_no_trade_rows']} 条已核验的零成交不可用记录、{report['total_halt_hours']} 个空停机占位；占位不是实际 K 线。", "", "| 交易对 | 归档条目 | 可用观察 | 日历小时 | 空停机 | 零成交不可用 | 非标准结束 | 不明缺口 |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {symbol} | {item['archive_rows']:,} | {item['observed_rows']:,} | {item['rows']:,} | {item['known_halt_hours']} | {item['no_trade_rows']} | {item['nonstandard_close_count']} | {item['unexplained_missing_hours']} |" for symbol, item in report["symbols"].items()]
    lines += ["", "价格和成交量保留十进制字符串，时间统一 UTC；空停机行情为空，不填价、不造交易。no_trade 行保留原文，不允许成交、标签价格或新估值；这是已核验日历中的有限执行约束，不能作为在线预测信号。只接受有限精确例外，原始非标准 close_time 与异常标记保留。", "", "SOL 2021-12 使用官方日包，排除已发现异常的月包；其余完整月份月包优先，未发布月包真实404时才改日包。来源选择及哈希见 manifest。", "", "恢复后重新累计 744 个连续观察小时才可发出策略信号。此处仅生成历史可用状态与标签／成交可用接口，指标、账本和策略尚未实现。分区含预热，终点仅保留开盘、来源及市场状态；未来行情与历史状态掩码。", "", "规则使用当前公开快照，名义金额采用模拟成交价近似。本次仅检查数据，不运行策略、训练模型或评价验证／保留测试的收益。", "", "精确路径、来源、环境和 SHA-256 见同目录 quality_report.json 与关联 manifest。"]
    (attempt / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"quality_report": str(path.resolve()), "quality_report_sha256": sha_file(path), "total_rows": report["total_rows"], "total_archive_rows": report["total_archive_rows"], "total_observed_rows": report["total_observed_rows"], "total_no_trade_rows": report["total_no_trade_rows"], "total_halt_hours": report["total_halt_hours"]}


def execute(step, config, root, experiment, attempt, config_path):
    source_hash = snapshot_source(attempt, config_path)
    context_path = attempt / "run_context.json"
    write_json(context_path, {"step": step, "started_at_utc": datetime.now(timezone.utc).isoformat(), "config_hash": config.config_hash, "source_hash": source_hash, "environment": environment()})
    if step == "prepare":
        result = prepare(config, root, attempt, source_hash)
    elif step == "rules":
        result = rules(config, root, attempt)
    elif step == "check-data":
        result = check_data(config, root, experiment, attempt)
    else:
        raise ValueError("unknown step")
    return result | {"source_hash": source_hash, "run_context": str(context_path.resolve()), "run_context_sha256": sha_file(context_path)}

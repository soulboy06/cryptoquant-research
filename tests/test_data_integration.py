import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from zipfile import ZipFile, ZipInfo

import pandas as pd
import pytest

from cryptoquant.cli import main
from test_rules import info

CONFIG = Path(__file__).parents[1] / "configs/first_experiment.toml"


class PublicResponse:
    status_code = 200
    headers = {}

    def __init__(self, payload):
        self.content = payload
        self.text = payload.decode("utf-8", errors="replace")

    def iter_content(self, size):
        yield self.content

    def close(self):
        pass


class PublicSession:
    halt_fixture = False
    def get(self, url, **kwargs):
        if "exchangeInfo" in url:
            symbols = []
            for symbol in ["BTCUSDT", "ETHUSDT", "SOLUSDT"]:
                symbol_info = info()
                symbol_info["symbol"] = symbol
                symbols.append(symbol_info)
            return PublicResponse(json.dumps({"symbols": symbols, "exchangeFilters": []}).encode())
        filename = url.rsplit("/", 1)[-1].removesuffix(".CHECKSUM")
        stamp = re.search(r"-1h-(.*)\.zip", filename)[1]
        start = datetime.strptime(stamp, "%Y-%m" if len(stamp) == 7 else "%Y-%m-%d").replace(tzinfo=timezone.utc)
        end = start.replace(month=start.month + 1, day=1, year=start.year) if len(stamp) == 7 and start.month != 12 else (start.replace(year=start.year + 1, month=1, day=1) if len(stamp) == 7 else start + timedelta(days=1))
        stream = io.BytesIO()
        lines = []
        for opened in pd.date_range(start, end, freq="h", inclusive="left"):
            if self.halt_fixture and opened == pd.Timestamp('2023-03-24T13:00:00Z'):
                continue
            stamp_ms = int(opened.timestamp()) * 1000
            closed = stamp_ms + 3599999
            if self.halt_fixture and opened == pd.Timestamp('2023-03-24T12:00:00Z'):
                closed = {'BTCUSDT': 1679661581646, 'ETHUSDT': 1679661583061, 'SOLUSDT': 1679661586948}[filename.split('-')[0]]
                lines.append(f"{stamp_ms},11,11,11,11,0,{closed},0,0,0,0,0")
            else:
                lines.append(f"{stamp_ms},10,12,9,11,2,{closed},21,3,1,10,0")
        with ZipFile(stream, "w") as zipped:
            zipped.writestr(ZipInfo(filename[:-4] + '.csv', date_time=(2020, 1, 1, 0, 0, 0)), "\n".join(lines))
        payload = stream.getvalue()
        if url.endswith(".CHECKSUM"):
            return PublicResponse(f"{hashlib.sha256(payload).hexdigest()}  {filename}".encode())
        return PublicResponse(payload)

    def close(self):
        pass


def small_config(tmp_path):
    body = CONFIG.read_text()
    changes = {"2026-10-02T00:00:00Z": "2022-01-05T00:00:00Z", "2025-01-01T00:00:00Z": "2022-01-02T00:00:00Z", "2025-12-31T20:00:00Z": "2022-01-02T20:00:00Z", "2026-01-01T00:00:00Z": "2022-01-03T00:00:00Z", "2026-10-01T00:00:00Z": "2022-01-04T00:00:00Z"}
    for old, new in changes.items():
        body = body.replace(old, new)
    path = tmp_path / "config.toml"
    path.write_text(body, encoding="utf-8")
    return path


def test_public_data_pipeline_end_to_end_without_network(tmp_path, monkeypatch):
    import requests
    monkeypatch.setattr(requests, "Session", PublicSession)
    monkeypatch.chdir(tmp_path)
    config = small_config(tmp_path)
    for command in ["prepare", "rules", "check-data"]:
        assert main([command, "--config", str(config), "--experiment-id", "EXP-001"]) == 0
    experiment = tmp_path / "artifacts/experiments/EXP-001"
    state = json.loads((experiment / "step_state.json").read_text())
    assert all(x["status"] == "complete" for x in state["steps"].values())
    for step in state["steps"].values():
        context = json.loads(Path(step["result"]["run_context"]).read_text())
        snapshot = Path(step["attempts"][-1]["path"]) / "source_manifest.json"
        assert context["source_hash"] == json.loads(snapshot.read_text())["source_hash"]
        assert "python" in context["environment"]
    report_path = Path(state["steps"]["check-data"]["result"]["quality_report"])
    report = json.loads(report_path.read_text())
    manifest = json.loads(Path(state['steps']['prepare']['result']['manifest']).read_text())
    assert manifest['data_policy'] == report['data_policy'] == 'halt_aware_v2'
    assert manifest['data_policy_sha256'] == report['data_policy_sha256']
    assert report['total_observed_rows'] == report['total_rows']
    source_files = json.loads((experiment / 'prepare/attempt-001/source_manifest.json').read_text())['files']
    assert 'src/cryptoquant/data/market_calendar.json' in source_files
    assert 'src/cryptoquant/data/market_calendar_v2.json' in source_files
    assert manifest['source_preferences'][0]['symbol'] == 'SOLUSDT'
    december = [x for x in manifest['archives'] if x['symbol'] == 'SOLUSDT' and '2021-12' in x['filename']]
    assert len(december) == 31 and all(x['kind'] == 'daily' for x in december)
    assert not any(x['filename'] == 'SOLUSDT-1h-2021-12.zip' for x in manifest['monthly_fallbacks'])
    assert report["total_rows"] == 840 * 3
    assert all(x["missing_hours"] == 0 for x in report["symbols"].values())
    part = pd.read_parquet(report["partitions"]["development"]["BTCUSDT"]["path"])
    assert (part.row_role == "evaluation").sum() == 24
    assert part.iloc[-1]["row_role"] == "boundary" and pd.isna(part.iloc[-1]["close"])
    original = report_path.read_bytes()
    assert main(["check-data", "--config", str(config), "--experiment-id", "EXP-001"]) == 1
    assert report_path.read_bytes() == original


def test_http_failure_is_recorded_without_fake_success(tmp_path, monkeypatch):
    import requests
    class Offline(PublicSession):
        def get(self, *args, **kwargs):
            raise requests.HTTPError("offline fixture")
    monkeypatch.setattr(requests, "Session", Offline)
    monkeypatch.chdir(tmp_path)
    config = small_config(tmp_path)
    assert main(["prepare", "--config", str(config), "--experiment-id", "EXP-001"]) == 1
    state = json.loads((tmp_path / "artifacts/experiments/EXP-001/step_state.json").read_text())
    assert state["steps"]["prepare"]["status"] == "failed"
    assert "offline fixture" in state["steps"]["prepare"]["result"]["error"]


def test_policy_change_after_prepare_stops_quality_step(tmp_path, monkeypatch):
    import requests
    from cryptoquant.data import workflow
    monkeypatch.setattr(requests, 'Session', PublicSession)
    monkeypatch.chdir(tmp_path)
    config = small_config(tmp_path)
    for command in ['prepare', 'rules']:
        assert main([command, '--config', str(config), '--experiment-id', 'EXP-001']) == 0
    policy_info = workflow.policy_info
    monkeypatch.setattr(workflow, 'policy_info', lambda policy: (policy_info(policy)[0], '0' * 64))
    assert main(['check-data', '--config', str(config), '--experiment-id', 'EXP-001']) == 1
    state = json.loads((tmp_path / 'artifacts/experiments/EXP-001/step_state.json').read_text())
    assert 'policy changed' in state['steps']['check-data']['result']['error']


def test_halt_pipeline_reports_actual_candles_and_calendar_separately(tmp_path, monkeypatch):
    import requests
    class HaltedSession(PublicSession):
        halt_fixture = True
    monkeypatch.setattr(requests, 'Session', HaltedSession)
    monkeypatch.chdir(tmp_path)
    body = CONFIG.read_text(encoding='utf-8')
    replacements = {'2021-12-01T00:00:00Z': '2023-02-01T00:00:00Z', '2022-01-01T00:00:00Z': '2023-03-23T00:00:00Z', '2025-01-01T00:00:00Z': '2023-03-24T00:00:00Z', '2025-12-31T20:00:00Z': '2023-03-24T20:00:00Z', '2026-01-01T00:00:00Z': '2023-03-25T00:00:00Z', '2026-10-01T00:00:00Z': '2023-03-26T00:00:00Z', '2026-10-02T00:00:00Z': '2023-03-27T00:00:00Z'}
    for old, new in replacements.items():
        body = body.replace(old, new)
    config = tmp_path / 'halt.toml'
    config.write_text(body, encoding='utf-8')
    for command in ['prepare', 'rules', 'check-data']:
        assert main([command, '--config', str(config), '--experiment-id', 'EXP-001']) == 0
    report = json.loads((tmp_path / 'artifacts/experiments/EXP-001/check-data/attempt-001/quality_report.json').read_text())
    assert report['total_rows'] - report['total_archive_rows'] == report['total_halt_hours'] == 3
    assert report['total_archive_rows'] - report['total_observed_rows'] == report['total_no_trade_rows'] == 3
    assert all(x['nonstandard_close_count'] == 1 for x in report['symbols'].values())
    part = pd.read_parquet(report['partitions']['validation']['BTCUSDT']['path'])
    assert pd.isna(part[part.market_state == 'halt'].iloc[0]['open'])
    noon = part[part.market_state == 'no_trade'].iloc[0]
    assert noon['open'] == '11' and noon.history_count == 0

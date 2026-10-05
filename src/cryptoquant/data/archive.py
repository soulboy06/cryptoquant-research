"""只读公开归档，校验后发布不可变版本。"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
import hashlib
import os
import re
import tempfile
import time
from zipfile import ZipFile, BadZipFile

import requests

BASE_URL = "https://data.binance.vision/data/spot"


@dataclass(frozen=True)
class ArchiveRequest:
    symbol: str
    kind: str
    start: datetime
    end: datetime
    filename: str

    @property
    def url(self):
        return f"{BASE_URL}/{self.kind}/klines/{self.symbol}/1h/{self.filename}"


@dataclass(frozen=True)
class VerifiedArchive:
    request: ArchiveRequest
    path: Path
    sha256: str
    bytes: int
    fetched_at: str
    cache_hit: bool


def plan_archives(symbol, start, end, monthly=True, force_daily_months=()):
    if symbol not in {"BTCUSDT", "ETHUSDT", "SOLUSDT"} or start.utcoffset() != timedelta(0) or end.utcoffset() != timedelta(0) or start >= end:
        raise ValueError("invalid archive request")
    if any([start.hour, start.minute, start.second, start.microsecond, end.hour, end.minute, end.second, end.microsecond]):
        raise ValueError("archive range must use UTC midnight boundaries")
    items = []
    current = start
    while current < end:
        next_month = current.replace(year=current.year + (current.month == 12), month=current.month % 12 + 1, day=1)
        use_month = monthly and current.strftime("%Y-%m") not in force_daily_months and current.day == 1 and next_month <= end
        following = next_month if use_month else current + timedelta(days=1)
        stamp = current.strftime("%Y-%m" if use_month else "%Y-%m-%d")
        items.append(ArchiveRequest(symbol, "monthly" if use_month else "daily", current, following, f"{symbol}-1h-{stamp}.zip"))
        current = following
    return items


def get_response(session, url, *, sleep=time.sleep, stream=False):
    for attempt in range(3):
        response = None
        try:
            response = session.get(url, timeout=(10, 20), stream=stream)
            status = response.status_code
            if status == 200:
                return response
            error = requests.HTTPError(f"HTTP {status}: {url}", response=response)
            if status not in {429, 500, 502, 503, 504}:
                raise error
            if attempt == 2:
                raise error
            delay = 2 ** attempt
            if status == 429 and response.headers.get("Retry-After"):
                value = response.headers["Retry-After"]
                try:
                    delay = float(value)
                except ValueError:
                    delay = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
                if not 0 <= delay <= 10:
                    raise ValueError("retry later: Retry-After exceeds short retry budget")
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 2:
                raise
            delay = 2 ** attempt
        finally:
            if response is not None and response.status_code != 200:
                response.close()
        sleep(delay)
    raise RuntimeError("unreachable retry state")


def sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def validate_zip(path, filename):
    try:
        with ZipFile(path) as zipped:
            if zipped.namelist() != [filename[:-4] + ".csv"]:
                raise ValueError("unexpected ZIP members")
            if zipped.testzip() is not None:
                raise ValueError("ZIP CRC mismatch")
    except BadZipFile as exc:
        raise ValueError("download is not a ZIP") from exc


def fetch_verified(request, cache_root, session):
    checksum_response = get_response(session, request.url + ".CHECKSUM")
    try:
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?([^\s]+)\s*", checksum_response.text.strip())
        if not match or match[2] != request.filename:
            raise ValueError("invalid checksum format or filename")
        expected = match[1].lower()
    finally:
        checksum_response.close()
    folder = Path(cache_root) / request.symbol / "1h" / request.filename
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{expected}.zip"
    hit = target.exists() and sha_file(target) == expected
    if not hit:
        response = get_response(session, request.url, stream=True)
        temp_name = None
        try:
            with tempfile.NamedTemporaryFile(dir=folder, suffix=".part", delete=False) as stream:
                temp_name = Path(stream.name)
                digest = hashlib.sha256()
                size = 0
                for block in response.iter_content(64 * 1024):
                    if block:
                        size += len(block)
                        if size > 100 * 1024 * 1024:
                            raise ValueError("1h archive exceeds download size budget")
                        stream.write(block)
                        digest.update(block)
            if digest.hexdigest() != expected:
                raise ValueError("SHA-256 mismatch")
            validate_zip(temp_name, request.filename)
            os.replace(temp_name, target)
        finally:
            response.close()
            if temp_name is not None:
                temp_name.unlink(missing_ok=True)
    validate_zip(target, request.filename)
    # Keep the official checksum beside the corresponding immutable content.
    checksum_path = folder / f"{expected}.CHECKSUM"
    if not checksum_path.exists():
        checksum_path.write_text(f"{expected}  {request.filename}\n", encoding="ascii")
    return VerifiedArchive(request, target, expected, target.stat().st_size, datetime.now(timezone.utc).isoformat(), hit)


def download_range(symbol, start, end, cache_root, session, progress=None, force_daily_months=()):
    verified = []
    for request in plan_archives(symbol, start, end, force_daily_months=force_daily_months):
        try:
            result = [fetch_verified(request, cache_root, session)]
        except requests.HTTPError as exc:
            if request.kind != "monthly" or exc.response is None or exc.response.status_code != 404:
                raise
            result = []
            for day in plan_archives(symbol, request.start, request.end, monthly=False):
                item = fetch_verified(day, cache_root, session)
                result.append(item)
                if progress:
                    progress(item)
        else:
            if progress:
                progress(result[0])
        verified.extend(result)
    return verified

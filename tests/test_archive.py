import hashlib
import io
from datetime import datetime, timezone
from zipfile import ZipFile

import pytest
import requests

from cryptoquant.data.archive import plan_archives, fetch_verified, download_range, get_response


def utc(value):
    return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


def zipped(name, text="data"):
    stream = io.BytesIO()
    with ZipFile(stream, "w") as archive:
        archive.writestr(name, text)
    return stream.getvalue()


class Response:
    def __init__(self, data=b"", status=200, headers=None):
        self.content, self.status_code = data, status
        self.headers = headers or {}
        self.text = data.decode("utf-8", errors="replace")

    def iter_content(self, size):
        yield self.content

    def close(self):
        pass


class Session:
    def __init__(self, replies):
        self.replies = list(replies)
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def test_full_month_and_partial_days_are_planned_without_overlap():
    items = plan_archives("BTCUSDT", utc("2025-01-31"), utc("2025-03-02"))
    assert [x.filename for x in items] == ["BTCUSDT-1h-2025-01-31.zip", "BTCUSDT-1h-2025-02.zip", "BTCUSDT-1h-2025-03-01.zip"]
    assert [x.kind for x in items] == ["daily", "monthly", "daily"]


def replies(item, payload):
    digest = hashlib.sha256(payload).hexdigest()
    return [Response(f"{digest}  {item.filename}\n".encode()), Response(payload)]


def test_verified_cache_is_immutable_and_corruption_is_not_trusted(tmp_path):
    item = plan_archives("BTCUSDT", utc("2025-01-01"), utc("2025-01-02"))[0]
    first = zipped(item.filename[:-4] + ".csv", "one")
    second = zipped(item.filename[:-4] + ".csv", "two")
    a = fetch_verified(item, tmp_path, Session(replies(item, first)))
    b = fetch_verified(item, tmp_path, Session(replies(item, second)))
    assert a.path != b.path and a.path.read_bytes() == first
    cached = fetch_verified(item, tmp_path, Session(replies(item, second)[:1]))
    assert cached.path == b.path and cached.cache_hit
    b.path.write_bytes(b"damaged")
    repaired = fetch_verified(item, tmp_path, Session(replies(item, second)))
    assert repaired.path.read_bytes() == second


@pytest.mark.parametrize("data,checksum", [
    (b"<html>oops</html>", None),
    (b"not a zip", "0" * 64),
    (b"x", "invalid"),
])
def test_bad_download_does_not_publish_a_zip(tmp_path, data, checksum):
    item = plan_archives("BTCUSDT", utc("2025-01-01"), utc("2025-01-02"))[0]
    checksum = checksum or hashlib.sha256(data).hexdigest()
    session = Session([Response(f"{checksum} {item.filename}".encode()), Response(data)])
    with pytest.raises(ValueError):
        fetch_verified(item, tmp_path, session)
    assert not [path for path in tmp_path.rglob("*.zip") if path.is_file()]
    assert not list(tmp_path.rglob("*.part"))


def test_month_404_falls_back_to_days_only(tmp_path):
    item = plan_archives("BTCUSDT", utc("2025-02-01"), utc("2025-03-01"))[0]
    days = plan_archives("BTCUSDT", item.start, item.end, monthly=False)
    responses = [Response(status=404)]
    for day in days:
        responses.extend(replies(day, zipped(day.filename[:-4] + ".csv")))
    result = download_range("BTCUSDT", item.start, item.end, tmp_path, Session(responses))
    assert len(result) == 28 and all(x.request.kind == "daily" for x in result)


@pytest.mark.parametrize("status", [403, 404, 451])
def test_missing_daily_and_forbidden_files_fail(tmp_path, status):
    with pytest.raises(requests.HTTPError):
        download_range("BTCUSDT", utc("2025-01-01"), utc("2025-01-02"), tmp_path, Session([Response(status=status)]))


def test_http_retries_are_finite_and_respect_short_retry_after():
    sleeps = []
    session = Session([Response(status=429, headers={"Retry-After": "3"}), Response(status=503), Response(b"ok")])
    assert get_response(session, "https://data.binance.vision/x", sleep=sleeps.append).content == b"ok"
    assert sleeps == [3, 2]
    with pytest.raises(requests.Timeout):
        get_response(Session([requests.Timeout()] * 3), "https://data.binance.vision/x", sleep=lambda _: None)


def test_long_retry_after_returns_without_blocking_agent():
    with pytest.raises(ValueError, match="retry"):
        get_response(Session([Response(status=429, headers={"Retry-After": "300"})]), "https://data.binance.vision/x", sleep=lambda _: pytest.fail("must not sleep"))


def test_explicit_daily_month_preserves_range_and_other_month_priority():
    planned = plan_archives('SOLUSDT', utc('2021-12-01'), utc('2022-02-01'), force_daily_months={'2021-12'})
    assert len(planned) == 32 and all(x.kind == 'daily' for x in planned[:31])
    assert planned[-1].filename == 'SOLUSDT-1h-2022-01.zip'
    assert all(a.end == b.start for a, b in zip(planned, planned[1:]))
    assert planned[0].start == utc('2021-12-01') and planned[-1].end == utc('2022-02-01')
    partial = plan_archives('SOLUSDT', utc('2021-12-24'), utc('2022-01-02'), force_daily_months={'2021-12'})
    assert len(partial) == 9 and all(x.kind == 'daily' for x in partial)


def test_daily_preference_download_does_not_request_monthly_or_fake_404(tmp_path):
    days = plan_archives('SOLUSDT', utc('2021-12-01'), utc('2022-01-01'), monthly=False)
    responses = []
    for day in days:
        responses.extend(replies(day, zipped(day.filename[:-4] + '.csv')))
    session = Session(responses)
    actual = download_range('SOLUSDT', utc('2021-12-01'), utc('2022-01-01'), tmp_path, session, force_daily_months={'2021-12'})
    assert len(actual) == 31
    assert all('/daily/' in url for url in session.urls)

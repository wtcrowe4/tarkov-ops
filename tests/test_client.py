import pytest
from pytest_httpx import HTTPXMock

from tarkov_ops.progress.client import TrackerAuthError, TrackerClient, TrackerQuotaError
from tarkov_ops.settings import Settings

BASE = "https://api.tarkovtracker.org"


@pytest.fixture
def settings() -> Settings:
    return Settings(tarkovtracker_token="PVE_deadbeefcafefeed01", _env_file=None)  # type: ignore[call-arg]


def test_etag_roundtrip_returns_304_without_body(settings: Settings, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/progress",
        json={"success": True},
        headers={"ETag": 'W/"abc"', "X-RateLimit-Remaining": "999", "X-RateLimit-Limit": "1000"},
    )
    httpx_mock.add_response(
        url=f"{BASE}/progress",
        status_code=304,
        match_headers={"If-None-Match": 'W/"abc"'},
        headers={"X-RateLimit-Remaining": "998"},
    )
    with TrackerClient(settings) as c:
        first = c.progress()
        second = c.progress()
    assert first.status == 200 and first.data == {"success": True} and first.rate_remaining == 999
    assert second.status == 304 and second.data is None and second.rate_remaining == 998
    assert second.etag == 'W/"abc"'


def test_401_raises_auth_error(settings: Settings, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/progress", status_code=401, json={"error": "Invalid token"}
    )
    with TrackerClient(settings) as c, pytest.raises(TrackerAuthError):
        c.progress()


def test_429_raises_quota_error_with_retry_after(settings: Settings, httpx_mock: HTTPXMock):
    httpx_mock.add_response(
        url=f"{BASE}/progress", status_code=429, headers={"Retry-After": "3600"}
    )
    with TrackerClient(settings) as c, pytest.raises(TrackerQuotaError) as ei:
        c.progress()
    assert ei.value.retry_after == 3600


def test_authorization_header_never_in_repr(settings: Settings):
    assert "deadbeef" not in repr(settings)

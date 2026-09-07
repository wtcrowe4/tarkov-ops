"""TarkovTracker progress API client.

Read-only in v1. Honors ETag / If-None-Match, logs X-RateLimit-Remaining on every
call, and raises loudly on 401 and 429. The Authorization header is never logged.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

import httpx

from tarkov_ops.settings import Settings, get_settings

log = logging.getLogger(__name__)


class TrackerAuthError(RuntimeError):
    """401: token invalid, revoked, or game-mode mismatch."""


class TrackerQuotaError(RuntimeError):
    """429: daily quota exhausted. `retry_after` is seconds."""

    def __init__(self, retry_after: int | None):
        self.retry_after = retry_after
        super().__init__(f"TarkovTracker quota exhausted; retry after {retry_after}s")


@dataclass
class TrackerResponse:
    status: int
    etag: str | None
    data: dict[str, Any] | None  # None on 304
    rate_remaining: int | None
    rate_limit: int | None
    rate_reset: int | None


class TrackerClient:
    def __init__(self, settings: Settings | None = None, timeout: float = 20.0):
        self.settings = settings or get_settings()
        self._client = httpx.Client(
            base_url=self.settings.tarkovtracker_base,
            headers={
                "Authorization": f"Bearer {self.settings.tarkovtracker_token.get_secret_value()}",
                "Accept": "application/json",
                "User-Agent": "tarkov-ops/0.1 (+https://github.com/wtcrowe4/tarkov-ops)",
            },
            timeout=timeout,
            follow_redirects=False,  # never carry the bearer across hosts
        )
        self._etag_cache: dict[str, str] = {}

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def get(self, path: str, use_etag: bool = True) -> TrackerResponse:
        headers: dict[str, str] = {}
        if use_etag and (etag := self._etag_cache.get(path)):
            headers["If-None-Match"] = etag
        r = self._client.get(path, headers=headers)

        limit = _int_header(r, "X-RateLimit-Limit")
        remaining = _int_header(r, "X-RateLimit-Remaining")
        reset = _int_header(r, "X-RateLimit-Reset")
        log.info("GET %s -> %s (quota %s/%s)", path, r.status_code, remaining, limit)

        if r.status_code == 401:
            raise TrackerAuthError("401 from TarkovTracker: check token and PVE_ game mode")
        if r.status_code == 429:
            raise TrackerQuotaError(_int_header(r, "Retry-After"))
        if r.status_code in (301, 302, 307, 308):
            raise RuntimeError(
                f"Unexpected redirect to {r.headers.get('location')}; "
                "TARKOVTRACKER_BASE must be https://api.tarkovtracker.org"
            )
        r.raise_for_status()

        etag = r.headers.get("ETag")
        if etag:
            self._etag_cache[path] = etag

        data = None if r.status_code == 304 else r.json()
        return TrackerResponse(r.status_code, etag, data, remaining, limit, reset)

    def progress(self, use_etag: bool = True) -> TrackerResponse:
        return self.get("/progress", use_etag=use_etag)

    def token_info(self) -> TrackerResponse:
        """GET /token: permissions, game mode, call count. Costs one read."""
        return self.get("/token", use_etag=False)

    def dump_progress(self, dest: Path) -> TrackerResponse:
        """Fetch /progress without ETag and save the raw JSON to `dest`."""
        resp = self.progress(use_etag=False)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(resp.data, indent=2), encoding="utf-8")
        return resp


def _int_header(r: httpx.Response, name: str) -> int | None:
    v = r.headers.get(name)
    try:
        return int(v) if v is not None else None
    except ValueError:
        return None

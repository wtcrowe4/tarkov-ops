"""Fetch json.tarkov.dev endpoints into a local cache.

Raw documents land in `data/gamedata/<endpoint>.json` (plus `<endpoint>_en.json` for
endpoints that carry translation keys). `meta.json` records `fetchedAt` per endpoint.
Everything downstream reads the cache; nothing reads the network in a request path.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from tarkov_ops.settings import Settings, get_settings

log = logging.getLogger(__name__)

# endpoint -> has an English translation overlay
ENDPOINTS: dict[str, bool] = {
    "tasks": True,
    "hideout": True,
    "items": True,
    "traders": True,
}
MAX_AGE = timedelta(hours=12)
USER_AGENT = "tarkov-ops/0.1 (+https://github.com/wtcrowe4/tarkov-ops)"


def cache_dir(settings: Settings | None = None) -> Path:
    s = settings or get_settings()
    return s.data_dir / "gamedata"


def read_meta(directory: Path) -> dict[str, str]:
    p = directory / "meta.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def is_stale(directory: Path, max_age: timedelta = MAX_AGE) -> bool:
    meta = read_meta(directory)
    if not all(name in meta for name in ENDPOINTS):
        return True
    oldest = min(datetime.fromisoformat(meta[name]) for name in ENDPOINTS)
    return datetime.now(UTC) - oldest > max_age


def refresh(
    settings: Settings | None = None,
    directory: Path | None = None,
    client: httpx.Client | None = None,
) -> dict[str, int]:
    """Download every endpoint (and its `_en` overlay). Returns bytes written per file."""
    s = settings or get_settings()
    out = directory or cache_dir(s)
    out.mkdir(parents=True, exist_ok=True)
    own = client is None
    c = client or httpx.Client(
        base_url=s.tarkov_json_base, headers={"User-Agent": USER_AGENT}, timeout=120.0
    )
    sizes: dict[str, int] = {}
    meta = read_meta(out)
    try:
        for name, translated in ENDPOINTS.items():
            files = [name, f"{name}_en"] if translated else [name]
            for f in files:
                r = c.get(f"/{s.game_mode}/{f}")
                r.raise_for_status()
                body = r.content
                json.loads(body)  # validate before replacing the cached copy
                tmp = out / f"{f}.json.tmp"
                tmp.write_bytes(body)
                tmp.replace(out / f"{f}.json")
                sizes[f] = len(body)
                log.info("fetched %s (%s bytes)", f, f"{len(body):,}")
            meta[name] = datetime.now(UTC).isoformat()
        (out / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    finally:
        if own:
            c.close()
    return sizes

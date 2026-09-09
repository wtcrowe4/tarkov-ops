# Decisions

ADR-style, newest at the bottom. One line of context, one line of decision.

## 2026-09-07 — Phase 0 scaffold on laptop (Omarchy)

- **Python 3.14** pinned via `uv` (`.python-version`). `requires-python >=3.13` so the
  Alienware can drop to 3.13 if `opencv-python` wheels lag on Windows. Plan said 3.12;
  owner asked for newest.
- **Layout**: `uv` project, hatchling build, `src/tarkov_ops`. Phase 3+ deps
  (`opencv`, `watchdog`, `mcp`, `apscheduler`) are optional extras so Phases 0-2 stay light.
- **Repo public** on GitHub. Nothing sensitive is tracked: `.env`, `data/`, `inbox/`, `out/`,
  `docs/samples/` (real API payloads carry account state) and `config/grid.json` are all
  gitignored.
- **Tracker client** uses `follow_redirects=False` so the bearer can never leak across a
  host redirect (the legacy `tarkovtracker.org/api/v2` host problem).
- **Token** is a pydantic `SecretStr`; the `PVE_` prefix is validated at load.
- **`GET /progress` schema is documented** after all: `https://api.tarkovtracker.org/openapi.json`
  (gateway v2.5.0) has full `ProgressResponse` models. `progress/models.py` is written from
  the spec; a copy lives in `docs/samples/openapi.json` (gitignored, re-fetch with curl).
  Ids in the payload are tarkov.dev ids, so they join straight to gamedata.
- **User-Agent is mandatory** on protected endpoints (5-200 chars). Client sends
  `tarkov-ops/<ver>`.

## 2026-09-09 — tarkovtracker.org, not tarkovtracker.io

- Owner's first account was on `tarkovtracker.io` (the older original). Its tokens are
  22-char unprefixed base62, its API has no PvE/PvP split, ignores `If-None-Match`, and
  sends no quota headers. TarkovMonitor treats it as a "legacy service".
- **Decision: `tarkovtracker.org` only.** Actively developed, PvE profile is first-class,
  public OpenAPI, TarkovMonitor's default. New `.org` account created 2026-09-09 with a
  `PVE_` token. The `.io` account is abandoned. No dual-tracker support; one source of truth.
- Verified live: `GET /token` → `gameMode=pve`, `GET /progress` → 200 with weak ETag,
  `If-None-Match` → 304. Quota headers present.

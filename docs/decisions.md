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

## 2026-10-04 — Phase 1: gamedata cache + needs engine (Alienware)

- **Repo now lives on the Alienware** at `D:/Claude/Projects/tarkov-ops`. `.env` and
  `docs/samples/` came over from Omarchy via Taildrop. TarkovMonitor and RatScanner are
  unpacked to `D:/Games/TarkovTools/` (portable, no installer).
- **Gamedata is a JSON file cache, not SQLite (yet).** `data/gamedata/<endpoint>.json` plus
  `<endpoint>_en.json`, `meta.json` holds `fetchedAt`; 12h staleness. The documents are
  small enough (~21 MB) to load in memory, and the needs engine is simpler against dicts.
  SQLite comes back when stash scans and verdict history need persistence.
- **Translation keys.** json.tarkov.dev stores names as keys (`"<id> Name"`,
  `hideout_area_13_name`); the `_en` overlay resolves them. Resolved once at load.
- **Token is optional in Settings** so `gamedata` commands run without one; the tracker
  client raises if it is missing.
- **Needs rules.** Item objectives = `giveItem` + `plantItem` (non-optional). `findItem` is
  skipped because it pairs with a `giveItem` for the same items. Multi-item objectives
  ("any 3 meds") are `any_of` needs, not pinned to one item. Currency is never a need.
  Collector items are their own "Kappa" reason. Urgency: active task > next hideout level >
  upcoming task (prereqs reachable, minPlayerLevel ≤ level+5) > later hideout level > Kappa.
  Objective `count` and hideout part `count` from the tracker are subtracted.
- **Tracker state on 2026-10-04:** level 14, `tasksProgress` empty, 5 hideout modules ticked.
  TarkovMonitor has never run against this account; Read Past Logs on the Alienware is the fix.

## 2026-10-05 — Field Card in repo; started tasks drive "active"

- **1.0 gates many tasks on story progress (`otherRequirements` globalVariable) and trader
  loyalty**, neither of which the tracker stores. Treating prereq-satisfied tasks as active gave
  202 "available" tasks. Now: **active = tasks TarkovMonitor saw accepted** (tracker entry, not
  complete, not failed); prereq-satisfied tasks without gates are "unlocked"; gated ones count only
  once started.
- **Field Card page lives in `publish/fieldcard_assets/`** and loads `data/{gear,loot,needs,routes}.json`
  at runtime, so a refresh republishes data files without touching the page.
  `tarkov-ops fieldcard build --level N` writes `out/fieldcard/`.
- **Hideout levels are overridable on the page** (browser-local) because the tracker only knows
  hand-ticked levels. Ticking on tarkovtracker.org remains the durable source.
- **Player level override** (`--level`) until the tracker level is set by hand; TarkovMonitor never
  writes level (verified in its source).
- Routes: open objectives grouped by map (Night Factory, GZ 21+, Labs Dark folded in);
  map-less objectives under "Anywhere / hideout".

## 2026-10-05 — Screenshot sync of active tasks

- Synced 62 active side tasks from in-game screenshots to the tracker via one `POST /progress/tasks`
  batch (`uncompleted` = open entry; the API has no "started" state). Rite of Passage → completed.
- **The tracker cascades `uncompleted` to follow-up tasks** (it created 20 extra open entries, e.g.
  Punisher Pt2). So "started" = open entry *whose own prerequisites are complete*. This reproduced
  the screenshot list exactly (62/62, no extras).

# tarkov-ops — session context (for a fresh Claude Code session)

Written 2026-09-11 on TC-ROGLaptop (Omarchy). Read this, then `docs/plan.md` (the original
build plan) and `docs/decisions.md`. Repo: https://github.com/wtcrowe4/tarkov-ops (public).

## Where the project is

**Phase 0 complete.** Phase 1 not started. Nothing runs as a service yet.

| Done | Where |
|---|---|
| uv project, Python 3.14, typer CLI, hatchling build | `pyproject.toml` |
| TarkovTracker client: bearer auth, ETag → 304, quota logging, raises on 401/429, no cross-host redirects | `src/tarkov_ops/progress/client.py` |
| Pydantic models from the gateway's OpenAPI spec | `src/tarkov_ops/progress/models.py` |
| `tarkov-ops progress token` / `progress raw` | `src/tarkov_ops/cli.py` |
| 6 tests, ruff clean | `tests/` |
| Decisions log | `docs/decisions.md` |

## Facts established (do not re-derive)

- **Tracker is tarkovtracker.org only.** Owner's first account was on tarkovtracker.io; that site has
  no PvE/PvP split, no quota headers, ignores `If-None-Match`, and TarkovMonitor treats it as legacy.
  `.io` account abandoned.
- `.org` API base `https://api.tarkovtracker.org`. Public spec at `/openapi.json` (gateway 2.5.0).
  `GET /progress` IS documented; the plan's claim that it isn't is outdated.
- Tokens: `PVE_` + 18 hex chars. Prefix decides game mode. User-Agent header is mandatory (5–200 chars).
  Free quota 1,000 reads/day, resets 00:00 UTC. Max 3 active tokens per account.
- Owner's `.org` profile (imported from tarkov.dev): level 14, USEC, **gameEdition 5 = Unheard**, PvE.
  Edition 5 auto-marks stash levels 1–4 and Cultist Circle as built. `displayName` is the owner's real
  name; never publish that field.
- **`tasksProgress` is empty.** The tarkov.dev import carries no quest state. Only TarkovMonitor
  (reads EFT logs) or manual clicks fill it.
- **TarkovMonitor never writes hideout.** Verified in its `TarkovTracker.cs`: only task
  started/complete/failed. Hideout levels are manual ticks on the site. Owner upgraded hideout in-game
  on 2026-09-11 and is ticking it on the site.
- `.env` on Omarchy holds `TARKOVTRACKER_TOKEN` (note `TarkovMonitor` is a *separate* token, see below).
- Payload size is trivial (2.6 KB with edition 5, grows with tasks). Poll at 5 min while EFT runs.

## Machines and phases

| Phase | Machine | Notes |
|---|---|---|
| 0–2: scaffold, gamedata, needs, routes, MCP | Laptop, any OS | pure API + SQLite |
| 3+: stash scanner, publish, service | Alienware, Windows-native Python | inbox, TarkovMonitor logs, Obsidian vault, EFT process are all there |

Laptop repo: `~/Projects/tarkov-ops` on Omarchy. Windows side of the laptop can clone to any path.
Alienware repo: `D:/Claude/Projects/tarkov-ops` (Windows filesystem, not WSL).
Monitor for Phase 3 calibration: Samsung Odyssey G9 super-ultrawide. Ask resolution + UI scale then.

## Immediate task on Windows (this week)

Install TarkovMonitor on the **laptop's Windows side** so task progress syncs while playing at the
beach. Full steps in `docs/handoff-windows-laptop.md`. Summary:
1. Launch EFT, let it update, confirm PvE profile.
2. tarkovtracker.org → Settings → API Tokens → new token: PvE, read + **write**, note
   `TarkovMonitor-laptop`. Copy it at creation (masked afterward).
3. Install TarkovMonitor ≥ 2.2.0 (github.com/the-hideout/TarkovMonitor/releases), Settings →
   TarkovTracker.org → import token, then **Read Past Logs** once. Leave it running while playing.
4. Verify later with `uv run tarkov-ops progress raw`: `tasksProgress` stops being empty.

## Next code work (Phase 1, laptop, any OS)

Per `docs/plan.md` §5.2 and §5.4:
- `gamedata/fetch.py`: pull `https://json.tarkov.dev/pve/{tasks,hideout,items,traders,barters,crafts,maps}`
  into SQLite (`data/tarkov-ops.db`), raw JSON + normalized tables, `fetchedAt` per endpoint, 12h refresh.
- Join tables: `task_required_items`, `task_prereqs`, `task_min_level`, `hideout_requirements`,
  `kappa_items`, `item_flea_banned`, `item_size`, `item_trader_sell_best`.
- `progress/poller.py` + `progress show`.
- `needs/engine.py` + `needs show`.
- Acceptance: `needs show` lists Intel Center L1+L2 items, Salty Dog ×4, Fierce Blow Sledgehammer,
  active Tour requirements, each with the correct reason. Needs real task progress to validate.

## Conventions

- Feature branch per phase, merge to main. Commit messages end with
  `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.
- Never log or print the token. `.env`, `data/`, `inbox/`, `out/`, `docs/samples/`, `config/grid.json`
  are gitignored.
- Read-only against the tracker in v1. Only TarkovMonitor writes.
- `requires-python >=3.13`, pinned 3.14 via uv. Drop to 3.13 if `opencv-python` wheels lag on Windows.
- Owner style: caveman mode, no filler, lead with the answer, explain commands before running them.

## Side projects touched (not tarkov, for awareness)

- KDE Connect on Omarchy, paired with Galaxy S23 Ultra (LAN). Tailscale on the phone is off.
- Beeper Desktop + `beeper-tui` (patched, `~/src/beeper-tui`) + `bp/bt/btg/msg` wrappers from
  `wtcrowe4/dev-config`. Third-party source checkouts live in `~/src` on Omarchy.
- Owner is weighing a personal Oracle Cloud free-tier server for a Beeper GroupMe bridge and other
  personal services. No usable GroupMe↔Matrix bridge exists as of 2026-09-11; it would be a from-scratch
  mautrix bridgev2 project. `bbctl` does accept third-party appservices.

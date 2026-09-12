# tarkov-ops — Claude Code build plan

Handoff for Claude Code on AlienwareDsktp. Read fully before writing code.
Date: 2026-09-07. Owner: Thomas (wtcrowe4). Personal project — commits to GitHub personal account, notes to `D:/Personal Vault`.

---

## 1. Goal

One local service that always knows, without manual upkeep:

1. **Where I am** — level, completed/active tasks, trader loyalty, hideout station levels. Source: TarkovTracker, fed automatically by TarkovMonitor reading EFT logs.
2. **What I need next** — every item still required by any active or upcoming task, any unbuilt hideout level, and Kappa/Collector. Source: `json.tarkov.dev`, diffed against progress.
3. **What I have** — stash contents, from screenshots I drop in a folder. No memory reading, no game hooks. Screenshots only.
4. **What to do** — keep/sell/hold verdict per item, next-task routing by map, stacked task runs, and the "why" for each.

Exposed as an MCP server so Claude (Code, Desktop, or Hermes/OpenClaw on the tailnet) can answer "what do I sell" and "what should I run on Customs" from live state. Also writes a dashboard note to Obsidian and pushes a summary to Slack.

**Constraints**
- PvE profile. Every game-data call uses `gameMode=pve`. Every tracker call uses the `PVE_` token.
- Zero game interaction beyond reading its own log files (TarkovMonitor does this; BSG has publicly not banned for it, 5+ years) and screenshots I take myself. Do not add anything that touches game memory, injects overlays, or automates input.
- Token lives in an env var. Never in the repo, never in the vault, never in a commit.

---

## 2. Environment

- Machine: AlienwareDsktp — Ultra 9 285K, 64GB, RTX 5080 16GB, Win11 Insider + WSL2 Ubuntu 24.04.
- Claude Code alias: `cca` (`claude --dangerously-skip-permissions`).
- EFT runs on Windows. TarkovMonitor and RatScanner are Windows apps. The service can run in WSL2 or Windows-native; **pick Windows-native Python** so the screenshot watcher, TarkovMonitor logs, and Ollama (Windows-native, `OLLAMA_HOST` bridged) are all on the same side with no path translation. Note the choice in README.
- Ollama available with vision-capable models (qwen-vl on the Ubuntu snap side; check what's pulled on Windows). Used only as fallback for low-confidence icon matches.
- Obsidian vault: `D:/Personal Vault` (git repo). Obsidian REST API plugin on port 27123 when Obsidian is open; Filesystem write to `D:/...` is the reliable fallback. Use the filesystem path.
- Slack: Hermes and OpenClaw are already wired in Socket Mode. Push summaries through whichever is simplest — a plain incoming webhook to a personal channel is fine for v1.
- Repo home: `D:/Claude/Projects/tarkov-ops`. GitHub: `wtcrowe4/tarkov-ops`, private.

### 2.1 Where this gets built vs. where it runs

**Build starts on the laptop (TC-ROGLaptop). Final runtime is the Alienware, Windows-native, on the Windows filesystem.** Git is the bridge.

| Phase | Machine | Why |
|---|---|---|
| 0–2 (scaffold, data, needs, routes, MCP) | Laptop, either OS | Pure API + SQLite. Nothing here cares about the host. |
| 3+ (stash scanner, publish, service) | Alienware, Windows | Screenshot inbox, TarkovMonitor logs, `EscapeFromTarkov.exe` process check, and the Obsidian vault are all on the Windows side. |

Rules:
- Repo lives at `D:/Claude/Projects/tarkov-ops` on the Alienware — **Windows filesystem, not WSL ext4.** A `watchdog` observer on `/mnt/d` from WSL is slow and unreliable, and every path the service touches (inbox, vault, EFT process) is Windows-native.
- On the laptop, clone wherever is convenient. If on Omarchy, that's fine for Phases 0–2. If on Windows, mirror the `D:/Claude/Projects/` layout so paths in `.env.example` transfer.
- Windows-native Python 3.12 on the Alienware. Don't depend on WSL for the runtime.
- `.env` is per-machine and never committed. The laptop `.env` needs only `TARKOVTRACKER_TOKEN`, `TARKOVTRACKER_BASE`, `TARKOV_JSON_BASE`, `GAME_MODE` for Phases 0–2. The rest gets filled in on the Alienware.
- Feature-branch workflow, MR to main. Each phase is its own branch.
- **Handoff point:** when Phase 2 acceptance passes on the laptop, push, clone to the Alienware, install TarkovMonitor there, and continue. Note the handoff in `docs/decisions.md`.

---

## 3. Data sources — verified 2026-09-07

### 3.1 TarkovTracker progress API (my state)

- Base: `https://api.tarkovtracker.org` (clean paths; `/api/v2/*` also accepted). The old `tarkovtracker.org/api/v2/*` host is deprecated — do not use it; .NET-style clients drop `Authorization` on the cross-host redirect and 401.
- Auth: `Authorization: Bearer $TARKOVTRACKER_TOKEN`. Token is prefixed `PVE_`. The prefix is cosmetic; the token's stored game mode decides which progress blob it reads/writes. Legacy `tt_` tokens are rejected.
- Endpoints known from docs: `GET /progress`, `GET /team/progress`, `POST /progress/task/{taskId}`. **The response schema for `GET /progress` is not fully documented — call it once, dump the JSON to `docs/samples/progress.json`, and write the Pydantic model from the real payload.** Do not guess field names.
- `GET /progress` returns a weak `ETag` and `Cache-Control: private, max-age=15`. Always send `If-None-Match`; a `304` costs quota but not bandwidth.
- Quota is per account, not per token. **Free tier: 1,000 reads/day, 100 writes/day**, resets 00:00 UTC. Headers `X-RateLimit-Limit/Remaining/Reset` on 200/304; `429` + `Retry-After` when exhausted. Poll at ≥60s. **Set the poller to 5 minutes (288 reads/day) and stop polling when EFT isn't running** (TarkovMonitor or a process check tells you).
- Max 3 active tokens per account, 3 creates/hour. I've created one already. Don't create more programmatically.
- Writes: only TarkovMonitor should write task completions. This service is read-only against the tracker in v1. If a write path is added later, it's for manual corrections only, behind an explicit CLI flag.

### 3.2 TarkovMonitor (log → tracker, automatic)

- Repo: `github.com/the-hideout/TarkovMonitor` (also mirrored under `tarkovtracker-org`).
- Reads EFT log files, auto-updates task progress on TarkovTracker via the token. Also gives raid-start/match audio cues and scav cooldown timers.
- Setup: install, paste the `PVE_` token into its settings, click Test Token. Confirm it's pointed at `api.tarkovtracker.org` (newer releases are; older ones hit the legacy host).
- **This is the piece that removes manual upkeep.** If it's not running, nothing else is current. Add a health check: if tracker `updatedAt` hasn't moved in >24h while EFT has run, alert.

### 3.3 json.tarkov.dev (game data)

Static JSON, no auth. Catalog at `https://json.tarkov.dev/endpoints`. The old `api.tarkov.dev` GraphQL endpoint is deprecated and unstable — do not use it.

| Endpoint | Path (gameMode=pve) | Contains |
|---|---|---|
| tasks | `/pve/tasks` | tasks, quest items, achievements, prestige |
| hideout | `/pve/hideout` | stations, levels, requirements, crafts |
| items | `/pve/items` | items, categories, flea data, armor materials, player levels, skills |
| traders | `/pve/traders` | traders, loyalty levels, cash offers |
| barters | `/pve/barters` | trader barters |
| crafts | `/pve/crafts` | hideout crafts |
| maps | `/pve/maps` | maps, bosses, loot containers, extracts |
| prices | `/pve/prices/{itemId}` | flea price history per item |
| status | `/status` | EFT server status |

Translated endpoints serve an English base plus `{endpoint}_{lang}` overlays. English only for v1 — read the base document.

Cache locally in SQLite. Refresh on a 12h timer and on demand. Store `fetchedAt` per endpoint. Everything downstream reads from cache, never from the network in the request path.

### 3.4 tarkov-data-overlay

`github.com/tarkovtracker-org/tarkov-data-overlay` — community corrections layered over tarkov.dev task data. Optional for v1. If task requirements look wrong, this is the first place to check before filing anything.

### 3.5 Stash contents — there is no API

No tool exposes stash inventory. Options evaluated:

- **RatScanner** (`github.com/tarkovtracker-org/RatScanner`, v3.9.x, Jan 2026): click-to-scan single items via screenshot + icon matching. Has TarkovTracker integration and shows Kappa-required counts. **It does not export a full inventory** and it's per-click, so it doesn't solve bulk stash reads. Useful as a reference implementation for icon matching only.
- **RatEye** (`github.com/tarkovtracker-org/RatEye`) + **RatScannerData / EfT-Icons**: the image-processing library and icon dataset RatScanner uses. This is the correct foundation for a bulk scanner.

**Approach: build a bulk stash scanner from screenshots.** Details in §5.3.

---

## 4. Architecture

```
EFT (Windows)
 ├─ logs ──► TarkovMonitor ──► api.tarkovtracker.org  (task progress, auto)
 └─ screenshots (F12 / PrtSc) ──► D:/Claude/Projects/tarkov-ops/inbox/*.png

tarkov-ops service (Python 3.12, Windows-native)
 ├─ progress/    poll GET /progress every 5m (ETag), normalize → SQLite
 ├─ gamedata/    fetch json.tarkov.dev pve/* every 12h → SQLite
 ├─ stash/       watch inbox/, grid-detect, icon-match, VLM fallback → SQLite
 ├─ needs/       diff(gamedata × progress) → required items with reasons
 ├─ verdicts/    join(needs × stash × prices) → keep / hold / sell + why
 ├─ routes/      active tasks grouped by map, stacked-run suggestions
 ├─ mcp/         FastMCP server exposing the above as tools
 └─ publish/     Obsidian note + HTML dashboard + Slack summary
```

Single SQLite file `data/tarkov-ops.db`. Tables: `items`, `tasks`, `task_objectives`, `hideout_levels`, `hideout_requirements`, `traders`, `barters`, `crafts`, `progress_snapshot`, `stash_scan`, `stash_item`, `verdict`, `fetch_log`.

Stack: Python 3.12, `httpx`, `pydantic`, `sqlite3`/`sqlmodel`, `opencv-python`, `watchdog`, `mcp` (FastMCP), `typer` for CLI, `apscheduler` for timers. No web framework needed in v1 — the MCP server is the API. If a dashboard needs serving, `python -m http.server` on the output folder is enough.

---

## 5. Components

### 5.1 `progress/` — my state

1. `client.py`: httpx client, bearer auth, ETag cache, honors `Retry-After`, logs `X-RateLimit-Remaining` every call. Raise loudly on 401 (token/mode mismatch) and 429.
2. First run: `GET /progress`, save raw to `docs/samples/progress.json`. **Write `models.py` from that file.** Expected shape includes at least: player level, per-task status (complete/active/failed), hideout module levels, trader loyalty. Confirm from the payload.
3. Normalize into `progress_snapshot` (one row per poll, keep last 30 days) plus current-state views.
4. Scheduler: every 5 min while `EscapeFromTarkov.exe` is running; every 60 min otherwise. Never below 60s.
5. `tarkov-ops progress show` CLI: level, active tasks, hideout levels, trader LL, last-updated age.

### 5.2 `gamedata/` — reference data

1. Fetch all `pve/*` endpoints from §3.3, store raw JSON + normalized tables.
2. Build the join tables that the needs engine depends on:
   - `task_required_items(task_id, item_id, count, found_in_raid: bool, objective_id)`
   - `task_prereqs(task_id, requires_task_id)` and `task_min_level`
   - `hideout_requirements(station_id, level, item_id, count)` plus station-level prereqs
   - `kappa_items(item_id)` — items required by The Collector
   - `item_flea_banned(item_id)`, `item_size(w, h)`, `item_trader_sell_best(item_id, trader, price)`
3. 12h refresh. `tarkov-ops gamedata refresh` for manual.

### 5.3 `stash/` — screenshot ingestion

The hard part. Build it in three stages and stop when accuracy is good enough.

**Stage A — grid detection.**
- Stash grid is fixed-pitch. Take one calibration screenshot at my resolution (confirm: 1440p or 4K — ask, don't assume) with the stash fully open and scrolled to top.
- Detect the grid: cell pitch in px, origin offset, columns (10 for stash). Store as `config/grid.json`. Re-run calibration if the game resolution changes.
- Multi-page: I'll scroll and take several screenshots. Detect overlap by hashing rows; de-duplicate.
- Known problem from RatScanner FAQ: the bright light at the top-center of the stash screen ruins matches in the top-left region. Mitigate by cropping the hideout backdrop and normalizing brightness per cell before matching.

**Stage B — icon matching (deterministic).**
- Pull the icon set from RatScannerData / EfT-Icons (check current repo name under `tarkovtracker-org`; icons keyed by item id).
- For each grid cell: crop, detect occupied vs empty, detect multi-cell items by shared border color, extract the icon region.
- Match with OpenCV template matching or ORB descriptors against the icon set. Emit `(item_id, confidence, cell_x, cell_y, w, h)`.
- Read the stack count / durability text in the cell corner with lightweight OCR (Tesseract or `rapidocr`). Read the FIR checkmark glyph (small overlay, top-right) — this matters for verdicts.
- Keys and small attachments mismatch often (RatScanner FAQ). Route confidence < threshold to Stage C.

**Stage C — VLM fallback.**
- For low-confidence cells, send the crop plus the top-5 candidate names to a local vision model via Ollama (qwen-vl class). Prompt: "Which of these items is shown? Answer with the exact name or UNKNOWN." Never let the VLM invent names outside the candidate list.
- If still UNKNOWN, write to `stash_unresolved` and surface in the dashboard for a manual tap.

**Container handling.** Junk boxes, cases, and rigs show as one icon in the stash. To inventory their contents I'll open each and screenshot it. Name the screenshot `container-<name>-<n>.png` and the watcher will attribute contents to that container. Config a list of known containers.

**Output:** `stash_scan(id, taken_at, resolution, page, container)` and `stash_item(scan_id, item_id, count, fir, cell_x, cell_y, confidence, source: match|vlm|manual)`. The latest full scan replaces the previous "current stash" view. `tarkov-ops stash show`, `tarkov-ops stash unresolved`.

### 5.4 `needs/` — what I still need

Compute from gamedata × progress. One row per (item, reason):

- **Task items**: for every task that is active, or not yet unlocked but whose prereqs are ≤ 5 levels away, sum required items. Carry `found_in_raid`. Include the task name and trader.
- **Hideout items**: for every station level not yet built, sum requirements. Include station and level.
- **Kappa/Collector**: every item on the list I don't yet have FIR.
- **Barters worth holding**: barters at my current or next trader LL where the barter output beats the trader sell price of the inputs. Flag inputs as "hold for barter".

Subtract counts already handed in where the tracker exposes it (objective-level progress). Result: `needs(item_id, count_needed, fir_required, reason, urgency)` where urgency = active task > hideout next level > upcoming task > kappa.

### 5.5 `verdicts/` — keep / hold / sell

For every item in the current stash scan:

```
if item in never_sell (kappa, streamer/purple, flea_banned & needed): KEEP
elif needs[item] > 0: KEEP up to count_needed; surplus → next rule
elif flea_banned: SELL (trader, best price)   # can't hold for flea
elif player_level < 15 and flea_price / best_trader_price >= 2.0 and slots <= 4: HOLD
else: SELL to best_trader
```

Attach: reason string, best trader + price, flea price if any, slots freed. Rank the SELL list by slots-freed-per-click descending — that's the actual stash relief order.

Also emit `space_report`: total slots, occupied, slots freed if all SELL verdicts executed.

### 5.6 `routes/` — where to go next

- Group active + about-to-unlock tasks by map. Include `minPlayerLevel`, required keys, required items I do or don't have, and whether it needs a kill count or a location visit.
- Emit "stacked runs": for each map, the set of tasks completable in one raid, ordered by geography where the data has coordinates (tarkov.dev has objective locations for many tasks). Flag tasks blocked by a missing key or item.
- Detect key spawns for keys I'm missing and surface them.

### 5.7 `mcp/` — expose everything

FastMCP server, stdio transport, plus an HTTP/SSE transport bound to the tailnet so Hermes/OpenClaw on other machines can call it. Tools:

| Tool | Returns |
|---|---|
| `progress_summary()` | level, active tasks, hideout levels, trader LL, tracker freshness |
| `needs(reason=None)` | required items with reasons and counts |
| `stash_current()` | latest scan, grouped by container |
| `stash_unresolved()` | cells needing manual ID |
| `verdicts(kind=None)` | keep/hold/sell with reasons, sell ranked by slots freed |
| `item_lookup(name)` | item card: uses, needs, best sell, flea, flea-banned, size |
| `next_runs(map=None)` | stacked task runs per map with blockers |
| `key_spawns(key_name)` | where a missing key spawns |
| `refresh(what)` | force gamedata / progress / stash refresh |

Register it in `claude-config` so `cca` on the Alienware has it by default. Also add it to the Claude Desktop config.

### 5.8 `publish/`

- **Obsidian**: write `D:/Personal Vault/Tarkov/Dashboard.md` on every verdict recompute. Sections: state, needs by urgency, sell list ranked, next runs, unresolved cells. Overwrite in place; append a one-line entry to `D:/Personal Vault/Tarkov/Log.md` per session. Never write the token.
- **HTML dashboard**: `out/dashboard.html`, static, same content as the Obsidian note but with the filter/search UI. Serve on the tailnet if wanted.
- **Slack**: on every completed stash scan, post: slots freed available, top 10 sells, next stacked run. On progress change (level-up, task complete): one line. Use an incoming webhook via `SLACK_WEBHOOK_URL`.

---

## 6. Build order

Ship each phase working before starting the next. Commit per phase on a feature branch, MR to main.

**Phase 0 — scaffold (1 session)**
- Repo, `pyproject.toml`, `uv` or `venv`, `.env.example`, `.gitignore` (`.env`, `data/`, `inbox/`, `docs/samples/`), README with the constraints from §1.
- `tarkov-ops` CLI skeleton with `typer`.
- Confirm token works: `tarkov-ops progress raw` → saves `docs/samples/progress.json`. Stop and show me the shape before modeling.

**Phase 1 — data (1–2 sessions)**
- gamedata fetch + normalize + join tables.
- progress model + poller + `progress show`.
- needs engine + `needs show`.
- Acceptance: `needs show` lists Intelligence folder ×4 (Intel Center L1+L2), Salty Dog ×4, Fierce Blow Sledgehammer, and the active Tour requirements, each with the correct reason.

**Phase 2 — routes + MCP (1 session)**
- routes engine, MCP server with the tools in §5.7, registered in `claude-config`.
- Acceptance: from `cca`, "what should I run on Customs" returns a stacked list with blockers.

**Phase 3 — stash scanner (2–4 sessions, the risky one)**
- Stage A calibration on my real screenshots. Ask me for 3 screenshots first: stash top, stash scrolled, one junk box open.
- Stage B icon matching. Measure accuracy on a labeled sample of ~50 cells. Target ≥90% top-1 before adding Stage C.
- Stage C VLM fallback only for the remainder.
- verdicts engine + `verdicts show` + `space_report`.
- Acceptance: a full stash scan produces a sell list that frees ≥100 slots and contains zero items from the never-sell set.

**Phase 4 — publish + automation (1 session)**
- Obsidian note, HTML dashboard, Slack.
- Install as a Windows service or a Task Scheduler job at logon. Watchdog on TarkovMonitor freshness.

**Phase 5 — polish (ongoing)**
- Barter hold logic, key spawn lookup, objective-level location routing, PvP token support if ever needed.

---

## 7. Repo layout

```
tarkov-ops/
  README.md
  pyproject.toml
  .env.example
  config/
    grid.json            # calibration, generated
    containers.yaml      # named containers to scan
    never_sell.yaml      # manual overrides
  src/tarkov_ops/
    cli.py
    settings.py          # env, paths
    db.py
    progress/  client.py models.py poller.py
    gamedata/  fetch.py normalize.py
    stash/     watch.py grid.py match.py vlm.py ocr.py
    needs/     engine.py
    verdicts/  engine.py
    routes/    engine.py
    mcp/       server.py
    publish/   obsidian.py html.py slack.py
  data/                  # sqlite, gitignored
  inbox/                 # screenshots drop, gitignored
  out/                   # dashboard.html
  docs/
    samples/             # real API payloads, gitignored
    decisions.md         # ADR-style notes
  tests/
```

---

## 8. Secrets and config

`.env` (never committed):

```
TARKOVTRACKER_TOKEN=PVE_...
TARKOVTRACKER_BASE=https://api.tarkovtracker.org
TARKOV_JSON_BASE=https://json.tarkov.dev
GAME_MODE=pve
OLLAMA_HOST=http://localhost:11434
OLLAMA_VISION_MODEL=            # set after checking what's pulled
OBSIDIAN_VAULT=D:/Personal Vault
SLACK_WEBHOOK_URL=
INBOX_DIR=D:/Claude/Projects/tarkov-ops/inbox
EFT_PROCESS_NAME=EscapeFromTarkov.exe
```

Never log the token. Redact `Authorization` in any debug output.

---

## 9. Risks and open questions — ask before assuming

1. **`GET /progress` schema** is not in the public docs. Dump it first, model second.
2. **Screen resolution and UI scale** for grid calibration — ask me. Don't hardcode 1080p.
3. **Icon dataset location** — RatScannerData vs EfT-Icons vs RatEye bundled data. Check `tarkovtracker-org` for the current one and note the choice in `docs/decisions.md`.
4. **FIR detection** from screenshots — the checkmark glyph is small. If OCR/matching is unreliable, fall back to "FIR unknown" and let the verdict engine treat unknown as not-FIR for task items (conservative: keep).
5. **Quota** — the free tier's 1,000 reads/day is plenty at 5-minute polling, but if I run Hermes/OpenClaw polling the same token, they share the account quota. One poller only; everything else reads from SQLite.
6. **Flea prices in PvE** — tarkov.dev serves PvE prices under `gameMode=pve`. Confirm the `prices` endpoint has PvE data; if sparse, fall back to trader sell prices for HOLD decisions.
7. **Windows-native vs WSL** — plan says Windows-native for path and process reasons. If a dependency (OpenCV, mcp) is painful on Windows Python, say so before switching.

---

## 10. Definition of done (v1)

- TarkovMonitor running and pushing task progress with no manual clicks.
- `tarkov-ops progress show` matches the in-game state within 5 minutes of a task completing.
- `tarkov-ops needs show` is correct for Intel Center, Tour, and all active tasks.
- Dropping stash screenshots into `inbox/` produces a keep/hold/sell list within 60 seconds, with ≥90% item ID accuracy and zero never-sell items on the sell list.
- MCP tools answer from `cca` and from Claude Desktop.
- `D:/Personal Vault/Tarkov/Dashboard.md` updates on every recompute.
- Slack gets a summary after each scan.

# tarkov-ops

Local service that always knows, without manual upkeep:

1. **Where I am** — level, tasks, trader loyalty, hideout. From TarkovTracker, fed by TarkovMonitor reading EFT logs.
2. **What I need next** — items for active/upcoming tasks, unbuilt hideout levels, Kappa. From `json.tarkov.dev` diffed against progress.
3. **What I have** — stash contents from screenshots dropped in a folder.
4. **What to do** — keep/hold/sell per item, task routing by map, stacked runs, with reasons.

Exposed as an MCP server, plus an Obsidian dashboard note and Slack summaries.

## Constraints

- **PvE profile only.** Every game-data call uses `gameMode=pve`; the tracker token is `PVE_`.
- **Zero game interaction** beyond reading EFT's own log files (via TarkovMonitor) and
  screenshots taken by hand. No memory reads, no overlays, no input automation.
- **Token lives in `.env` only.** Never in the repo, vault, logs, or a commit.
- **Read-only against TarkovTracker** in v1. Only TarkovMonitor writes.

## Where it runs

Built on the laptop for Phases 0-2 (pure API + SQLite). Final runtime is the Alienware,
**Windows-native Python**, repo at `D:/Claude/Projects/tarkov-ops`, so the screenshot
inbox, TarkovMonitor logs, EFT process check and Obsidian vault share one filesystem.

## Setup

```sh
uv sync
cp .env.example .env   # fill in TARKOVTRACKER_TOKEN
uv run tarkov-ops progress raw
```

## Layout

```
src/tarkov_ops/
  cli.py settings.py db.py
  progress/  gamedata/  stash/  needs/  verdicts/  routes/  mcp/  publish/
config/      grid.json (generated), containers.yaml, never_sell.yaml
data/        sqlite (gitignored)
inbox/       screenshot drop (gitignored)
docs/        decisions.md, samples/ (gitignored)
```

See `docs/decisions.md` for the why behind non-obvious choices.

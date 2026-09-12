# Handoff: TarkovMonitor on TC-ROGLaptop (Windows side)

Written 2026-09-11 from the Omarchy session. Goal: run TarkovMonitor on the laptop's
Windows install for the beach week so task progress lands on tarkovtracker.org
automatically. Full Alienware setup comes after.

## Before anything
- Launch EFT once. Let the launcher update the game and run one raid or at least
  reach the main menu so the log folder exists.
- Confirm the profile in-game is **PvE**.

## Token
Make a **second** tarkovtracker.org token for TarkovMonitor. Do not reuse the one in
Omarchy's `.env` (different disk, and one token per tool is cleaner). Account cap is
3 active tokens; 1 is in use.
- tarkovtracker.org → Settings → API Tokens → create: game mode **PvE**, permissions
  read progress + **write progress**, note `TarkovMonitor-laptop`.
- It will start with `PVE_`. Copy it once at creation; the list masks it afterward.

## Install
1. https://github.com/the-hideout/TarkovMonitor/releases → latest (2.2.0.0 or newer).
   Installer is the `.exe`; in-app updates work from 2.2.0 on.
2. Run it. Settings → TarkovTracker.org → **Import token** → paste. It verifies the
   token and reads the game mode from the `PVE_` prefix.
3. Settings → point it at the EFT install if it did not auto-detect
   (`C:\Battlestate Games\EFT`, or wherever the launcher put it).
4. **Read Past Logs** once. That replays existing EFT logs into the tracker.
5. Leave it running while playing. It also gives raid-start cues and scav timers.

## Verify (from any machine with the repo)
```sh
uv run tarkov-ops progress raw
```
`tasksProgress` should stop being empty after the first task completes with
TarkovMonitor running. If it stays empty after a raid, check TarkovMonitor's log
pane for a 401 (wrong mode or token).

## Hideout
TarkovMonitor never writes hideout levels. Tick built stations on tarkovtracker.org
by hand. One click per upgrade after the initial catch-up.

## Not in scope this week
Stash scanner, Obsidian, Slack, service install. Those are Phase 3+ on the Alienware.

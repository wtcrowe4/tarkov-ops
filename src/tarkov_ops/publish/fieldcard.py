"""Data files for the Field Card page: needs.json and routes.json.

The page computes hideout needs itself from per-station levels the player can override,
because the tracker only knows hideout levels that were ticked by hand on the site.
No account fields (displayName, userId) are ever written.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tarkov_ops.gamedata.model import GameData
from tarkov_ops.needs.engine import Urgency, compute_needs
from tarkov_ops.progress.models import ProgressData
from tarkov_ops.routes.engine import compute_routes, load_map_names, routes_to_json


def build_needs_and_routes(
    gd: GameData, progress: ProgressData, data_dir: Path, level: int | None = None
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    tracker_level = progress.playerLevel
    if level is not None:
        progress = progress.model_copy(update={"playerLevel": max(level, tracker_level)})
    res = compute_needs(gd, progress, include_kappa=True)
    st = res.task_state
    assert st is not None

    task_items = []
    for n in res.items:
        srcs = [s for s in n.sources if s.kind != "hideout"]
        if not srcs:
            continue
        task_items.append(
            {
                "id": n.item_id,
                "name": n.name,
                "sources": [
                    {
                        "label": s.label,
                        "count": s.count,
                        "fir": s.fir,
                        "urgency": int(s.urgency),
                        "kind": s.kind,
                    }
                    for s in srcs
                ],
            }
        )

    built = progress.built_module_ids
    parts = {p.id: int(p.count) for p in progress.hideoutPartsProgress}
    parts_done = {p.id for p in progress.hideoutPartsProgress if p.complete}
    stations = []
    for sid, stn in gd.hideout.items():
        levels = sorted(stn.get("levels", []), key=lambda lv: lv["level"])
        tracker_lvl = max((lv["level"] for lv in levels if lv["id"] in built), default=0)
        stations.append(
            {
                "id": sid,
                "name": gd.station_names.get(sid, sid),
                "trackerLevel": tracker_lvl,
                "maxLevel": max((lv["level"] for lv in levels), default=0),
                "levels": [
                    {
                        "level": lv["level"],
                        "items": [
                            {
                                "id": r["item"],
                                "name": gd.item_name(r["item"]),
                                "count": max(
                                    0,
                                    0
                                    if r["id"] in parts_done
                                    else int(r["count"]) - parts.get(r["id"], 0),
                                ),
                                "fir": bool((r.get("attributes") or {}).get("foundInRaid")),
                            }
                            for r in lv.get("itemRequirements", [])
                            if not (gd.items.get(r["item"]) and gd.items[r["item"]].is_currency)
                        ],
                        "stations": [
                            [gd.station_names.get(x["station"], x["station"]), x["level"]]
                            for x in lv.get("stationLevelRequirements", [])
                        ],
                    }
                    for lv in levels
                ],
            }
        )
    stations.sort(key=lambda s: s["name"])

    name = gd.task_names.get
    needs = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "trackerLevel": tracker_level,
        "levelUsed": progress.playerLevel,
        "tasksDone": len(progress.completed_task_ids),
        "started": sorted(name(t, t) for t in st.started),
        "unlocked": sorted(name(t, t) for t in st.available - st.started),
        "upcomingCount": len(st.upcoming),
        "urgencyLabels": {int(u): u.label for u in Urgency},
        "taskItems": task_items,
        "anyOf": [
            {
                "label": a.label,
                "task": a.task,
                "count": a.count,
                "fir": a.fir,
                "urgency": int(a.urgency),
            }
            for a in res.any_of
            if a.urgency in (Urgency.ACTIVE_TASK, Urgency.UPCOMING_TASK)
        ],
        "stations": stations,
    }
    routes = compute_routes(gd, progress, st, load_map_names(data_dir))
    started_names = {name(t, t) for t in st.started}
    rj = routes_to_json(routes)
    for m in rj:
        for t in m["tasks"]:
            t["started"] = t["name"] in started_names
    return needs, rj

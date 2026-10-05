"""Where to go next: available tasks grouped by map, so one raid can clear several.

A task lands under every map one of its open objectives happens on. Objectives with no map
(hand-ins, trader levels, skills) go under "Anywhere / hideout". Night Factory, Ground Zero 21+
and The Lab (Dark) fold into their base map.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tarkov_ops.gamedata.model import GameData
from tarkov_ops.needs.engine import TaskState
from tarkov_ops.progress.models import ProgressData

ANYWHERE = "Anywhere / hideout"
MAP_ALIASES = {
    "Night Factory": "Factory",
    "Ground Zero 21+": "Ground Zero",
    "The Lab (Dark)": "The Lab",
}
SKIP_MAPS = {"Ground Zero Tutorial"}
IN_RAID_TYPES = {
    "visit",
    "shoot",
    "extract",
    "findQuestItem",
    "plantItem",
    "plantQuestItem",
    "mark",
    "findItem",
    "useItem",
    "experience",
    "buildWeapon",
}


@dataclass
class RouteObjective:
    text: str
    type: str
    count: int
    done: int
    optional: bool


@dataclass
class RouteTask:
    id: str
    name: str
    trader: str
    kappa: bool
    lightkeeper: bool
    wiki: str | None
    objectives: list[RouteObjective] = field(default_factory=list)
    keys: list[str] = field(default_factory=list)


def load_map_names(data_dir: Path) -> dict[str, str]:
    d = data_dir / "gamedata"
    maps = json.loads((d / "maps.json").read_text(encoding="utf-8"))["data"]["maps"]
    en = json.loads((d / "maps_en.json").read_text(encoding="utf-8"))["data"]
    out = {}
    for mid, m in maps.items():
        name = en.get(m["name"], m["name"])
        if name in SKIP_MAPS:
            continue
        out[mid] = MAP_ALIASES.get(name, name)
    return out


def compute_routes(
    gd: GameData,
    progress: ProgressData,
    state: TaskState,
    map_names: dict[str, str],
) -> dict[str, list[RouteTask]]:
    obj_done = {o.id for o in progress.taskObjectivesProgress if o.complete}
    obj_counts = progress.objective_counts
    by_map: dict[str, dict[str, RouteTask]] = {}

    for tid in state.available:
        t = gd.tasks[tid]
        keys_by_map: dict[str, list[str]] = {}
        for nk in t.get("neededKeys") or []:
            mname = map_names.get(nk.get("map", ""), ANYWHERE)
            keys_by_map.setdefault(mname, []).extend(gd.item_name(k) for k in nk.get("keys", []))
        for o in t.get("objectives", []):
            if o["id"] in obj_done:
                continue
            maps = {map_names[m] for m in (o.get("maps") or []) if m in map_names}
            if not maps and o.get("type") in IN_RAID_TYPES and t.get("map") in map_names:
                maps = {map_names[t["map"]]}
            if not maps:
                maps = {ANYWHERE}
            count = int(o.get("count") or 1)
            ro = RouteObjective(
                text=gd.objective_text.get(o["id"], o["id"]),
                type=o.get("type", ""),
                count=count,
                done=int(obj_counts.get(o["id"], 0)),
                optional=bool(o.get("optional")),
            )
            for mname in maps:
                rt = by_map.setdefault(mname, {}).get(tid)
                if rt is None:
                    rt = RouteTask(
                        id=tid,
                        name=gd.task_names.get(tid, tid),
                        trader=gd.trader_name(t.get("trader")),
                        kappa=bool(t.get("kappaRequired")),
                        lightkeeper=bool(t.get("lightkeeperRequired")),
                        wiki=t.get("wikiLink"),
                        keys=sorted(set(keys_by_map.get(mname, []))),
                    )
                    by_map[mname][tid] = rt
                rt.objectives.append(ro)

    ordered = sorted(by_map.items(), key=lambda kv: (kv[0] == ANYWHERE, -len(kv[1]), kv[0]))
    return {m: sorted(ts.values(), key=lambda r: r.name) for m, ts in ordered}


def routes_to_json(routes: dict[str, list[RouteTask]]) -> list[dict[str, Any]]:
    return [
        {
            "map": m,
            "tasks": [
                {
                    "name": r.name,
                    "trader": r.trader,
                    "kappa": r.kappa,
                    "lightkeeper": r.lightkeeper,
                    "wiki": r.wiki,
                    "keys": r.keys,
                    "objectives": [
                        {
                            "text": o.text,
                            "type": o.type,
                            "count": o.count,
                            "done": o.done,
                            "optional": o.optional,
                        }
                        for o in r.objectives
                    ],
                }
                for r in tasks
            ],
        }
        for m, tasks in routes.items()
    ]

"""What items do I still need?

Joins gamedata (tasks, hideout) with TarkovTracker progress and returns one record per
item, each with the reasons (task / hideout level / Kappa) and how many are still owed.

Urgency order: active task > next hideout level > upcoming task > later hideout level > Kappa.
Objectives that accept any one of several items (e.g. "hand over 3 medical items") can't
be pinned to one item, so they are returned separately as `any_of` needs.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from tarkov_ops.gamedata.model import GameData
from tarkov_ops.progress.models import ProgressData

COLLECTOR_NAME = "collector"
ITEM_OBJECTIVES = {"giveItem", "plantItem"}  # findItem is paired with giveItem; skip it


class Urgency(IntEnum):
    ACTIVE_TASK = 1
    HIDEOUT_NEXT = 2
    UPCOMING_TASK = 3
    HIDEOUT_LATER = 4
    KAPPA = 5

    @property
    def label(self) -> str:
        return {
            1: "active task",
            2: "next hideout level",
            3: "upcoming task",
            4: "later hideout level",
            5: "Kappa (Collector)",
        }[self.value]


@dataclass
class NeedSource:
    kind: str  # "task" | "hideout" | "kappa"
    label: str  # "Gunsmith - Part 2 (Mechanic)" / "Medstation L2"
    count: int
    fir: bool
    urgency: Urgency
    ref_id: str  # task id or station-level id


@dataclass
class ItemNeed:
    item_id: str
    name: str
    sources: list[NeedSource] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(s.count for s in self.sources)

    @property
    def fir_total(self) -> int:
        return sum(s.count for s in self.sources if s.fir)

    @property
    def urgency(self) -> Urgency:
        return min(s.urgency for s in self.sources)


@dataclass
class AnyOfNeed:
    label: str  # objective text
    task: str
    count: int
    fir: bool
    urgency: Urgency
    item_ids: list[str]


@dataclass
class TaskState:
    done: set[str]
    available: set[str]  # started (per tracker) + probably unlocked
    upcoming: set[str]
    started: set[str] = field(default_factory=set)  # accepted in game, seen by TarkovMonitor


@dataclass
class NeedsResult:
    items: list[ItemNeed]
    any_of: list[AnyOfNeed]
    task_state: TaskState | None
    player_level: int | None


# ---------------------------------------------------------------- task state


def _req_ok(req: dict[str, Any], done: set[str], failed: set[str], open_: set[str]) -> bool:
    status = set(req.get("status") or ["complete"])
    tid = req["task"]
    if "complete" in status and tid in done:
        return True
    if "failed" in status and tid in failed:
        return True
    return "active" in status and tid in open_


def compute_task_state(gd: GameData, progress: ProgressData, level_window: int = 5) -> TaskState:
    done = progress.completed_task_ids
    failed = progress.failed_task_ids
    level = progress.playerLevel
    faction = progress.pmcFaction

    eligible = {
        tid: t for tid, t in gd.tasks.items() if t.get("factionName", "Any") in ("Any", faction)
    }
    open_tasks = {tid for tid in eligible if tid not in done and tid not in failed}
    # Tasks TarkovMonitor saw you accept: the tracker holds them as not complete, not failed.
    # Tasks accepted in game: open tracker entries whose own prerequisites are done. Marking a
    # task "uncompleted" on the tracker also creates open entries for its follow-ups, so an open
    # entry alone doesn't mean accepted.
    started = {
        t.id
        for t in progress.tasksProgress
        if not t.complete
        and not t.failed
        and t.id in eligible
        and all(
            r["task"] in done
            for r in eligible[t.id].get("taskRequirements", [])
            if "complete" in (r.get("status") or ["complete"])
        )
    }

    # available: started, or prerequisites met and level reached. 1.0 also gates tasks on story
    # progress (globalVariable) and trader loyalty, which the tracker doesn't record, so tasks
    # with those gates only count once started. Iterate because "active" prereqs chain.
    available: set[str] = set(started)
    changed = True
    while changed:
        changed = False
        for tid in open_tasks - available:
            t = eligible[tid]
            if (t.get("minPlayerLevel") or 0) > level:
                continue
            if t.get("otherRequirements") or t.get("traderRequirements"):
                continue
            if all(_req_ok(r, done, failed, available) for r in t.get("taskRequirements", [])):
                available.add(tid)
                changed = True

    # upcoming: within the level window and every prerequisite is done, available or upcoming
    reachable = available | done
    upcoming: set[str] = set()
    changed = True
    while changed:
        changed = False
        for tid in open_tasks - available - upcoming:
            t = eligible[tid]
            if (t.get("minPlayerLevel") or 0) > level + level_window:
                continue
            ok = all(
                r["task"] in reachable or r["task"] in upcoming
                for r in t.get("taskRequirements", [])
            )
            if ok:
                upcoming.add(tid)
                changed = True
    return TaskState(done=done | failed, available=available, upcoming=upcoming, started=started)


# ---------------------------------------------------------------- needs


def compute_needs(
    gd: GameData,
    progress: ProgressData | None,
    level_window: int = 5,
    include_kappa: bool = True,
) -> NeedsResult:
    """Without progress, every task counts as upcoming and every hideout level as unbuilt."""
    by_item: dict[str, ItemNeed] = {}
    any_of: list[AnyOfNeed] = []

    def add(item_id: str, src: NeedSource) -> None:
        if src.count <= 0:
            return
        it = gd.items.get(item_id)
        if it is not None and it.is_currency:
            return  # money isn't loot
        need = by_item.setdefault(item_id, ItemNeed(item_id, gd.item_name(item_id)))
        need.sources.append(src)

    state = compute_task_state(gd, progress, level_window) if progress else None
    obj_counts = progress.objective_counts if progress else {}
    obj_done = {o.id for o in progress.taskObjectivesProgress if o.complete} if progress else set()

    collector_id = next(
        (tid for tid, t in gd.tasks.items() if t.get("normalizedName") == COLLECTOR_NAME), None
    )

    # tasks
    for tid, t in gd.tasks.items():
        if tid == collector_id:
            continue
        if state is None:
            urg = Urgency.UPCOMING_TASK
        elif tid in state.started:
            urg = Urgency.ACTIVE_TASK
        elif tid in state.available or tid in state.upcoming:
            urg = Urgency.UPCOMING_TASK
        else:
            continue
        label = f"{gd.task_names.get(tid, tid)} ({gd.trader_name(t.get('trader'))})"
        for o in _item_objectives(t):
            if o["id"] in obj_done:
                continue
            remaining = int(o.get("count") or 1) - int(obj_counts.get(o["id"], 0))
            fir = bool(o.get("foundInRaid"))
            ids = o.get("items") or []
            if len(ids) == 1:
                add(ids[0], NeedSource("task", label, remaining, fir, urg, tid))
            elif ids and remaining > 0:
                any_of.append(
                    AnyOfNeed(
                        gd.objective_text.get(o["id"], o["id"]),
                        label,
                        remaining,
                        fir,
                        urg,
                        list(ids),
                    )
                )

    # Kappa / Collector
    done_tasks = state.done if state else set()
    if include_kappa and collector_id and collector_id not in done_tasks:
        for o in _item_objectives(gd.tasks[collector_id]):
            if o["id"] in obj_done:
                continue
            remaining = int(o.get("count") or 1) - int(obj_counts.get(o["id"], 0))
            for iid in (o.get("items") or [])[:1]:
                add(
                    iid,
                    NeedSource(
                        "kappa", "Collector (Fence)", remaining, True, Urgency.KAPPA, collector_id
                    ),
                )

    # hideout
    built = progress.built_module_ids if progress else set()
    parts = (
        {p.id: (p.complete, int(p.count)) for p in progress.hideoutPartsProgress}
        if progress
        else {}
    )
    for sid, st in gd.hideout.items():
        levels = sorted(st.get("levels", []), key=lambda lv: lv["level"])
        unbuilt = [lv for lv in levels if lv["id"] not in built]
        for i, lv in enumerate(unbuilt):
            urg = Urgency.HIDEOUT_NEXT if i == 0 else Urgency.HIDEOUT_LATER
            label = f"{gd.station_names.get(sid, sid)} L{lv['level']}"
            for req in lv.get("itemRequirements", []):
                complete, have = parts.get(req["id"], (False, 0))
                if complete:
                    continue
                fir = bool((req.get("attributes") or {}).get("foundInRaid"))
                add(
                    req["item"],
                    NeedSource("hideout", label, int(req["count"]) - have, fir, urg, lv["id"]),
                )

    items = sorted(by_item.values(), key=lambda n: (n.urgency, -n.total, n.name))
    any_of.sort(key=lambda a: (a.urgency, a.task))
    return NeedsResult(items, any_of, state, progress.playerLevel if progress else None)


def _item_objectives(task: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for o in task.get("objectives", []):
        if o.get("type") in ITEM_OBJECTIVES and not o.get("optional"):
            yield o

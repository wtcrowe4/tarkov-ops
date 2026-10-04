from tarkov_ops.gamedata.model import GameData, Item
from tarkov_ops.needs import Urgency, compute_needs
from tarkov_ops.progress.models import ProgressData


def _item(iid: str, name: str) -> Item:
    return Item(iid, name, name, 1, 1, frozenset(), 1000, 900, 500, "Therapist", 400)


def _gd() -> GameData:
    tasks = {
        "t1": {  # available at level 5, done-able now
            "id": "t1",
            "trader": "tr",
            "minPlayerLevel": 1,
            "taskRequirements": [],
            "objectives": [
                {
                    "id": "o1",
                    "type": "giveItem",
                    "count": 3,
                    "foundInRaid": True,
                    "items": ["salty"],
                },
                {"id": "o1f", "type": "findItem", "count": 3, "items": ["salty"]},
            ],
        },
        "t2": {  # needs t1 complete -> upcoming
            "id": "t2",
            "trader": "tr",
            "minPlayerLevel": 3,
            "taskRequirements": [{"task": "t1", "status": ["complete"]}],
            "objectives": [{"id": "o2", "type": "giveItem", "count": 2, "items": ["folder"]}],
        },
        "t3": {  # level 30 -> out of window
            "id": "t3",
            "trader": "tr",
            "minPlayerLevel": 30,
            "taskRequirements": [],
            "objectives": [{"id": "o3", "type": "giveItem", "count": 1, "items": ["folder"]}],
        },
        "t4": {  # any-of objective
            "id": "t4",
            "trader": "tr",
            "minPlayerLevel": 1,
            "taskRequirements": [],
            "objectives": [
                {"id": "o4", "type": "giveItem", "count": 3, "items": ["salty", "folder"]}
            ],
        },
        "col": {
            "id": "col",
            "normalizedName": "collector",
            "trader": "tr",
            "minPlayerLevel": 1,
            "taskRequirements": [],
            "objectives": [
                {"id": "oc", "type": "giveItem", "count": 1, "foundInRaid": True, "items": ["egg"]}
            ],
        },
    }
    hideout = {
        "st": {
            "levels": [
                {
                    "id": "st-1",
                    "level": 1,
                    "itemRequirements": [
                        {"id": "st-1-1", "item": "folder", "count": 1},
                        {"id": "st-1-2", "item": "5449016a4bdc2d6f028b456f", "count": 50000},
                    ],
                },
                {
                    "id": "st-2",
                    "level": 2,
                    "itemRequirements": [
                        {
                            "id": "st-2-1",
                            "item": "folder",
                            "count": 3,
                            "attributes": {"foundInRaid": True},
                        },
                    ],
                },
            ]
        },
    }
    items = {
        i: _item(i, n)
        for i, n in [
            ("salty", "Salty Dog"),
            ("folder", "Intelligence folder"),
            ("egg", "Egg"),
            ("5449016a4bdc2d6f028b456f", "Roubles"),
        ]
    }
    return GameData(
        tasks,
        hideout,
        items,
        {"tr": "Prapor"},
        task_names={"t1": "T1", "t2": "T2", "t3": "T3", "t4": "T4", "col": "Collector"},
        station_names={"st": "Intel Center"},
    )


def _progress(**kw) -> ProgressData:
    base = {
        "tasksProgress": [],
        "taskObjectivesProgress": [],
        "hideoutModulesProgress": [],
        "hideoutPartsProgress": [],
        "displayName": "x",
        "userId": "u",
        "playerLevel": 5,
        "gameEdition": 1,
        "pmcFaction": "USEC",
    }
    base.update(kw)
    return ProgressData.model_validate(base)


def test_states_and_counts():
    res = compute_needs(_gd(), _progress())
    st = res.task_state
    assert st is not None
    assert {"t1", "t4", "col"} <= st.available
    assert "t2" in st.upcoming and "t3" not in st.upcoming
    by = {n.item_id: n for n in res.items}
    assert by["salty"].total == 3 and by["salty"].fir_total == 3  # findItem not double counted
    assert by["salty"].urgency is Urgency.ACTIVE_TASK
    # folder: t2 upcoming x2 + Intel L1 x1 (next) + Intel L2 x3 (later); t3 out of window
    assert by["folder"].total == 6
    assert by["folder"].urgency is Urgency.HIDEOUT_NEXT
    assert "5449016a4bdc2d6f028b456f" not in by  # currency skipped
    assert by["egg"].sources[0].kind == "kappa"
    assert res.any_of and res.any_of[0].count == 3


def test_progress_subtracts():
    prog = _progress(
        tasksProgress=[{"id": "t1", "complete": True}],
        taskObjectivesProgress=[{"id": "o2", "complete": False, "count": 1}],
        hideoutModulesProgress=[{"id": "st-1", "complete": True}],
        hideoutPartsProgress=[{"id": "st-2-1", "complete": False, "count": 2}],
    )
    res = compute_needs(_gd(), prog)
    by = {n.item_id: n for n in res.items}
    assert "salty" not in by  # t1 done
    st = res.task_state
    assert st is not None and "t2" in st.available
    # folder: t2 now active, 2-1 handed in = 1; Intel L2 3-2 = 1 (now next level)
    assert by["folder"].total == 2
    assert {s.urgency for s in by["folder"].sources} == {Urgency.ACTIVE_TASK, Urgency.HIDEOUT_NEXT}


def test_no_progress_lists_everything():
    res = compute_needs(_gd(), None)
    by = {n.item_id: n for n in res.items}
    assert by["folder"].total == 2 + 1 + 1 + 3  # t2, t3, Intel L1, Intel L2
    assert res.task_state is None

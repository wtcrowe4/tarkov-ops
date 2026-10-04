"""In-memory view of the cached json.tarkov.dev documents.

json.tarkov.dev stores display strings as translation keys (e.g. `"<id> Name"`,
`"hideout_area_13_name"`); the `<endpoint>_en` document maps keys to English.
This module resolves them once and exposes the fields the needs/price code uses.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tarkov_ops.gamedata.fetch import cache_dir

FENCE_ID = "579dc571d53a0658a154fbec"
CURRENCY_IDS = {
    "5449016a4bdc2d6f028b456f",  # roubles
    "5696686a4bdc2da3298b456a",  # dollars
    "569668774bdc2da2298b4568",  # euros
}


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    short: str
    width: int
    height: int
    types: frozenset[str]
    avg24h: int | None
    last_low: int | None
    base_price: int
    best_trader: str | None
    best_trader_price: int
    link: str | None = None

    @property
    def slots(self) -> int:
        return max(1, self.width * self.height)

    @property
    def flea_banned(self) -> bool:
        return "noFlea" in self.types

    @property
    def flea_price(self) -> int | None:
        return self.avg24h or self.last_low

    @property
    def is_currency(self) -> bool:
        return self.id in CURRENCY_IDS


@dataclass
class GameData:
    tasks: dict[str, dict[str, Any]]
    hideout: dict[str, dict[str, Any]]
    items: dict[str, Item]
    traders: dict[str, str]  # id -> display name
    task_names: dict[str, str] = field(default_factory=dict)
    objective_text: dict[str, str] = field(default_factory=dict)
    station_names: dict[str, str] = field(default_factory=dict)
    fetched_at: dict[str, str] = field(default_factory=dict)

    def item_name(self, item_id: str) -> str:
        it = self.items.get(item_id)
        return it.name if it else item_id

    def trader_name(self, trader_id: str | None) -> str:
        return self.traders.get(trader_id or "", trader_id or "?")


def _read(directory: Path, name: str) -> dict[str, Any]:
    return json.loads((directory / f"{name}.json").read_text(encoding="utf-8"))["data"]


def _tr(en: dict[str, str], key: str | None) -> str:
    if not key:
        return ""
    v = en.get(key)
    return v if v else key


def load_gamedata(directory: Path | None = None) -> GameData:
    d = directory or cache_dir()
    if not (d / "items.json").exists():
        raise FileNotFoundError(f"No gamedata cache in {d}. Run: tarkov-ops gamedata refresh")

    traders_raw = _read(d, "traders")
    traders_en = _read(d, "traders_en")
    traders = {tid: _tr(traders_en, t.get("name")) for tid, t in traders_raw.items()}

    items_raw = _read(d, "items")["items"]
    items_en = _read(d, "items_en")
    items: dict[str, Item] = {}
    for iid, it in items_raw.items():
        sells = [
            s
            for s in (it.get("sellToTrader") or [])
            if s.get("trader") != FENCE_ID and s.get("priceRUB")
        ]
        best = max(sells, key=lambda s: s["priceRUB"], default=None)
        items[iid] = Item(
            id=iid,
            name=_tr(items_en, it.get("name")),
            short=_tr(items_en, it.get("shortName")),
            width=int(it.get("width") or 1),
            height=int(it.get("height") or 1),
            types=frozenset(it.get("types") or ()),
            avg24h=it.get("avg24hPrice") or None,
            last_low=it.get("lastLowPrice") or None,
            base_price=int(it.get("basePrice") or 0),
            best_trader=traders.get(best["trader"]) if best else None,
            best_trader_price=int(best["priceRUB"]) if best else 0,
            link=it.get("link"),
        )

    tasks = _read(d, "tasks")["tasks"]
    tasks_en = _read(d, "tasks_en")
    task_names = {tid: _tr(tasks_en, t.get("name")) for tid, t in tasks.items()}
    objective_text = {
        o["id"]: _tr(tasks_en, o.get("description"))
        for t in tasks.values()
        for o in t.get("objectives", [])
    }

    hideout = _read(d, "hideout")
    hideout_en = _read(d, "hideout_en")
    station_names = {sid: _tr(hideout_en, s.get("name")) for sid, s in hideout.items()}

    meta_p = d / "meta.json"
    fetched = json.loads(meta_p.read_text(encoding="utf-8")) if meta_p.exists() else {}
    return GameData(
        tasks=tasks,
        hideout=hideout,
        items=items,
        traders=traders,
        task_names=task_names,
        objective_text=objective_text,
        station_names=station_names,
        fetched_at=fetched,
    )

"""Loot reference: every barter/provision/med/key/case item with PvE prices and uses.

Tier is roubles per inventory slot (best of flea and trader). "Used in" counts come from
the needs engine run without progress, so they are full-game totals, not what's left.
"""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from tarkov_ops.gamedata.fetch import USER_AGENT
from tarkov_ops.gamedata.model import GameData
from tarkov_ops.needs import compute_needs

LOOT_TYPES = {"barter", "provisions", "meds", "injectors", "keys", "container"}
TIERS = [(100_000, "S"), (40_000, "A"), (15_000, "B"), (5_000, "C"), (0, "D")]
FLEA_FEE = 0.10  # rough haircut for flea fees when comparing to trader
THIN_MARKET = 2  # <= this many live offers: flea price is a troll listing, don't trust it


def tier_for(per_slot: float) -> str:
    return next(t for floor, t in TIERS if per_slot >= floor)


def build_loot(gd: GameData, items_raw: dict[str, Any], hb_names: dict[str, str]) -> list[dict]:
    uses: dict[str, dict[str, int]] = {}
    for n in compute_needs(gd, None).items:
        u = uses.setdefault(n.item_id, {"hideout": 0, "task": 0, "kappa": 0, "fir": 0})
        for s in n.sources:
            u[s.kind] += s.count
            if s.fir:
                u["fir"] += s.count

    out = []
    for it in gd.items.values():
        if it.is_currency or "preset" in it.types:
            continue
        if not (it.types & LOOT_TYPES or it.id in uses):
            continue
        raw = items_raw.get(it.id, {})
        flea = None if it.flea_banned else it.flea_price
        offers = raw.get("lastOfferCount") or 0
        thin = bool(flea) and offers <= THIN_MARKET
        flea_net = int(flea * (1 - FLEA_FEE)) if flea and not thin else 0
        best = max(flea_net, it.best_trader_price)
        per_slot = best / it.slots
        cats = raw.get("handbookCategories") or []
        out.append(
            {
                "id": it.id,
                "name": it.name,
                "short": it.short,
                "cat": hb_names.get(cats[0], "") if cats else "",
                "w": it.width,
                "h": it.height,
                "flea": flea,
                "fleaNet": flea_net,
                "thin": thin,
                "fleaLevel": raw.get("minLevelForFlea"),
                "trader": it.best_trader,
                "traderPrice": it.best_trader_price,
                "perSlot": int(per_slot),
                "sellTo": "flea" if flea_net > it.best_trader_price else "trader",
                "tier": tier_for(per_slot),
                "uses": uses.get(it.id),
                "fleaBanned": it.flea_banned,
                "change48h": raw.get("changeLast48hPercent"),
            }
        )
    out.sort(key=lambda r: -r["perSlot"])
    return out


def fetch_icons(ids: list[str], cache: Path) -> dict[str, str]:
    """Download 64px icons once into `cache`; return id -> data URI."""
    cache.mkdir(parents=True, exist_ok=True)
    uris: dict[str, str] = {}
    with httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=30) as c:
        for iid in ids:
            p = cache / f"{iid}.webp"
            if not p.exists():
                r = c.get(f"https://assets.tarkov.dev/{iid}-icon.webp")
                if r.status_code != 200:
                    continue
                p.write_bytes(r.content)
            uris[iid] = "data:image/webp;base64," + base64.b64encode(p.read_bytes()).decode()
    return uris


def export(gd: GameData, data_dir: Path, dest: Path, icons: bool = True) -> int:
    raw = json.loads((data_dir / "gamedata" / "items.json").read_text(encoding="utf-8"))["data"]
    en = json.loads((data_dir / "gamedata" / "items_en.json").read_text(encoding="utf-8"))["data"]
    hb = {cid: en.get(c.get("name"), c.get("name")) for cid, c in raw["handbookCategories"].items()}
    rows = build_loot(gd, raw["items"], hb)
    icon_map = fetch_icons([r["id"] for r in rows], data_dir / "icons") if icons else {}
    doc = {
        "generatedAt": datetime.now(UTC).isoformat(),
        "pricesUpdated": max((raw["items"][r["id"]].get("updated") or "") for r in rows),
        "items": rows,
        "icons": icon_map,
    }
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
    return len(rows)

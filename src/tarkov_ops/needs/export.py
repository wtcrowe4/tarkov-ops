"""Serialize a NeedsResult for static pages (no account fields, no token)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from tarkov_ops.gamedata.model import GameData
from tarkov_ops.needs.engine import NeedsResult


def needs_to_json(gd: GameData, res: NeedsResult) -> dict[str, Any]:
    def item_card(iid: str) -> dict[str, Any]:
        it = gd.items.get(iid)
        if it is None:
            return {"id": iid, "name": iid}
        return {
            "id": iid,
            "name": it.name,
            "short": it.short,
            "slots": it.slots,
            "flea": it.flea_price,
            "trader": it.best_trader,
            "traderPrice": it.best_trader_price,
            "fleaBanned": it.flea_banned,
        }

    st = res.task_state
    return {
        "generatedAt": datetime.now(UTC).isoformat(),
        "gamedataFetchedAt": gd.fetched_at,
        "playerLevel": res.player_level,
        "tasks": None
        if st is None
        else {
            "done": len(st.done),
            "available": sorted(gd.task_names.get(t, t) for t in st.available),
            "upcoming": sorted(gd.task_names.get(t, t) for t in st.upcoming),
        },
        "items": [
            {
                **item_card(n.item_id),
                "total": n.total,
                "fir": n.fir_total,
                "urgency": int(n.urgency),
                "urgencyLabel": n.urgency.label,
                "sources": [
                    {
                        "kind": s.kind,
                        "label": s.label,
                        "count": s.count,
                        "fir": s.fir,
                        "urgency": int(s.urgency),
                    }
                    for s in n.sources
                ],
            }
            for n in res.items
        ],
        "anyOf": [
            {
                "label": a.label,
                "task": a.task,
                "count": a.count,
                "fir": a.fir,
                "urgency": int(a.urgency),
                "items": [gd.item_name(i) for i in a.item_ids],
            }
            for a in res.any_of
        ],
    }

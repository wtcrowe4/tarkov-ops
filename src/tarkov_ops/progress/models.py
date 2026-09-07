"""Pydantic models for TarkovTracker `GET /progress` and `GET /token`.

Derived from the gateway's OpenAPI spec (v2.5.0, `docs/samples/openapi.json`).
Task/objective/hideout ids are tarkov.dev ids, so they join directly to gamedata.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

GameMode = Literal["pvp", "pve", "seasonal"]
PmcFaction = Literal["USEC", "BEAR"]
Permission = Literal["GP", "TP", "WP"]  # progress read, team read, progress write


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")  # keep unknown fields; the spec may grow


class ProgressTask(_Base):
    id: str
    complete: bool
    failed: bool = False
    invalid: bool = False


class ProgressObjective(_Base):
    id: str
    complete: bool
    count: float = 0  # omitted by the API when 0
    invalid: bool = False


class ProgressHideoutModule(_Base):
    id: str  # hideout station *level* id
    complete: bool


class ProgressHideoutPart(_Base):
    id: str  # hideout level requirement id
    complete: bool
    count: float = 0


class ProgressData(_Base):
    tasksProgress: list[ProgressTask]
    taskObjectivesProgress: list[ProgressObjective]
    hideoutModulesProgress: list[ProgressHideoutModule]
    hideoutPartsProgress: list[ProgressHideoutPart]
    displayName: str
    userId: str
    playerLevel: int
    gameEdition: int
    pmcFaction: PmcFaction

    # convenience views
    @property
    def completed_task_ids(self) -> set[str]:
        return {t.id for t in self.tasksProgress if t.complete}

    @property
    def failed_task_ids(self) -> set[str]:
        return {t.id for t in self.tasksProgress if t.failed}

    @property
    def built_module_ids(self) -> set[str]:
        return {m.id for m in self.hideoutModulesProgress if m.complete}

    @property
    def objective_counts(self) -> dict[str, float]:
        return {o.id: o.count for o in self.taskObjectivesProgress}


class ProgressMeta(_Base):
    self: str
    gameMode: GameMode


class ProgressResponse(_Base):
    success: bool
    data: ProgressData
    meta: ProgressMeta


class TokenInfoResponse(_Base):
    success: bool
    permissions: list[Permission]
    token: str
    owner: str
    note: str
    calls: int
    gameMode: GameMode

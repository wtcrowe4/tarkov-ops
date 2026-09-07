import json
from pathlib import Path

from tarkov_ops.progress.models import ProgressResponse

SPEC = Path(__file__).resolve().parents[1] / "docs" / "samples" / "openapi.json"


def test_progress_response_parses_spec_example():
    if not SPEC.exists():
        import pytest

        pytest.skip("openapi.json sample not present")
    spec = json.loads(SPEC.read_text())
    example = spec["components"]["schemas"]["ProgressResponse"]["examples"][0]
    r = ProgressResponse.model_validate(example)
    assert r.meta.gameMode == "pvp"
    assert r.data.completed_task_ids == {"task-1"}
    assert r.data.objective_counts == {"obj-1": 2}


def test_objective_count_defaults_to_zero():
    r = ProgressResponse.model_validate(
        {
            "success": True,
            "data": {
                "tasksProgress": [],
                "taskObjectivesProgress": [{"id": "o", "complete": False}],
                "hideoutModulesProgress": [],
                "hideoutPartsProgress": [],
                "displayName": "x",
                "userId": "u",
                "playerLevel": 1,
                "gameEdition": 1,
                "pmcFaction": "USEC",
            },
            "meta": {"self": "u", "gameMode": "pve"},
        }
    )
    assert r.data.taskObjectivesProgress[0].count == 0

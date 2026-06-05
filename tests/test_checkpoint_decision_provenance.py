from __future__ import annotations

import shutil
from pathlib import Path

import yaml

from concept_design.checkpoint import CheckpointManager
from concept_design.traceability import validate_checkpoint_decision_trace


FIXTURE = Path(__file__).parent / "fixtures" / "minimal_workspace"


def test_checkpoint_reasonable_default_is_marked_as_user_authorized(tmp_path: Path):
    ws = tmp_path / "workspace"
    shutil.copytree(FIXTURE, ws)
    index = yaml.safe_load((ws / "domain-design-index.yaml").read_text(encoding="utf-8"))
    domain = index["domain_design_index"]["domains"][0]
    domain["stage"] = "draft_generated"
    feedback = {
        "DM-001": {
            "accepted_item_ids": ["DM-001", "SD-001", "EVT-001", "REQ-001", "Q-001"],
            "open_issues": [{"item_id": "Q-001", "decision": "reasonable default", "note": "合理即可"}],
        }
    }

    manager = CheckpointManager(ws)
    presented = manager.present_for_user_confirmation([domain])
    manager.apply_user_modifications(presented, feedback)

    package = yaml.safe_load((ws / "domains" / "DM-001" / "confirmed_scope_package.yaml").read_text(encoding="utf-8"))["confirmed_scope_package"]
    issue = package["domains"][0]["subdomains"][0]["open_issues"][0]
    assert issue["decision_type"] == "user_authorized_default_design"
    assert issue["decision_origin"] == "checkpoint_feedback"
    assert issue["must_not_be_treated_as_original_requirement"] is True
    assert validate_checkpoint_decision_trace(ws) == []

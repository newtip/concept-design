from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from concept_design.checkpoint import CheckpointError, CheckpointManager


FIXTURE = Path(__file__).parent / "fixtures" / "minimal_workspace"


def copy_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    shutil.copytree(FIXTURE, ws)
    return ws


def set_stage(ws: Path, stage: str = "draft_generated") -> None:
    path = ws / "domain-design-index.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["domain_design_index"]["domains"][0]["stage"] = stage
    data["domain_design_index"]["domains"][0]["status"] = "in_progress"
    data["main_domains"][0]["stage"] = stage
    data["main_domains"][0]["status"] = "in_progress"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    state_path = ws / "project-state.yaml"
    state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
    state["project_state"]["phase"] = "context_packs_built"
    state["project_state"]["checkpoint_confirmed"] = True
    state["project_state"]["baselines_frozen"] = True
    state["project_state"]["context_packs_built"] = True
    state_path.write_text(yaml.safe_dump(state, allow_unicode=True, sort_keys=False), encoding="utf-8")


def domains(ws: Path) -> list[dict]:
    data = yaml.safe_load((ws / "domain-design-index.yaml").read_text(encoding="utf-8"))
    return data["domain_design_index"]["domains"]


def test_checkpoint_accept_delete_modify_and_add_notes(tmp_path):
    ws = copy_workspace(tmp_path)
    set_stage(ws)
    manager = CheckpointManager(ws)
    presented = manager.present_for_user_confirmation([domains(ws)[0]])

    scopes = manager.apply_user_modifications(
        presented,
        {
            "DM-001": {
                "module_overrides": {"MOD-tp-01": {"module_name": "Confirmed Plan Drafting"}},
                "risks": [{"risk_id": "RISK-001", "note": "Keep required-field risk visible."}],
                "boundary_notes": ["Training delivery is excluded."],
            }
        },
    )

    scope = scopes[0]["confirmed_design_scope"]
    assert scope["modules"][0]["module_name"] == "Confirmed Plan Drafting"
    assert scope["risks"][0]["risk_id"] == "RISK-001"
    assert "Training delivery is excluded." in scope["boundary_notes"]
    assert (ws / "domains" / "DM-001" / "confirmed_design_scope.yaml").exists()


def test_checkpoint_deletes_unreasonable_split_item(tmp_path):
    ws = copy_workspace(tmp_path)
    set_stage(ws)
    manager = CheckpointManager(ws)
    presented = manager.present_for_user_confirmation([domains(ws)[0]])

    scopes = manager.apply_user_modifications(presented, {"DM-001": {"delete_modules": ["MOD-tp-01"]}})

    assert scopes[0]["confirmed_design_scope"]["modules"] == []
    assert scopes[0]["confirmed_design_scope"]["deleted_items"] == ["MOD-tp-01"]


def test_checkpoint_rejects_unconfirmed_source_in_formal_module(tmp_path):
    ws = copy_workspace(tmp_path)
    set_stage(ws)
    manager = CheckpointManager(ws)
    presented = manager.present_for_user_confirmation([domains(ws)[0]])

    with pytest.raises(CheckpointError, match="REC-002"):
        manager.apply_user_modifications(
            presented,
            {"DM-001": {"module_overrides": {"MOD-tp-01": {"source": ["REC-002"]}}}},
        )


def test_checkpoint_applies_numbered_feedback(tmp_path):
    ws = copy_workspace(tmp_path)
    set_stage(ws)
    manager = CheckpointManager(ws)
    presented = manager.present_for_user_confirmation([domains(ws)[0]])

    scopes = manager.apply_user_modifications(
        presented,
        {
            "DM-001": {
                "accepted_item_ids": ["DM-001", "SD-001", "SD-002", "EVT-001", "RISK-001", "BOUND-001", "EXC-001", "Q-001"],
                "deleted_items": [{"item_id": "EVT-004", "reason": "Current project does not support cancellation."}],
                "modified_items": [
                    {
                        "item_id": "SD-002",
                        "field": "subdomain_name",
                        "before": "Training Registration Management",
                        "after": "Training Registration Record",
                        "reason": "Only record registration actions.",
                    }
                ],
                "added_items": [{"item_id": "REQ-005", "title": "Added fixture requirement"}],
                "open_issues": [{"item_id": "Q-001", "decision": "keep_as_open_issue", "note": "No approval workflow now."}],
            }
        },
    )

    root = scopes[0]["confirmed_design_scope"]
    assert root["confirmation_status"] == "confirmed_with_modifications"
    assert "EVT-004" in root["deleted_item_ids"]
    assert "SD-002-M" in root["modified_item_ids"]
    assert "REQ-005-N" in root["added_item_ids"]
    domain = root["domains"][0]
    assert domain["subdomains"][1]["subdomain_id"] == "SD-002-M"
    assert domain["subdomains"][1]["subdomain_name"] == "Training Registration Record"
    assert domain["subdomains"][0]["open_issues"][0]["id"] == "Q-001"
    package = yaml.safe_load((ws / "domains" / "DM-001" / "confirmed_scope_package.yaml").read_text(encoding="utf-8"))["confirmed_scope_package"]
    assert package["modified_item_ids"] == ["SD-002-M"]
    assert package["added_item_ids"] == ["REQ-005-N"]
    assert package["deleted_item_ids"] == ["EVT-004"]


def test_runner_checkpoint_p2_domains_updates_stage(tmp_path):
    ws = copy_workspace(tmp_path)
    set_stage(ws)

    result = subprocess.run(
        [sys.executable, "-m", "concept_design", "checkpoint-p2-domains", "--workspace", str(ws)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    updated = domains(ws)[0]
    assert updated["stage"] == "checkpoint_confirmed"
    assert updated["confirmed_design_scope_file"] == "domains/DM-001/confirmed_design_scope.yaml"
    assert updated["confirmed_scope_package_file"] == "domains/DM-001/confirmed_scope_package.yaml"

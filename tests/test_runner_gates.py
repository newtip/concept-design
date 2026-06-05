from __future__ import annotations

import yaml
from pathlib import Path

from concept_design.runner import main


def write_feedback(workspace: Path, status: str = "confirmed") -> Path:
    data = yaml.safe_load((workspace / "project-state.yaml").read_text(encoding="utf-8"))
    run_id = data["project_state"]["run_id"]
    checkpoint_id = data["project_state"].get("checkpoint_id") or f"CP-{run_id}"
    path = workspace / "checkpoints" / checkpoint_id / "user-feedback.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "run_id": run_id,
                "checkpoint_id": checkpoint_id,
                "source": "current_run_user_feedback",
                "status": status,
                "confirmed_by": "pytest",
                "notes": "test confirmation",
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def test_confirm_checkpoint_without_feedback_fails(tmp_path):
    assert main(["init", "--workspace", str(tmp_path)]) == 0
    assert main(["checkpoint", "--workspace", str(tmp_path)]) == 0

    assert main(["confirm-checkpoint", "--workspace", str(tmp_path)]) == 2


def test_confirm_checkpoint_with_mismatched_feedback_fails(tmp_path):
    assert main(["init", "--workspace", str(tmp_path)]) == 0
    assert main(["checkpoint", "--workspace", str(tmp_path)]) == 0
    path = write_feedback(tmp_path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["run_id"] = "not-this-run"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    assert main(["confirm-checkpoint", "--workspace", str(tmp_path), "--feedback-file", str(path)]) == 2


def test_freeze_requires_confirmed_checkpoint(tmp_path):
    assert main(["init", "--workspace", str(tmp_path)]) == 0
    assert main(["checkpoint", "--workspace", str(tmp_path)]) == 0

    assert main(["freeze", "--workspace", str(tmp_path), "--skip-scripts"]) == 2


def test_freeze_after_confirm_checkpoint(tmp_path):
    assert main(["init", "--workspace", str(tmp_path)]) == 0
    assert main(["checkpoint", "--workspace", str(tmp_path)]) == 0
    feedback = write_feedback(tmp_path)
    assert main(["confirm-checkpoint", "--workspace", str(tmp_path), "--mode", "anchor", "--feedback-file", str(feedback)]) == 0

    assert main(["freeze", "--workspace", str(tmp_path), "--skip-scripts"]) == 0

    state = yaml.safe_load((tmp_path / "project-state.yaml").read_text(encoding="utf-8"))
    assert state["project_state"]["phase"] == "baselines_frozen"
    assert state["project_state"]["design_mode"] == "anchor"


def test_build_context_packs_requires_frozen_baselines(tmp_path):
    assert main(["init", "--workspace", str(tmp_path)]) == 0
    assert main(["checkpoint", "--workspace", str(tmp_path)]) == 0
    feedback = write_feedback(tmp_path)
    assert main(["confirm-checkpoint", "--workspace", str(tmp_path), "--feedback-file", str(feedback)]) == 0

    assert main(["build-context-packs", "--workspace", str(tmp_path), "--skip-scripts"]) == 2


def test_prepare_p3_rejects_non_passed_domain(tmp_path):
    assert main(["init", "--workspace", str(tmp_path)]) == 0
    assert main(["checkpoint", "--workspace", str(tmp_path)]) == 0
    feedback = write_feedback(tmp_path)
    assert main(["confirm-checkpoint", "--workspace", str(tmp_path), "--feedback-file", str(feedback)]) == 0
    assert main(["freeze", "--workspace", str(tmp_path), "--skip-scripts"]) == 0
    assert main(["build-context-packs", "--workspace", str(tmp_path), "--skip-scripts"]) == 0
    (tmp_path / "domain-design-index.yaml").write_text(
        yaml.safe_dump({"main_domains": [{"domain_id": "DM-001", "p2_required": True, "status": "reviewing", "stage": "reviewing"}]}),
        encoding="utf-8",
    )

    assert main(["prepare-p3", "--workspace", str(tmp_path), "--skip-scripts"]) == 2


def test_prepare_p3_accepts_all_passed_domains(tmp_path):
    assert main(["init", "--workspace", str(tmp_path)]) == 0
    assert main(["checkpoint", "--workspace", str(tmp_path)]) == 0
    feedback = write_feedback(tmp_path)
    assert main(["confirm-checkpoint", "--workspace", str(tmp_path), "--feedback-file", str(feedback)]) == 0
    assert main(["freeze", "--workspace", str(tmp_path), "--skip-scripts"]) == 0
    assert main(["build-context-packs", "--workspace", str(tmp_path), "--skip-scripts"]) == 0
    (tmp_path / "domain-design-index.yaml").write_text(
        yaml.safe_dump({"main_domains": [{"domain_id": "DM-001", "p2_required": True, "status": "passed", "stage": "passed"}]}),
        encoding="utf-8",
    )

    assert main(["prepare-p3", "--workspace", str(tmp_path), "--skip-scripts"]) == 0

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

import yaml

from concept_design.access_policy import AccessPolicy, AccessScope
from concept_design.runner import main


def write_state(ws: Path, phase: str = "context_packs_built", mode: str = "mode_a_sequential") -> None:
    (ws / "project-state.yaml").write_text(
        yaml.safe_dump(
            {
                "project_state": {
                    "phase": phase,
                    "run_id": "stage-test",
                    "checkpoint_confirmed": True,
                    "baselines_frozen": True,
                    "context_packs_built": True,
                    "p2_complete": False,
                    "design_mode": "sequential",
                    "p2_execution_mode": mode,
                    "history": [],
                }
            }
        ),
        encoding="utf-8",
    )


def write_index(ws: Path, stage: str, status: str = "pending", review_status: str = "missing") -> None:
    (ws / "domain-design-index.yaml").write_text(
        yaml.safe_dump(
            {
                "p2_execution_mode": "mode_a_sequential",
                "domain_design_index": {
                    "domains": [
                        {
                            "domain_id": "DM-001",
                            "p2_required": True,
                            "required_for_p3": True,
                            "sequence": 1,
                            "is_anchor": True,
                            "depends_on": [],
                            "status": status,
                            "stage": stage,
                            "context_pack_file": "context-packs/DM-001-context.yaml",
                            "output_file": "domains/DM-001/tp-main-domain-functional-design.yaml",
                            "design_file": "domains/DM-001/tp-main-domain-functional-design.yaml",
                            "review_file": "domains/DM-001/tp-review-checklist.md",
                            "review_result_file": "domains/DM-001/review-result.yaml",
                            "review_report_file": "domains/DM-001/review-report.md",
                            "confirmed_design_scope_file": "domains/DM-001/confirmed_design_scope.yaml",
                            "review_round": 0,
                            "repair_round": 0,
                            "review_status": review_status,
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


def write_review_result(ws: Path, status: str) -> None:
    path = ws / "domains" / "DM-001" / "review-result.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(
            {
                "review_result": {
                    "domain_id": "DM-001",
                    "status": status,
                    "reviewed_modules": [],
                    "issue_count": 0,
                    "blocker_count": 0,
                    "critical_count": 0,
                    "source_check_count": 0,
                    "generic_issue_count": 0,
                    "issues": [],
                }
            }
        ),
        encoding="utf-8",
    )


def domain(ws: Path) -> dict:
    data = yaml.safe_load((ws / "domain-design-index.yaml").read_text(encoding="utf-8"))
    return data["domain_design_index"]["domains"][0]


def write_multi_index(ws: Path, mode: str, dm1_stage: str, dm2_stage: str, dm3_stage: str = "context_ready", dm2_required: bool = True) -> None:
    base = {
        "p2_execution_mode": mode,
        "domain_design_index": {
            "p2_execution_mode": mode,
            "domains": [
                {
                    "domain_id": "DM-001",
                    "stage": dm1_stage,
                    "status": "passed" if dm1_stage == "passed" else "pending",
                    "required_for_p3": True,
                    "sequence": 1,
                    "is_anchor": True,
                    "depends_on": [],
                    "context_pack_file": "context-packs/DM-001-context.yaml",
                    "output_file": "domains/DM-001/tp-main-domain-functional-design.yaml",
                    "review_file": "domains/DM-001/tp-review-checklist.md",
                    "review_result_file": "domains/DM-001/review-result.yaml",
                    "review_report_file": "domains/DM-001/review-report.md",
                    "confirmed_design_scope_file": "domains/DM-001/confirmed_design_scope.yaml",
                },
                {
                    "domain_id": "DM-002",
                    "stage": dm2_stage,
                    "status": "passed" if dm2_stage == "passed" else "pending",
                    "required_for_p3": dm2_required,
                    "sequence": 2,
                    "is_anchor": False,
                    "depends_on": ["DM-001"],
                    "context_pack_file": "context-packs/DM-002-context.yaml",
                    "output_file": "domains/DM-002/ns-main-domain-functional-design.yaml",
                    "review_file": "domains/DM-002/ns-review-checklist.md",
                    "review_result_file": "domains/DM-002/review-result.yaml",
                    "review_report_file": "domains/DM-002/review-report.md",
                    "confirmed_design_scope_file": "domains/DM-002/confirmed_design_scope.yaml",
                },
                {
                    "domain_id": "DM-003",
                    "stage": dm3_stage,
                    "status": "passed" if dm3_stage == "passed" else "pending",
                    "required_for_p3": True,
                    "sequence": 3,
                    "is_anchor": False,
                    "depends_on": [],
                    "context_pack_file": "context-packs/DM-003-context.yaml",
                    "output_file": "domains/DM-003/au-main-domain-functional-design.yaml",
                    "review_file": "domains/DM-003/au-review-checklist.md",
                    "review_result_file": "domains/DM-003/review-result.yaml",
                    "review_report_file": "domains/DM-003/review-report.md",
                    "confirmed_design_scope_file": "domains/DM-003/confirmed_design_scope.yaml",
                },
            ],
        },
    }
    (ws / "domain-design-index.yaml").write_text(yaml.safe_dump(base), encoding="utf-8")


def domain_by_id(ws: Path, domain_id: str) -> dict:
    data = yaml.safe_load((ws / "domain-design-index.yaml").read_text(encoding="utf-8"))
    return next(d for d in data["domain_design_index"]["domains"] if d["domain_id"] == domain_id)


def test_context_ready_before_run_p2_domain(tmp_path):
    write_state(tmp_path)
    write_index(tmp_path, "pending")

    assert main(["run-p2-domain", "--workspace", str(tmp_path), "--domain-id", "DM-001"]) == 2


def test_context_ready_allows_run_p2_domain(tmp_path):
    write_state(tmp_path)
    write_index(tmp_path, "context_ready")

    assert main(["run-p2-domain", "--workspace", str(tmp_path), "--domain-id", "DM-001"]) == 0
    assert domain(tmp_path)["stage"] == "draft_generated"


def test_runner_sequential_blocks_later_domain_until_previous_required_passed(tmp_path):
    write_state(tmp_path)
    write_multi_index(tmp_path, "mode_a_sequential", "context_ready", "context_ready")

    assert main(["run-p2-domain", "--workspace", str(tmp_path), "--domain-id", "DM-002"]) == 2


def test_runner_sequential_allows_later_domain_after_previous_passed(tmp_path):
    write_state(tmp_path)
    write_multi_index(tmp_path, "mode_a_sequential", "passed", "context_ready")

    assert main(["run-p2-domain", "--workspace", str(tmp_path), "--domain-id", "DM-002"]) == 0
    assert domain_by_id(tmp_path, "DM-002")["stage"] == "draft_generated"


def test_runner_parallel_allows_context_ready_domain_without_previous_passed(tmp_path):
    write_state(tmp_path, mode="mode_b_parallel")
    write_multi_index(tmp_path, "mode_b_parallel", "context_ready", "context_ready")

    assert main(["run-p2-domain", "--workspace", str(tmp_path), "--domain-id", "DM-002"]) == 0


def test_runner_anchor_blocks_non_anchor_until_anchor_passed(tmp_path):
    write_state(tmp_path, mode="mode_c_anchor")
    write_multi_index(tmp_path, "mode_c_anchor", "context_ready", "context_ready")

    assert main(["run-p2-domain", "--workspace", str(tmp_path), "--domain-id", "DM-002"]) == 2


def test_runner_anchor_allows_non_anchor_after_anchor_passed(tmp_path):
    write_state(tmp_path, mode="mode_c_anchor")
    write_multi_index(tmp_path, "mode_c_anchor", "passed", "context_ready")

    assert main(["run-p2-domain", "--workspace", str(tmp_path), "--domain-id", "DM-002"]) == 0


def test_draft_generated_before_review_domain(tmp_path):
    write_state(tmp_path)
    write_index(tmp_path, "context_ready")

    assert main(["review-domain", "--workspace", str(tmp_path), "--domain-id", "DM-001"]) == 2


def test_draft_generated_review_domain_requires_schema_gate_for_passed(tmp_path):
    write_state(tmp_path)
    write_index(tmp_path, "draft_generated")
    write_review_result(tmp_path, "passed")

    assert main(["review-domain", "--workspace", str(tmp_path), "--domain-id", "DM-001"]) == 0
    assert domain(tmp_path)["stage"] == "repair_required"


def test_repair_required_before_repair_domain(tmp_path):
    write_state(tmp_path)
    write_index(tmp_path, "draft_generated")

    assert main(["repair-domain", "--workspace", str(tmp_path), "--domain-id", "DM-001"]) == 2


def test_repair_required_allows_repair_domain(tmp_path):
    write_state(tmp_path)
    write_index(tmp_path, "repair_required")

    assert main(["repair-domain", "--workspace", str(tmp_path), "--domain-id", "DM-001"]) == 0
    updated = domain(tmp_path)
    assert updated["stage"] == "rereviewing"
    assert updated["repair_round"] == 1


def test_prepare_p3_rejects_non_passed_stage(tmp_path):
    write_state(tmp_path)
    write_index(tmp_path, "repair_required", status="passed", review_status="passed")

    assert main(["prepare-p3", "--workspace", str(tmp_path), "--skip-scripts"]) == 2


def test_prepare_p3_accepts_passed_stage(tmp_path):
    write_state(tmp_path)
    write_index(tmp_path, "passed", status="passed", review_status="passed")

    assert main(["prepare-p3", "--workspace", str(tmp_path), "--skip-scripts"]) == 0


def test_p3_access_reads_passed_stage(tmp_path):
    write_index(tmp_path, "passed", status="pending")

    AccessPolicy().assert_can_read(
        AccessScope.P3,
        tmp_path,
        "domains/DM-001/confirmed_design_scope.yaml",
    )


def test_update_domain_status_failed_enters_repair_required(tmp_path):
    write_index(tmp_path, "reviewing")
    write_review_result(tmp_path, "failed")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/update_domain_status.py",
            "--workspace",
            str(tmp_path),
            "--domain-id",
            "DM-001",
            "--to",
            "repair_required",
            "--reason",
            "review failed",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    updated = domain(tmp_path)
    assert updated["stage"] == "repair_required"
    assert updated["status"] == "review_failed"
    assert updated["last_transition_at"]
    assert updated["last_transition_reason"] == "review failed"


def test_update_domain_status_needs_human_enters_human_review_required(tmp_path):
    write_index(tmp_path, "reviewing")
    write_review_result(tmp_path, "needs_human_review")

    result = subprocess.run(
        [
            sys.executable,
            "scripts/update_domain_status.py",
            "--workspace",
            str(tmp_path),
            "--domain-id",
            "DM-001",
            "--to",
            "human_review_required",
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    updated = domain(tmp_path)
    assert updated["stage"] == "human_review_required"
    assert updated["last_transition_at"]

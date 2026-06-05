from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

from concept_design.access_policy import AccessPolicy, AccessScope, AccessViolation


FIXTURE = Path(__file__).parent / "fixtures" / "minimal_workspace"


def run_cmd(*args: str) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(args, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    return result


def test_minimal_workspace_e2e_gates(tmp_path):
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURE, workspace)

    run_cmd(sys.executable, "-m", "concept_design", "init", "--workspace", str(workspace))
    assert phase(workspace) == "initialized"

    run_cmd(sys.executable, "-m", "concept_design", "checkpoint", "--workspace", str(workspace))
    assert phase(workspace) == "checkpoint_created"
    write_checkpoint_feedback(workspace)

    run_cmd(
        sys.executable,
        "-m",
        "concept_design",
        "confirm-checkpoint",
        "--workspace",
        str(workspace),
        "--mode",
        "sequential",
    )
    assert phase(workspace) == "checkpoint_confirmed"
    assert (workspace / "checkpoint" / "user-confirmation.yaml").exists()

    run_cmd(sys.executable, "-m", "concept_design", "freeze", "--workspace", str(workspace))
    assert phase(workspace) == "baselines_frozen"
    assert (workspace / "baselines" / "business_model.yaml").exists()
    assert (workspace / "baselines" / "industry_insight.yaml").exists()
    assert (workspace / "baselines" / "architecture_design.yaml").exists()

    run_cmd(sys.executable, "-m", "concept_design", "build-context-packs", "--workspace", str(workspace))
    assert phase(workspace) == "context_packs_built"
    assert (workspace / "domain-design-index.yaml").exists()
    assert (workspace / "context-packs" / "DM-001-context.yaml").exists()
    assert load_domain(workspace)["stage"] == "context_ready"
    assert load_index(workspace)["p2_execution_mode"] == "mode_a_sequential"
    registry = load_context_pack(workspace, "DM-001")["source_registry"]
    assert isinstance(registry, dict)
    assert registry["FUNC-001"]["source_type"] == "requirement_fact"
    assert registry["REC-002"]["source_type"] == "industry_enrichment"
    assert registry["RISK-001"]["source_type"] == "risk_note"
    assert registry["Q-001"]["source_type"] == "open_question"
    blocked_dm2 = subprocess.run(
        [sys.executable, "-m", "concept_design", "run-p2-domain", "--workspace", str(workspace), "--domain-id", "DM-002"],
        text=True,
        capture_output=True,
    )
    assert blocked_dm2.returncode == 2

    policy = AccessPolicy()
    policy.assert_can_read(AccessScope.P2, workspace, "context-packs/DM-001-context.yaml", "DM-001")
    try:
        policy.assert_can_read(AccessScope.P2, workspace, "p1/business_model.yaml", "DM-001")
    except AccessViolation:
        pass
    else:
        raise AssertionError("P2 must not read p1/business_model.yaml")

    run_cmd(sys.executable, "-m", "concept_design", "run-p2-domain", "--workspace", str(workspace), "--domain-id", "DM-001")
    assert load_domain(workspace)["stage"] == "draft_generated"
    feedback_path = workspace / "checkpoint" / "p2-feedback.yaml"
    feedback_path.write_text(
        yaml.safe_dump(
            {
                "DM-001": {
                    "accepted_item_ids": ["DM-001", "SD-001", "SD-002", "EVT-001", "RISK-001", "BOUND-001", "EXC-001", "Q-001"],
                    "deleted_items": [{"item_id": "EVT-004", "reason": "Current project does not support cancellation."}],
                    "modified_items": [{"item_id": "SD-002", "field": "subdomain_name", "before": "Training Registration Management", "after": "Training Registration Record"}],
                    "added_items": [{"item_id": "REQ-005", "title": "Added fixture requirement"}],
                    "open_issues": [{"item_id": "Q-001", "decision": "keep_as_open_issue", "note": "No approval workflow now."}],
                }
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    run_cmd(sys.executable, "-m", "concept_design", "checkpoint-p2-domains", "--workspace", str(workspace), "--modifications-file", str(feedback_path))
    assert load_domain(workspace)["stage"] == "checkpoint_confirmed"
    assert (workspace / "domains" / "DM-001" / "confirmed_design_scope.yaml").exists()
    assert load_domain(workspace)["confirmed_design_scope_file"] == "domains/DM-001/confirmed_design_scope.yaml"
    confirmed_scope = yaml.safe_load((workspace / "domains" / "DM-001" / "confirmed_design_scope.yaml").read_text(encoding="utf-8"))["confirmed_design_scope"]
    assert "accepted_item_ids" in confirmed_scope
    assert "REQ-005-N" in confirmed_scope["added_item_ids"]
    assert "SD-002-M" in confirmed_scope["modified_item_ids"]
    assert "EVT-004" in confirmed_scope["deleted_item_ids"]
    assert (workspace / "domains" / "DM-001" / "confirmed_scope_package.yaml").exists()
    assert all("subdomain_id" in item for item in confirmed_scope["domains"][0]["subdomains"])
    run_cmd(sys.executable, "-m", "concept_design", "review-domain", "--workspace", str(workspace), "--domain-id", "DM-001")
    assert load_domain(workspace)["stage"] == "passed"

    run_cmd(sys.executable, "scripts/validate_review.py", "--workspace", str(workspace))
    assert (workspace / "domains" / "DM-001" / "review-result.yaml").exists()

    run_cmd(sys.executable, "scripts/update_domain_status.py", "--workspace", str(workspace), "--domain-id", "DM-001", "--to", "passed")
    domain = load_domain(workspace)
    assert domain["status"] == "passed"
    assert domain["stage"] == "passed"
    assert domain["review_status"] == "passed"
    assert domain["last_transition_at"]
    assert domain["last_transition_reason"]
    policy.assert_can_read(AccessScope.P3, workspace, domain["confirmed_design_scope_file"])
    try:
        policy.assert_can_read(AccessScope.P3, workspace, domain["output_file"])
    except AccessViolation:
        pass
    else:
        raise AssertionError("P3 must not read unconfirmed P2 draft output")

    run_cmd(sys.executable, "-m", "concept_design", "build-p3-workspaces", "--workspace", str(workspace))
    p3_workspaces = list((workspace / "p3-workspaces").glob("P3-WS-*"))
    assert [item.name for item in p3_workspaces] == ["P3-WS-DM001"]
    p3_context = yaml.safe_load((workspace / "p3-workspaces" / "P3-WS-DM001" / "context-pack.yaml").read_text(encoding="utf-8"))
    assert "EVT-004" not in str(p3_context)
    assert "REQ-005-N" in str(p3_context)
    assert {item["subdomain_id"] for item in p3_context["context_pack"]["subdomains"]}
    try:
        policy.assert_can_read(
            AccessScope.P3,
            workspace,
            "p3-workspaces/P3-WS-DM001-SD001/context-pack.yaml",
            "P3-WS-DM001-SD001",
        )
    except AccessViolation:
        pass
    else:
        raise AssertionError("P3 workspace must not read another workspace context-pack")

    run_cmd(sys.executable, "-m", "concept_design", "prepare-p3", "--workspace", str(workspace))
    assert phase(workspace) == "p3_prepared"
    assert (workspace / "final" / "final-document-index.yaml").exists()
    awaiting = subprocess.run(
        [sys.executable, "-m", "concept_design", "run-p3-workspace", "--workspace", str(workspace), "--p3-workspace-id", "P3-WS-DM001"],
        text=True,
        capture_output=True,
    )
    assert awaiting.returncode == 0
    assert "awaiting_agent_output" in awaiting.stdout
    assert (workspace / "p3-workspaces" / "P3-WS-DM001" / "p3-agent-prompt.md").exists()
    assert not (workspace / "p3-workspaces" / "P3-WS-DM001" / "design-output.yaml").exists()
    for p3_workspace in p3_workspaces:
        output = tmp_path / f"{p3_workspace.name}-agent-output.yaml"
        write_agent_output(workspace, p3_workspace.name, output)
        run_cmd(
            sys.executable,
            "-m",
            "concept_design",
            "run-p3-workspace",
            "--workspace",
            str(workspace),
            "--p3-workspace-id",
            p3_workspace.name,
            "--agent-output-file",
            str(output),
        )
        assert (p3_workspace / "p3-agent-output.yaml").exists()
        assert (p3_workspace / "p3-run-log.yaml").exists()
    run_cmd(sys.executable, "scripts/validate_p3_workspace_output.py", "--workspace", str(workspace))
    run_cmd(sys.executable, "-m", "concept_design", "assemble-final-design", "--workspace", str(workspace))
    assert (workspace / "final" / "overview-design.md").exists()
    run_cmd(sys.executable, "scripts/validate_p3_assembly.py", "--workspace", str(workspace))
    run_cmd(sys.executable, "scripts/validate_final_doc.py", "--workspace", str(workspace))
    logs = read_agent_logs(workspace)
    agent_names = [entry["agent_name"] for entry in logs]
    assert "01-P1CheckpointAgent" in agent_names
    assert "02-BaselineFreezeAgent" in agent_names
    assert "03-ContextPackBuilderAgent" in agent_names
    assert "05-DesignSynthesisAgent" in agent_names
    assert "P2CheckpointManager" in agent_names
    assert "P3-WorkspacePackagingAgent" in agent_names
    assert "P3WorkspaceAgent" in agent_names
    assert "08-P3PreparationAgent" in agent_names
    assert "10-FinalAssemblyAgent" in agent_names
    assert any(entry["domain_id"] == "DM-001" and entry["output_file"] == "domains/DM-001/confirmed_design_scope.yaml" for entry in logs)
    assert any(entry["memory_snapshot"].get("internal_step") == "prepare-p3" for entry in logs)
    assert any(entry["workspace_id"] == "P3-WS-DM001" and "EVT-004" in entry["deleted_item_ids"] and "REQ-005-N" in entry["added_item_ids"] for entry in logs)


def phase(workspace: Path) -> str:
    data = yaml.safe_load((workspace / "project-state.yaml").read_text(encoding="utf-8"))
    return data["project_state"]["phase"]


def load_domain(workspace: Path) -> dict:
    data = yaml.safe_load((workspace / "domain-design-index.yaml").read_text(encoding="utf-8"))
    return data["domain_design_index"]["domains"][0]


def load_index(workspace: Path) -> dict:
    return yaml.safe_load((workspace / "domain-design-index.yaml").read_text(encoding="utf-8"))


def load_context_pack(workspace: Path, domain_id: str) -> dict:
    data = yaml.safe_load((workspace / "context-packs" / f"{domain_id}-context.yaml").read_text(encoding="utf-8"))
    return data["context_pack"]


def read_agent_logs(workspace: Path) -> list[dict]:
    path = workspace / "logs" / "agent_execution.jsonl"
    assert path.exists()
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def write_agent_output(workspace: Path, workspace_id: str, output_path: Path) -> None:
    manifest_path = workspace / "p3-workspaces" / workspace_id / "workspace-manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    registry = yaml.safe_load((workspace / "p3-workspaces" / workspace_id / "source_registry.yaml").read_text(encoding="utf-8"))["source_registry"]
    source_ids = sorted(registry)
    formal = [
        source_id
        for source_id, meta in registry.items()
        if "formal_design" in meta.get("allowed_usage", []) and "formal_design" not in meta.get("forbidden_usage", [])
    ]
    data = {
        "p3_workspace_output": {
            "workspace_id": workspace_id,
            "granularity": "domain",
            "domain_id": manifest["domain_id"],
            "domain_name": manifest["domain_name"],
            "generated_at": "2026-06-04T00:00:00Z",
            "status": "generated_by_agent",
            "input_artifacts": {
                "workspace_manifest": f"p3-workspaces/{workspace_id}/workspace-manifest.yaml",
                "confirmed_scope_package": f"p3-workspaces/{workspace_id}/confirmed_scope_package.yaml",
                "context_pack": f"p3-workspaces/{workspace_id}/context-pack.yaml",
                "source_registry": f"p3-workspaces/{workspace_id}/source_registry.yaml",
                "p2_reference": f"p3-workspaces/{workspace_id}/p2-reference.yaml",
                "hard_constraints": f"p3-workspaces/{workspace_id}/hard-constraints.yaml",
            },
            "source_ids_used": source_ids,
            "included_item_ids": [item for values in manifest.get("included_item_ids", {}).values() for item in values],
            "excluded_item_ids": manifest.get("excluded_item_ids", []),
            "modified_item_ids": manifest.get("modified_item_ids", []),
            "added_item_ids": manifest.get("added_item_ids", []),
            "deleted_item_ids": manifest.get("deleted_item_ids", []),
            "business_design_summary": f"Agent output for {workspace_id}",
            "domain_data_model_design": {"owned_objects": ["TrainingPlan", "TrainingRegistration"]},
            "domain_permission_design": ["Training administrator"],
            "domain_interface_design": ["Notification service"],
            "cross_subdomain_design": {"cross_subdomain_interfaces": []},
            "subdomain_designs": [
                {
                    "subdomain_id": item["subdomain_id"],
                    "subdomain_name": item["subdomain_name"],
                    "source_ids_used": formal[:1],
                    "data_model_design": {"owned_objects": ["TrainingPlan"]},
                    "function_design": [{"name": "Confirmed function", "source_ids": formal[:1]}] if formal else [],
                    "workflow_design": ["create", "publish"],
                    "page_design": ["Training page"],
                    "interface_design": [],
                    "permission_design": ["Training administrator"],
                    "dfx_design": ["Audit trail"],
                    "unsupported_design": [],
                    "open_issues": [],
                    "traceability": {"formal_source_ids": formal[:1], "reference_only_source_ids": []},
                }
                for item in manifest["included_subdomains"]
            ],
            "dfx_design": ["Traceability"],
            "unsupported_design": [],
            "open_issues": [],
            "traceability": {"formal_source_ids": formal[:1], "reference_only_source_ids": [item for item in source_ids if item not in formal[:1]], "source_to_subdomain_map": {}},
        }
    }
    output_path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def write_checkpoint_feedback(workspace: Path) -> Path:
    run_state = yaml.safe_load((workspace / "project-state.yaml").read_text(encoding="utf-8"))
    run_id = run_state["project_state"]["run_id"]
    checkpoint_id = run_state["project_state"].get("checkpoint_id") or f"CP-{run_id}"
    feedback_path = workspace / "checkpoints" / checkpoint_id / "user-feedback.yaml"
    feedback_path.parent.mkdir(parents=True, exist_ok=True)
    feedback_path.write_text(
        yaml.safe_dump(
            {
                "run_id": run_id,
                "checkpoint_id": checkpoint_id,
                "source": "current_run_user_feedback",
                "status": "confirmed",
                "confirmed_by": "pytest-e2e",
                "notes": "clean rerun confirmation for this execution",
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return feedback_path

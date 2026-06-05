from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import yaml


FIXTURE = Path(__file__).parent / "fixtures" / "minimal_workspace"


def prepared_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    shutil.copytree(FIXTURE, ws)
    state_path = ws / "project-state.yaml"
    state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
    state["project_state"]["phase"] = "p3_prepared"
    state["project_state"]["checkpoint_confirmed"] = True
    state["project_state"]["baselines_frozen"] = True
    state["project_state"]["context_packs_built"] = True
    state["project_state"]["p2_complete"] = True
    state_path.write_text(yaml.safe_dump(state, allow_unicode=True, sort_keys=False), encoding="utf-8")
    index_path = ws / "domain-design-index.yaml"
    index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    domain = index["domain_design_index"]["domains"][0]
    domain["stage"] = "passed"
    domain["status"] = "passed"
    domain["review_status"] = "passed"
    index_path.write_text(yaml.safe_dump(index, allow_unicode=True, sort_keys=False), encoding="utf-8")
    subprocess.run([sys.executable, "-m", "concept_design", "build-p3-workspaces", "--workspace", str(ws)], check=True)
    subprocess.run([sys.executable, "scripts/build_final_document_index.py", "--workspace", str(ws)], check=True)
    return ws


def test_run_p3_workspace_generates_input_bundle_without_fake_output(tmp_path: Path):
    ws = prepared_workspace(tmp_path)

    result = subprocess.run(
        [sys.executable, "-m", "concept_design", "run-p3-workspace", "--workspace", str(ws), "--p3-workspace-id", "P3-WS-DM001"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "awaiting_agent_output" in result.stdout
    p3 = ws / "p3-workspaces" / "P3-WS-DM001"
    assert (p3 / "p3-agent-prompt.md").exists()
    assert (p3 / "p3-agent-input-summary.yaml").exists()
    assert not (p3 / "p3-agent-output.yaml").exists()
    assert "included_subdomains" in (p3 / "p3-agent-prompt.md").read_text(encoding="utf-8")


def test_run_p3_workspace_rejects_subdomain_workspace_id(tmp_path: Path):
    ws = prepared_workspace(tmp_path)

    result = subprocess.run(
        [sys.executable, "-m", "concept_design", "run-p3-workspace", "--workspace", str(ws), "--p3-workspace-id", "P3-WS-DM001-SD001"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert "domain-level" in result.stderr


def test_run_p3_workspace_imports_and_validates_agent_output(tmp_path: Path):
    ws = prepared_workspace(tmp_path)
    output = tmp_path / "agent-output.yaml"
    write_output(ws, "P3-WS-DM001", output)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "concept_design",
            "run-p3-workspace",
            "--workspace",
            str(ws),
            "--domain-id",
            "DM-001",
            "--agent-output-file",
            str(output),
        ],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    p3 = ws / "p3-workspaces" / "P3-WS-DM001"
    assert (p3 / "p3-agent-output.yaml").exists()
    assert (p3 / "p3-run-log.yaml").exists()


def write_output(ws: Path, workspace_id: str, output: Path) -> None:
    manifest = yaml.safe_load((ws / "p3-workspaces" / workspace_id / "workspace-manifest.yaml").read_text(encoding="utf-8"))
    registry = yaml.safe_load((ws / "p3-workspaces" / workspace_id / "source_registry.yaml").read_text(encoding="utf-8"))["source_registry"]
    formal = [source_id for source_id, meta in registry.items() if "formal_design" in meta.get("allowed_usage", [])]
    subdomain_designs = [
        {
            "subdomain_id": item["subdomain_id"],
            "subdomain_name": item["subdomain_name"],
            "source_ids_used": formal[:1],
            "function_design": [{"name": "Create training plan", "source_ids": formal[:1]}] if formal else [],
            "data_model_design": {"entities": ["TrainingPlan"]},
            "workflow_design": ["draft", "publish"],
            "page_design": ["Training plan page"],
            "interface_design": [],
            "permission_design": ["Training admin"],
            "dfx_design": ["Audit changes"],
            "unsupported_design": [],
            "open_issues": [],
            "traceability": {"formal_source_ids": formal[:1], "reference_only_source_ids": []},
        }
        for item in manifest["included_subdomains"]
    ]
    data = {
        "p3_workspace_output": {
            "workspace_id": workspace_id,
            "granularity": "domain",
            "domain_id": manifest["domain_id"],
            "domain_name": manifest["domain_name"],
            "generated_at": "2026-06-04T00:00:00Z",
            "status": "generated_by_agent",
            "input_artifacts": {"workspace_manifest": f"p3-workspaces/{workspace_id}/workspace-manifest.yaml"},
            "source_ids_used": sorted(registry),
            "included_item_ids": [],
            "excluded_item_ids": manifest.get("excluded_item_ids", []),
            "modified_item_ids": manifest.get("modified_item_ids", []),
            "added_item_ids": manifest.get("added_item_ids", []),
            "deleted_item_ids": manifest.get("deleted_item_ids", []),
            "business_design_summary": "real agent output",
            "domain_data_model_design": {"entities": ["TrainingPlan", "TrainingRegistration"]},
            "domain_permission_design": ["Training admin can maintain plans"],
            "domain_interface_design": ["Notification service"],
            "cross_subdomain_design": {"cross_subdomain_interfaces": []},
            "subdomain_designs": subdomain_designs,
            "dfx_design": ["Traceable operations"],
            "unsupported_design": [],
            "open_issues": [],
            "traceability": {"formal_source_ids": formal[:1], "reference_only_source_ids": [], "source_to_subdomain_map": {}},
        }
    }
    output.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

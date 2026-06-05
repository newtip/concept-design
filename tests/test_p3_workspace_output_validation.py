from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import yaml


FIXTURE = Path(__file__).parent / "fixtures" / "minimal_workspace"


def test_validate_p3_workspace_output_rejects_formal_risk_source(tmp_path: Path):
    ws = tmp_path / "workspace"
    shutil.copytree(FIXTURE, ws)
    state_path = ws / "project-state.yaml"
    state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
    state["project_state"]["phase"] = "context_packs_built"
    state["project_state"]["checkpoint_confirmed"] = True
    state["project_state"]["baselines_frozen"] = True
    state["project_state"]["context_packs_built"] = True
    state_path.write_text(yaml.safe_dump(state, allow_unicode=True, sort_keys=False), encoding="utf-8")
    subprocess.run([sys.executable, "-m", "concept_design", "build-p3-workspaces", "--workspace", str(ws)], check=True)
    workspace_id = "P3-WS-DM001"
    manifest = yaml.safe_load((ws / "p3-workspaces" / workspace_id / "workspace-manifest.yaml").read_text(encoding="utf-8"))
    output = {
        "p3_workspace_output": {
            "workspace_id": workspace_id,
            "granularity": "domain",
            "domain_id": manifest["domain_id"],
            "domain_name": manifest["domain_name"],
            "generated_at": "2026-06-04T00:00:00Z",
            "status": "generated_by_agent",
            "input_artifacts": {"workspace_manifest": f"p3-workspaces/{workspace_id}/workspace-manifest.yaml"},
            "source_ids_used": ["RISK-001"],
            "included_item_ids": [],
            "excluded_item_ids": [],
            "modified_item_ids": [],
            "added_item_ids": [],
            "deleted_item_ids": [],
            "subdomain_designs": [
                {
                    "subdomain_id": item["subdomain_id"],
                    "subdomain_name": item["subdomain_name"],
                    "source_ids_used": ["RISK-001"],
                    "function_design": [{"source_ids": ["RISK-001"]}],
                    "traceability": {"formal_source_ids": ["RISK-001"], "reference_only_source_ids": []},
                }
                for item in manifest["included_subdomains"]
            ],
            "traceability": {"formal_source_ids": ["RISK-001"], "reference_only_source_ids": []},
        }
    }
    (ws / "p3-workspaces" / workspace_id / "p3-agent-output.yaml").write_text(yaml.safe_dump(output, allow_unicode=True), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/validate_p3_workspace_output.py", "--workspace", str(ws), "--p3-workspace-id", workspace_id],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "not allowed for formal P3 design" in result.stdout


def test_validate_p3_workspace_output_rejects_subdomain_workspace_id(tmp_path: Path):
    ws = tmp_path / "workspace"
    shutil.copytree(FIXTURE, ws)
    (ws / "p3-workspaces" / "P3-WS-DM001-SD001").mkdir(parents=True)
    output = {
        "p3_workspace_output": {
            "workspace_id": "P3-WS-DM001-SD001",
            "granularity": "domain",
            "domain_id": "DM-001",
            "domain_name": "Training",
            "generated_at": "2026-06-04T00:00:00Z",
            "status": "generated_by_agent",
            "input_artifacts": {},
            "source_ids_used": [],
            "included_item_ids": [],
            "excluded_item_ids": [],
            "modified_item_ids": [],
            "added_item_ids": [],
            "deleted_item_ids": [],
            "subdomain_designs": [],
            "traceability": {},
        }
    }
    (ws / "p3-workspaces" / "P3-WS-DM001-SD001" / "p3-agent-output.yaml").write_text(
        yaml.safe_dump(output, allow_unicode=True),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "scripts/validate_p3_workspace_output.py", "--workspace", str(ws), "--p3-workspace-id", "P3-WS-DM001-SD001"],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "domain-level" in result.stdout

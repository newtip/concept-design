from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import yaml


FIXTURE = Path(__file__).parent / "fixtures" / "minimal_workspace"


def setup_ws(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    shutil.copytree(FIXTURE, ws)
    state = yaml.safe_load((ws / "project-state.yaml").read_text(encoding="utf-8"))
    state["project_state"]["phase"] = "p3_prepared"
    state["project_state"]["p2_complete"] = True
    state["project_state"]["context_packs_built"] = True
    state["project_state"]["baselines_frozen"] = True
    state["project_state"]["checkpoint_confirmed"] = True
    (ws / "project-state.yaml").write_text(yaml.safe_dump(state, allow_unicode=True, sort_keys=False), encoding="utf-8")
    index = yaml.safe_load((ws / "domain-design-index.yaml").read_text(encoding="utf-8"))
    d = index["domain_design_index"]["domains"][0]
    d["stage"] = "passed"
    d["status"] = "passed"
    d["review_status"] = "passed"
    (ws / "domain-design-index.yaml").write_text(yaml.safe_dump(index, allow_unicode=True, sort_keys=False), encoding="utf-8")
    subprocess.run([sys.executable, "-m", "concept_design", "build-p3-workspaces", "--workspace", str(ws)], check=True)
    return ws


def test_assemble_final_design_fails_when_required_output_missing(tmp_path: Path):
    ws = setup_ws(tmp_path)

    result = subprocess.run(
        [sys.executable, "-m", "concept_design", "assemble-final-design", "--workspace", str(ws)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert (ws / "final" / "p3-assembly-report.yaml").exists()
    assert not (ws / "final" / "overview-design.md").exists()


def test_assemble_final_design_succeeds_with_all_workspace_outputs(tmp_path: Path):
    ws = setup_ws(tmp_path)
    for manifest_path in (ws / "p3-workspaces").glob("*/workspace-manifest.yaml"):
        workspace_id = manifest_path.parent.name
        output = tmp_path / f"{workspace_id}.yaml"
        write_output(ws, workspace_id, output)
        subprocess.run(
            [
                sys.executable,
                "-m",
                "concept_design",
                "run-p3-workspace",
                "--workspace",
                str(ws),
                "--p3-workspace-id",
                workspace_id,
                "--agent-output-file",
                str(output),
            ],
            check=True,
        )

    result = subprocess.run(
        [sys.executable, "-m", "concept_design", "assemble-final-design", "--workspace", str(ws)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    overview = (ws / "final" / "overview-design.md").read_text(encoding="utf-8")
    assert "第 11 章 后续建议" in overview
    assert "需求与决策追踪矩阵" in overview
    assert "P3 领域输出覆盖矩阵" in overview
    assert "REQ-001" in overview
    report = yaml.safe_load((ws / "final" / "p3-assembly-report.yaml").read_text(encoding="utf-8"))["p3_assembly_report"]
    assert report["required_domain_count"] == report["required_workspace_count"] == report["validated_workspace_count"]
    assert report["invalid_subdomain_workspace_ids"] == []
    subprocess.run([sys.executable, "scripts/validate_p3_assembly.py", "--workspace", str(ws)], check=True)
    subprocess.run([sys.executable, "scripts/validate_final_doc.py", "--workspace", str(ws)], check=True)


def write_output(ws: Path, workspace_id: str, output: Path) -> None:
    manifest = yaml.safe_load((ws / "p3-workspaces" / workspace_id / "workspace-manifest.yaml").read_text(encoding="utf-8"))
    registry = yaml.safe_load((ws / "p3-workspaces" / workspace_id / "source_registry.yaml").read_text(encoding="utf-8"))["source_registry"]
    formal = [source_id for source_id, meta in registry.items() if "formal_design" in meta.get("allowed_usage", [])]
    subdomain_designs = [
        {
            "subdomain_id": item["subdomain_id"],
            "subdomain_name": item["subdomain_name"],
            "source_ids_used": formal[:1],
            "function_design": [{"name": "Maintain training plan", "source_ids": formal[:1]}] if formal else [],
            "data_model_design": {"entities": ["TrainingPlan"]},
            "workflow_design": ["create", "publish"],
            "page_design": ["Training plan page"],
            "interface_design": ["Notification service"],
            "permission_design": ["Training administrator"],
            "dfx_design": ["Audit trail"],
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
            "business_design_summary": f"output {workspace_id}",
            "domain_data_model_design": {"entities": ["TrainingPlan", "TrainingRegistration"]},
            "domain_permission_design": ["Training admin permissions"],
            "domain_interface_design": ["Notification and email integration"],
            "cross_subdomain_design": {"cross_subdomain_interfaces": ["Plan status shared to registration"]},
            "subdomain_designs": subdomain_designs,
            "dfx_design": ["Traceability", "Consistency"],
            "unsupported_design": [],
            "open_issues": [],
            "traceability": {"formal_source_ids": formal[:1], "reference_only_source_ids": [], "source_to_subdomain_map": {}},
        }
    }
    output.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

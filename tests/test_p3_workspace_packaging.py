from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from concept_design.access_policy import AccessPolicy, AccessScope, AccessViolation


FIXTURE = Path(__file__).parent / "fixtures" / "minimal_workspace"


def copy_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    shutil.copytree(FIXTURE, ws)
    state_path = ws / "project-state.yaml"
    state = yaml.safe_load(state_path.read_text(encoding="utf-8"))
    state["project_state"]["phase"] = "context_packs_built"
    state["project_state"]["checkpoint_confirmed"] = True
    state["project_state"]["baselines_frozen"] = True
    state["project_state"]["context_packs_built"] = True
    state_path.write_text(yaml.safe_dump(state, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return ws


def test_build_p3_workspaces_from_confirmed_scope(tmp_path):
    ws = copy_workspace(tmp_path)

    result = subprocess.run(
        [sys.executable, "-m", "concept_design", "build-p3-workspaces", "--workspace", str(ws)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    p3 = ws / "p3-workspaces" / "P3-WS-DM001"
    assert p3.exists()
    assert not (ws / "p3-workspaces" / "P3-WS-DM001-SD001").exists()
    for filename in [
        "workspace-manifest.yaml",
        "confirmed_scope_package.yaml",
        "confirmed_design_scope.yaml",
        "context-pack.yaml",
        "source_registry.yaml",
        "p2-reference.yaml",
        "hard-constraints.yaml",
    ]:
        assert (p3 / filename).exists()

    manifest = yaml.safe_load((p3 / "workspace-manifest.yaml").read_text(encoding="utf-8"))
    assert manifest["workspace_id"] == "P3-WS-DM001"
    assert manifest["granularity"] == "domain"
    assert manifest["domain_id"] == "DM-001"
    assert {item["subdomain_id"] for item in manifest["included_subdomains"]} == {"SD-001", "SD-002-M"}
    assert "EVT-001" in manifest["included_item_ids"]["domain_events"]
    assert "EVT-004" in manifest["excluded_item_ids"]
    assert "REQ-005-N" in manifest["added_item_ids"]

    context = yaml.safe_load((p3 / "context-pack.yaml").read_text(encoding="utf-8"))["context_pack"]
    assert context["granularity"] == "domain"
    assert "EVT-004" not in str(context)
    assert "REQ-005-N" in str(context)
    assert {item["subdomain_id"] for item in context["subdomains"]} == {"SD-001", "SD-002-M"}
    assert set(context["source_registry"]).issubset(set(context["accepted_item_ids"]))

    scope = yaml.safe_load((p3 / "confirmed_design_scope.yaml").read_text(encoding="utf-8"))
    subdomains = scope["confirmed_design_scope"]["domains"][0]["subdomains"]
    assert {item["subdomain_id"] for item in subdomains} == {"SD-001", "SD-002-M"}
    package = yaml.safe_load((p3 / "confirmed_scope_package.yaml").read_text(encoding="utf-8"))["confirmed_scope_package"]
    assert package["added_item_ids"] == ["REQ-005-N"]
    assert package["deleted_item_ids"] == ["EVT-004"]


def test_p3_workspace_access_policy_is_isolated(tmp_path):
    ws = copy_workspace(tmp_path)
    subprocess.run([sys.executable, "-m", "concept_design", "build-p3-workspaces", "--workspace", str(ws)], check=True)
    policy = AccessPolicy()

    policy.assert_can_read(
        AccessScope.P3,
        ws,
        "p3-workspaces/P3-WS-DM001/context-pack.yaml",
        "P3-WS-DM001",
    )
    with pytest.raises(AccessViolation):
        policy.assert_can_read(
            AccessScope.P3,
            ws,
            "p3-workspaces/P3-WS-DM001-SD001/context-pack.yaml",
            "P3-WS-DM001-SD001",
        )

    policy.assert_can_write(
        AccessScope.P3,
        ws,
        "p3-workspaces/P3-WS-DM001/p3-agent-output.yaml",
        "P3-WS-DM001",
    )
    with pytest.raises(AccessViolation):
        policy.assert_can_write(
            AccessScope.P3,
            ws,
            "p3-workspaces/P3-WS-DM002/p3-agent-output.yaml",
            "P3-WS-DM001",
        )
    with pytest.raises(AccessViolation):
        policy.assert_can_write(AccessScope.P3, ws, "domain-design-index.yaml", "P3-WS-DM001")
    with pytest.raises(AccessViolation):
        policy.assert_can_write(AccessScope.P3, ws, "context-packs/DM-001-context.yaml", "P3-WS-DM001")

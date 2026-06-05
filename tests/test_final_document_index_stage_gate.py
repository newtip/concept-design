from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import yaml


FIXTURE = Path(__file__).parent / "fixtures" / "minimal_workspace"


def test_final_document_index_uses_stage_passed_not_display_status(tmp_path: Path):
    ws = tmp_path / "workspace"
    shutil.copytree(FIXTURE, ws)
    index_path = ws / "domain-design-index.yaml"
    index = yaml.safe_load(index_path.read_text(encoding="utf-8"))
    domain = index["domain_design_index"]["domains"][0]
    domain["stage"] = "passed"
    domain["status"] = "pending"
    domain["review_status"] = "missing"
    domain["p3_workspaces"] = [{"workspace_id": "P3-WS-DM001", "domain_id": "DM-001", "granularity": "domain"}]
    index_path.write_text(yaml.safe_dump(index, allow_unicode=True, sort_keys=False), encoding="utf-8")

    result = subprocess.run([sys.executable, "scripts/build_final_document_index.py", "--workspace", str(ws)], text=True, capture_output=True)

    assert result.returncode == 0, result.stdout + result.stderr
    final = yaml.safe_load((ws / "final" / "final-document-index.yaml").read_text(encoding="utf-8"))["final_document_index"]
    assert final["passed_domains"][0]["domain_id"] == "DM-001"
    assert final["passed_domains"][0]["stage"] == "passed"
    assert final["passed_domains"][0]["status"] == "pending"

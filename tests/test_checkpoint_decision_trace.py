from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import yaml


FIXTURE = Path(__file__).parent / "fixtures" / "minimal_workspace"


def test_checkpoint_decision_trace_script_reports_missing_provenance(tmp_path: Path):
    ws = tmp_path / "workspace"
    shutil.copytree(FIXTURE, ws)
    package_path = ws / "domains" / "DM-001" / "confirmed_scope_package.yaml"
    package = yaml.safe_load(package_path.read_text(encoding="utf-8"))
    issue = package["confirmed_scope_package"]["domains"][0]["subdomains"][0]["open_issues"][0]
    issue["note"] = "合理即可"
    issue.pop("decision_type", None)
    package_path.write_text(yaml.safe_dump(package, allow_unicode=True, sort_keys=False), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/validate_checkpoint_decision_trace.py", "--workspace", str(ws)],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    assert "user_authorized_default_design" in result.stdout

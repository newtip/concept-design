from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import yaml


FIXTURE = Path(__file__).parent / "fixtures" / "minimal_workspace"


def test_summary_report_commands_create_yaml_and_markdown(tmp_path: Path):
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

    for command, stem in [
        ("summarize-pre-p2", "pre-p2-summary"),
        ("summarize-p2-checkpoint", "p2-checkpoint-summary"),
        ("summarize-p3-workspaces", "p3-workspace-summary"),
    ]:
        result = subprocess.run([sys.executable, "-m", "concept_design", command, "--workspace", str(ws)], text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
        data = yaml.safe_load((ws / "reports" / f"{stem}.yaml").read_text(encoding="utf-8"))
        assert data["summary_report"]["report_type"]
        assert (ws / "reports" / f"{stem}.md").exists()

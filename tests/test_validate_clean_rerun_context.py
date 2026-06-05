from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml

from concept_design.project_state import Phase, ProjectState


def _init_state(workspace: Path, *, with_checkpoint: bool = False) -> tuple[str, str]:
    state = ProjectState.load(workspace)
    state.transition_to(Phase.INITIALIZED)
    state.mark_p1_complete()
    if with_checkpoint:
        state.create_checkpoint()
    state.save()
    data = yaml.safe_load((workspace / "project-state.yaml").read_text(encoding="utf-8"))["project_state"]
    return data["run_id"], data["checkpoint_id"]


def _write_p1_open_questions(workspace: Path) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    (workspace / "p1").mkdir(exist_ok=True)
    (workspace / "p1" / "business_model.yaml").write_text(
        """
business_model:
  open_questions:
    - question_id: Q-001
      question: 是否需要审批流程？
      status: unresolved
""",
        encoding="utf-8",
    )


def _write_feedback(workspace: Path, run_id: str, checkpoint_id: str, **extra) -> Path:
    path = workspace / "checkpoints" / checkpoint_id / "user-feedback.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "checkpoint_id": checkpoint_id,
        "source": "current_run_user_feedback",
        "status": "confirmed",
        "confirmed_by": "pytest-clean-rerun",
    }
    payload.update(extra)
    path.write_text(yaml.safe_dump(payload, allow_unicode=True), encoding="utf-8")
    return path


def _run_validate(workspace: Path, expect_code: int = 0, *, stage: str = "checkpoint", feedback_file: Path | None = None) -> str:
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(root) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [
        sys.executable,
        str(root / "scripts/validate_clean_rerun_context.py"),
        "--workspace",
        str(workspace),
        "--stage",
        stage,
    ]
    if feedback_file is not None:
        cmd.extend(["--feedback-file", str(feedback_file)])
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=root,
        env=env,
        timeout=30,
    )
    assert result.returncode == expect_code, result.stdout + result.stderr
    return result.stdout + result.stderr


def test_clean_rerun_checkpoint_validation_passes_without_feedback(tmp_path):
    _init_state(tmp_path, with_checkpoint=False)
    _write_p1_open_questions(tmp_path)
    output = _run_validate(tmp_path, 0, stage="checkpoint")
    assert "PASSED: clean rerun context validation" in output
    assert "Q-001" in output


def test_clean_rerun_confirm_validation_requires_current_feedback(tmp_path):
    run_id, checkpoint_id = _init_state(tmp_path, with_checkpoint=True)
    _write_p1_open_questions(tmp_path)
    output = _run_validate(tmp_path, 1, stage="confirm")
    assert "missing feedback file" in output
    feedback = _write_feedback(tmp_path, run_id, checkpoint_id)
    output = _run_validate(tmp_path, 0, stage="confirm", feedback_file=feedback)
    assert "PASSED: clean rerun context validation" in output


def test_clean_rerun_validation_rejects_legacy_feedback_path_in_confirm_stage(tmp_path):
    run_id, checkpoint_id = _init_state(tmp_path, with_checkpoint=True)
    _write_p1_open_questions(tmp_path)
    output = _run_validate(
        tmp_path,
        1,
        stage="confirm",
        feedback_file=tmp_path / "checkpoint" / "user-feedback.yaml",
    )
    assert "missing feedback file" in output
    legacy = _write_feedback(tmp_path, run_id, checkpoint_id, source="legacy_prompt_cache")
    output = _run_validate(tmp_path, 1, stage="confirm", feedback_file=legacy)
    assert "source must be current_run_user_feedback" in output


def test_clean_rerun_validation_rejects_historical_status(tmp_path):
    _init_state(tmp_path, with_checkpoint=False)
    _write_p1_open_questions(tmp_path)
    state = yaml.safe_load((tmp_path / "p1" / "business_model.yaml").read_text(encoding="utf-8"))
    state["business_model"]["open_questions"][0]["status"] = "confirmed"
    (tmp_path / "p1" / "business_model.yaml").write_text(yaml.safe_dump(state, allow_unicode=True), encoding="utf-8")
    output = _run_validate(tmp_path, 1, stage="checkpoint")
    assert "forbidden pre-checkpoint status" in output


def test_clean_rerun_validation_rejects_prompt_contamination(tmp_path):
    _init_state(tmp_path, with_checkpoint=False)
    _write_p1_open_questions(tmp_path)
    (tmp_path / "p1-workspace").mkdir(exist_ok=True)
    (tmp_path / "p1-workspace" / "agent_prompt.md").write_text("Q-001: 用户在本线程已确认的问题答案", encoding="utf-8")
    output = _run_validate(tmp_path, 1, stage="checkpoint")
    assert "historical" in output or "contamination" in output


def test_clean_rerun_validation_rejects_forbidden_p1_read_scope(tmp_path):
    _init_state(tmp_path, with_checkpoint=False)
    _write_p1_open_questions(tmp_path)
    (tmp_path / "p1-workspace").mkdir(exist_ok=True)
    (tmp_path / "p1-workspace" / "agent_prompt.md").write_text("请读取 parsed/document.md，不要读取 baselines/business_model.yaml。", encoding="utf-8")
    output = _run_validate(tmp_path, 1, stage="checkpoint")
    assert "forbidden path" in output


def test_clean_rerun_checkpoint_stage_rejects_advanced_workspace(tmp_path):
    run_id, checkpoint_id = _init_state(tmp_path, with_checkpoint=True)
    _write_p1_open_questions(tmp_path)
    (tmp_path / "checkpoint" / "user-confirmation.yaml").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "checkpoint" / "user-confirmation.yaml").write_text("{}", encoding="utf-8")
    state = ProjectState.load(tmp_path)
    state.transition_to(Phase.CHECKPOINT_CONFIRMED)
    state.save()
    feedback = _write_feedback(tmp_path, run_id, checkpoint_id)
    output = _run_validate(tmp_path, 1, stage="checkpoint")
    assert "only valid before checkpoint" in output
    _run_validate(tmp_path, 0, stage="confirm", feedback_file=feedback)

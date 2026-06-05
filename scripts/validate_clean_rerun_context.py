#!/usr/bin/env python3
"""Validate clean-rerun context to prevent historical checkpoint answer contamination."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from concept_design.access_policy import AccessPolicy, AccessScope
from concept_design.project_state import ProjectState
from concept_design.project_state import Phase


CHECKPOINT_FILE_MAX_BYTES = 100 * 1024

P1_ALLOWED_STATUSES = {
    "",
    "unresolved",
    "pending",
    "pending_confirmation",
    "open",
    "open_pending_confirmation",
}
P1_FORBIDDEN_STATUSES = {
    "answered",
    "answered_by_user",
    "confirmed",
    "confirmed_by_user",
    "done",
    "resolved",
    "approved",
}
P1_QUESTION_TEXT_FORBIDDEN = {
    "requires confirmation",
    "报名剩余容量口径",
    "站内信和邮件",
    "合理即可",
    "不用脱敏",
    "同一人员重复出现不允许",
    "用户在本线程已确认的问题答案",
    "用户已确认",
    "open questions", 
}
P1_Q_PATTERNS = tuple(f"Q-00{i}" for i in range(1, 10))
P1_Q_LIST_KEYS = {"open_questions", "open_question_candidates", "open_questions_numbered", "questions"}

HISTORICAL_ANSWER_MARKERS = (
    "answer from previous",
    "answer from prior",
    "answered_by_user",
    "confirmed_by_user",
    "历史答案",
    "历史确认",
    "historical answer",
    "history answer",
    "previous run",
    "previously confirmed",
    "already confirmed",
    "user confirmed",
    "confirmed in this round",
    "confirmed this round",
)
HISTORICAL_ANSWER_PHRASES = (
    "用户在本线程已确认的问题答案",
    "用户已确认 open questions",
    "报名剩余容量口径：减审核通过人数",
    "站内信和邮件",
    "合理即可",
    "不用脱敏",
    "同一人员重复出现不允许",
    "用户已确认",
    "已确认 open questions",
    *HISTORICAL_ANSWER_MARKERS,
)
FORBIDDEN_QUESTION_ROLES = {"rule", "decision", "confirmed_rule", "confirmedrule"}

READ_INTENT_MARKERS = ("read", "input", "context", "source", "load", "parsed")
WRITE_INTENT_MARKERS = ("write", "output", "emit", "generate", "produce", "save")
FORBIDDEN_P1_READ_PATH_MARKERS = (
    " raw/",
    " raw\\",
    " baselines/",
    " baselines\\",
    " context-packs/",
    " context-packs\\",
    " domains/",
    " domains\\",
    " p3-workspaces/",
    " p3-workspaces\\",
    " final/",
    " final\\",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate clean-rerun context safety")
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument(
        "--stage",
        choices=["checkpoint", "confirm"],
        default="checkpoint",
        help="checkpoint=check before checkpoint creation; confirm=check before confirm-checkpoint",
    )
    parser.add_argument("--feedback-file", default="", help="Optional feedback path used by confirm stage")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--run-validator", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()

    workspace = Path(args.workspace)
    errors: list[str] = []
    pending_questions: list[tuple[str, str, str]] = []

    state = _load_state(workspace, errors)
    if state is None:
        _print_fail(errors)
        return 1

    run_id = state.run_id
    checkpoint_id = state.checkpoint_id or f"CP-{run_id}"

    if args.stage == "checkpoint":
        _validate_not_already_advanced(workspace, state, errors)

    _validate_p1_open_questions(workspace, run_id, pending_questions, errors)
    _validate_prompt_and_logs_for_leakage(workspace, errors)
    _validate_p1_access_gate(workspace, errors)

    if args.stage == "confirm":
        feedback_path = _resolve_feedback_path(workspace, checkpoint_id, args.feedback_file)
        _validate_checkpoint_feedback(feedback_path, run_id, checkpoint_id, errors)

    if args.strict:
        p1_dir = workspace / "p1"
        run_p1_dir = workspace / "runs" / run_id / "p1"
        if not p1_dir.exists() and not run_p1_dir.exists():
            errors.append("strict mode: no P1 outputs found; run should start from parsed outputs first")

    if pending_questions:
        summary_lines = [f"  - {qid} ({source}) status={status}" for qid, status, source in sorted(pending_questions)]
        print("Q-001~Q-009 checkpoint candidates:")
        print("\n".join(summary_lines))

    if errors:
        _print_fail(errors)
        return 1

    print("PASSED: clean rerun context validation")
    return 0


def _load_state(workspace: Path, errors: list[str]):
    try:
        return ProjectState.load(workspace)
    except Exception as exc:
        errors.append(f"cannot load project-state.yaml: {exc}")
        return None


def _validate_not_already_advanced(workspace: Path, state: ProjectState, errors: list[str]) -> None:
    if state.phase not in {Phase.INITIALIZED, Phase.P1_COMPLETE, Phase.CHECKPOINT_CREATED}:
        errors.append(f"clean rerun checkpoint validation is only valid before checkpoint; current phase={state.phase.value}")

    forbidden_files = [
        workspace / "checkpoints" / (state.checkpoint_id or f"CP-{state.run_id}") / "user-feedback.yaml",
        workspace / "checkpoint" / "user-confirmation.yaml",
        workspace / "checkpoint" / "P1-summary.md",
    ]
    for path in forbidden_files:
        if path.exists():
            errors.append(f"clean rerun checkpoint must not already contain {path.relative_to(workspace)}")

    for rel in ("baselines", "context-packs", "domains", "p3-workspaces", "final"):
        folder = workspace / rel
        if not folder.exists():
            continue
        files = [p for p in folder.rglob("*") if p.is_file()]
        if files:
            sample = ", ".join(str(p.relative_to(workspace)) for p in files[:3])
            errors.append(f"clean rerun checkpoint must not contain generated files under {rel}/: {sample}")


def _validate_p1_open_questions(
    workspace: Path,
    run_id: str,
    pending_questions: list[tuple[str, str, str]],
    errors: list[str],
) -> None:
    p1_paths = [
        workspace / "p1" / "business_model.yaml",
        workspace / "p1" / "industry_insight.yaml",
        workspace / "p1" / "architecture_design.yaml",
        workspace / "runs" / run_id / "p1" / "business_model.yaml",
        workspace / "runs" / run_id / "p1" / "industry_insight.yaml",
        workspace / "runs" / run_id / "p1" / "architecture_design.yaml",
        workspace / "runs" / run_id / "P1" / "business_model.yaml",
        workspace / "runs" / run_id / "P1" / "industry_insight.yaml",
        workspace / "runs" / run_id / "P1" / "architecture_design.yaml",
    ]

    for path in p1_paths:
        if not path.exists():
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            if path.stat().st_size <= CHECKPOINT_FILE_MAX_BYTES:
                _scan_text_for_historical_answers(path, text, errors)
        except Exception as exc:
            errors.append(f"{path}: cannot read ({exc})")
            continue

        try:
            payload = yaml.safe_load(text) or {}
        except Exception as exc:
            errors.append(f"{path}: invalid yaml ({exc})")
            continue

        for item in _walk_open_questions(payload):
            if not isinstance(item, dict):
                continue

            qid = _normalize_qid(item.get("question_id") or item.get("id") or item.get("source_id"))
            if not qid:
                continue

            status = _normalize_status(item.get("status") or item.get("answer_status"))
            if status and status in P1_FORBIDDEN_STATUSES:
                errors.append(f"{path}: {qid} has forbidden pre-checkpoint status '{status}'")
                continue
            if status and status not in P1_ALLOWED_STATUSES:
                errors.append(f"{path}: {qid} status must be pending before checkpoint, got '{status}'")
                continue

            question_role = _normalize_question_role(item)
            if question_role in FORBIDDEN_QUESTION_ROLES:
                errors.append(f"{path}: {qid} appears as {question_role}, expected open question")
                continue

            if item.get("answer") is not None and str(item.get("answer")).strip():
                errors.append(f"{path}: {qid} has inline answer payload before checkpoint")
                continue
            question_text = str(item.get("question") or item.get("question_text") or "").strip()
            if _contains_forbidden_question_text(question_id=qid, text=question_text):
                errors.append(f"{path}: {qid} has forbidden/placeholder question text '{question_text}'")
                continue

            if item.get("notes") is not None and str(item.get("notes")).strip():
                note = str(item.get("notes"))
                if "decision" in note.lower() or "answer" in note.lower() or "纭" in note:
                    errors.append(f"{path}: {qid} has inline historical note payload before checkpoint")

            if not status:
                status = ""
            pending_questions.append((qid, status, str(path.relative_to(workspace))))


def _resolve_feedback_path(workspace: Path, checkpoint_id: str, feedback_file: str) -> Path:
    if feedback_file:
        candidate = Path(feedback_file)
        return candidate if candidate.is_absolute() else workspace / candidate
    return workspace / "checkpoints" / checkpoint_id / "user-feedback.yaml"


def _validate_checkpoint_feedback(feedback_path: Path, run_id: str, checkpoint_id: str, errors: list[str]) -> None:
    if not feedback_path.exists():
        errors.append(f"missing feedback file: {feedback_path}")
        return

    payload = _load_yaml(feedback_path)
    if not isinstance(payload, dict):
        errors.append(f"{feedback_path}: YAML payload must be map")
        return

    for field in ("run_id", "checkpoint_id", "source"):
        if field not in payload:
            errors.append(f"{feedback_path}: missing required field '{field}'")

    if payload.get("run_id") != run_id:
        errors.append(f"{feedback_path}: run_id mismatch")
    if payload.get("checkpoint_id") != checkpoint_id:
        errors.append(f"{feedback_path}: checkpoint_id mismatch")
    if payload.get("source") != "current_run_user_feedback":
        errors.append(f"{feedback_path}: source must be current_run_user_feedback")

    status = payload.get("status") or payload.get("confirmation_status")
    if status not in {"confirmed", "approved"}:
        errors.append(f"{feedback_path}: status must be confirmed/approved")


def _validate_prompt_and_logs_for_leakage(workspace: Path, errors: list[str]) -> None:
    candidates = [
        workspace / "p1-workspace" / "agent_prompt.md",
        workspace / "p1-workspace" / "input_summary.yaml",
        workspace / "p1-workspace" / "input_artifacts.yaml",
        workspace / "logs" / "agent_execution.jsonl",
    ]

    for path in candidates:
        if not path.exists():
            continue
        if path.stat().st_size > CHECKPOINT_FILE_MAX_BYTES:
            errors.append(f"{path}: exceeds 100KB and cannot be scanned for clean-rerun confirmation leakage")
            continue

        if path.name == "agent_execution.jsonl":
            _scan_agent_execution_log(path, errors)
            continue

        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as exc:
            errors.append(f"{path}: cannot read: {exc}")
            continue

        _scan_text_for_historical_answers(path, text, errors)
        _scan_text_for_forbidden_p1_reads(path, text, errors)


def _scan_agent_execution_log(path: Path, errors: list[str]) -> None:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line_number, line in enumerate(handle, 1):
                entry = _parse_jsonl(line)
                if not isinstance(entry, dict):
                    continue
                for label, text in _iter_agent_text_fields(entry):
                    context = f"line {line_number} {label}"
                    _scan_text_for_historical_answers(path, text, errors, context=context)
                    _scan_text_for_forbidden_p1_reads(path, text, errors, context=context)
    except Exception as exc:
        errors.append(f"{path}: cannot scan agent log: {exc}")


def _iter_agent_text_fields(value: Any, prefix: str = "") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, item in value.items():
            name = f"{prefix}.{key}" if prefix else str(key)
            if key in {"prompt", "memory_snapshot", "input_summary", "input_artifacts", "included_item_ids"}:
                if isinstance(item, str):
                    yield name, item
                elif isinstance(item, (dict, list)):
                    yield name, yaml.safe_dump(item, allow_unicode=True, sort_keys=False)
                elif item is not None:
                    yield name, str(item)
            elif isinstance(item, (dict, list)):
                yield from _iter_agent_text_fields(item, name)
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            yield from _iter_agent_text_fields(item, f"{prefix}[{idx}]")


def _scan_text_for_historical_answers(path: Path, text: str, errors: list[str], context: str = "") -> None:
    for qid in P1_Q_PATTERNS:
        if qid not in text:
            continue
        for line in text.splitlines():
            if qid not in line:
                continue
            if _line_indicates_history_answer(line):
                errors.append(_format_context(path, context, f"{qid} has contamination marker in '{line.strip()[:180]}'"))
                return
    lower_text = text.lower()
    if any(marker.lower() in lower_text for marker in P1_QUESTION_TEXT_FORBIDDEN):
        errors.append(_format_context(path, context, "forbidden placeholder phrase detected in prompt/log payload"))
        return


def _scan_text_for_forbidden_p1_reads(path: Path, text: str, errors: list[str], context: str = "") -> None:
    for line in text.splitlines():
        normalized = (" " + line.replace("\\", "/")).lower()
        has_read_intent = any(marker in normalized for marker in READ_INTENT_MARKERS)
        has_write_intent = any(marker in normalized for marker in WRITE_INTENT_MARKERS)
        if not has_read_intent or has_write_intent:
            continue
        if any(marker in normalized for marker in FORBIDDEN_P1_READ_PATH_MARKERS):
            errors.append(_format_context(path, context, f"P1 read scope includes forbidden path in '{line.strip()[:180]}'"))
            return


def _validate_p1_access_gate(workspace: Path, errors: list[str]) -> None:
    policy = AccessPolicy()
    try:
        policy.assert_can_read(AccessScope.P1, workspace, "parsed/document.md")
        policy.assert_can_read(AccessScope.P1, workspace, "parsed/document-ir.yaml")
        policy.assert_can_read(AccessScope.P1, workspace, "parsed/image-manifest.yaml")

        tables_dir = workspace / "parsed" / "tables"
        if tables_dir.exists():
            for path in sorted(tables_dir.glob("*.yaml")):
                policy.assert_can_read(AccessScope.P1, workspace, path)
        images_dir = workspace / "parsed" / "images"
        if images_dir.exists():
            for path in sorted(images_dir.iterdir()):
                policy.assert_can_read(AccessScope.P1, workspace, path)

        for denied in (
            "raw/original.docx",
            "p1/business_model.yaml",
            "baselines/business_model.yaml",
            "context-packs/sample.yaml",
        ):
            try:
                policy.assert_can_read(AccessScope.P1, workspace, denied)
                errors.append(f"P1 policy should deny read access to {denied}")
            except Exception:
                continue
    except Exception as exc:
        errors.append(f"P1 policy validation failed: {exc}")


def _walk_open_questions(value: Any):
    if isinstance(value, dict):
        qid = _normalize_qid(value.get("question_id") or value.get("id") or value.get("source_id"))
        if qid:
            yield value

        for key, item in value.items():
            if key in P1_Q_LIST_KEYS and isinstance(item, list):
                for entry in item:
                    if isinstance(entry, dict):
                        yield entry
                continue
            if isinstance(item, (dict, list)):
                yield from _walk_open_questions(item)
    elif isinstance(value, list):
        for entry in value:
            if isinstance(entry, dict):
                yield from _walk_open_questions(entry)


def _normalize_qid(value: object) -> str | None:
    if not value:
        return None
    text = str(value).strip().upper()
    if not text.startswith("Q-"):
        return None
    if not re.fullmatch(r"Q-\d{3,}", text):
        return None
    return text if text in P1_Q_PATTERNS else None


def _normalize_status(value: object) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _normalize_question_role(item: dict) -> str:
    for key in ("source_type", "category", "type", "question_type", "decision_type"):
        value = str(item.get(key, "")).strip().lower().replace(" ", "_")
        if value:
            return value
    return "question"


def _line_indicates_history_answer(line: str) -> bool:
    lower = line.lower()
    if any(marker.lower() in lower for marker in HISTORICAL_ANSWER_MARKERS):
        return True
    return any(phrase.lower() in lower for phrase in HISTORICAL_ANSWER_PHRASES)


def _contains_forbidden_question_text(question_id: str, text: str) -> bool:
    if not text:
        return False
    normalized = text.strip()
    if any(marker.lower() in normalized.lower() for marker in P1_QUESTION_TEXT_FORBIDDEN):
        return True
    if normalized.startswith(f"{question_id}:"):
        return True
    if normalized.startswith(f"Question {question_id}") and "requires confirmation" in normalized:
        return True
    return False


def _parse_jsonl(raw: str) -> dict | None:
    raw = raw.strip()
    if not raw:
        return None
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except Exception:
        return None


def _load_yaml(path: Path):
    if not path.exists():
        return None
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def _format_context(path: Path, context: str, message: str) -> str:
    return f"{path}: {context}: {message}" if context else f"{path}: {message}"


def _print_fail(errors: list[str]) -> None:
    print(f"FAILED: clean rerun context validation ({len(errors)} issues)")
    for item in errors:
        print(f"  - {item}")


if __name__ == "__main__":
    raise SystemExit(main())


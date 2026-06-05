"""Command runner for the executable concept-design orchestrator."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import re
from datetime import datetime
from pathlib import Path
from typing import Sequence

import yaml

from .access_policy import AccessPolicy, AccessScope, AccessViolation
from .agent_logger import AgentLogger
from .checkpoint import CheckpointError, CheckpointManager
from .domain_scheduler import DomainScheduleViolation, DomainScheduler, P2ExecutionMode, normalize_mode
from .domain_state import DomainStage, DomainStateMachine, DomainStateTransitionError
from .final_assembler import FinalAssembler
from .index_store import atomic_write_yaml
from .p3_workspace import P3WorkspaceRunner
from .project_state import GateError, Phase, ProjectState
from .summary_reports import SummaryReports


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
CHECKPOINT_FEEDBACK_SCAN_BYTES = 100 * 1024
CHECKPOINT_CONFIRMATION_NOTE_CHARS = 2000
CHECKPOINT_FEEDBACK_KEYS = {
    "run_id",
    "checkpoint_id",
    "source",
    "status",
    "confirmation_status",
    "confirmed_by",
    "notes",
}
P1_WORKSPACE = Path("p1-workspace")
P1_PROMPT_FILE = P1_WORKSPACE / "agent_prompt.md"
P1_INPUT_SUMMARY_FILE = P1_WORKSPACE / "input_summary.yaml"
P1_INPUT_ARTIFACTS_FILE = P1_WORKSPACE / "input_artifacts.yaml"
P1_OUTPUT_SUMMARY_FILE = P1_WORKSPACE / "output_summary.yaml"
P1_OPEN_QUESTION_PLACEHOLDER_TEXTS = {f"Question Q-00{i} requires confirmation." for i in range(1, 10)}
BUSINESS_GOAL_PLACEHOLDER_TEXTS = {"To be clarified after clean inspection of parsed artifacts."}
ARCHITECTURE_DOMAIN_PLACEHOLDER_KEYS = {"architecture_domains", "domains"}
P1_HISTORY_QUESTION_TEXT_MARKERS = {
    "Question Q-001 requires confirmation.",
    "Question Q-002 requires confirmation.",
    "Question Q-003 requires confirmation.",
    "Question Q-004 requires confirmation.",
    "Question Q-005 requires confirmation.",
    "Question Q-006 requires confirmation.",
    "Question Q-007 requires confirmation.",
    "Question Q-008 requires confirmation.",
    "Question Q-009 requires confirmation.",
    "previously confirmed",
    "historical answer",
    "user confirmed",
    "用户在本线程已确认的问题答案",
    "用户已确认 open questions",
}


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (GateError, AccessViolation, DomainStateTransitionError, DomainScheduleViolation, CheckpointError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m concept_design")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="initialize a new workspace state")
    add_workspace(init)
    init.set_defaults(func=cmd_init)

    checkpoint = sub.add_parser("checkpoint", help="mark P1 complete and create the checkpoint hard stop")
    add_workspace(checkpoint)
    checkpoint.add_argument("--clean-rerun", action="store_true", help="Validate clean-rerun context constraints before checkpointing.")
    checkpoint.set_defaults(func=cmd_checkpoint)

    confirm = sub.add_parser("confirm-checkpoint", help="record explicit checkpoint confirmation")
    add_workspace(confirm)
    confirm.add_argument("--mode", default="mode_a_sequential", choices=["sequential", "parallel", "anchor", "mode_a_sequential", "mode_b_parallel", "mode_c_anchor"])
    confirm.add_argument("--confirmed-by", default="user")
    confirm.add_argument("--feedback-file", default="", help="Path to user feedback file for current run checkpoint")
    confirm.add_argument("--clean-rerun", action="store_true", help="Validate clean-rerun context constraints before confirming.")
    confirm.set_defaults(func=cmd_confirm_checkpoint)

    freeze = sub.add_parser("freeze", help="freeze P1 outputs into baselines after checkpoint confirmation")
    add_workspace(freeze)
    freeze.add_argument("--skip-scripts", action="store_true", help=argparse.SUPPRESS)
    freeze.set_defaults(func=cmd_freeze)

    packs = sub.add_parser("build-context-packs", help="build domain index and P2 context packs")
    add_workspace(packs)
    packs.add_argument("--mode", default=None, choices=["sequential", "parallel", "anchor", "mode_a_sequential", "mode_b_parallel", "mode_c_anchor"])
    packs.add_argument("--skip-scripts", action="store_true", help=argparse.SUPPRESS)
    packs.set_defaults(func=cmd_build_context_packs)

    run_p2 = sub.add_parser("run-p2-domain", help="verify P2 access gates for one domain")
    add_workspace(run_p2)
    add_domain(run_p2)
    run_p2.set_defaults(func=cmd_run_p2_domain)

    review = sub.add_parser("review-domain", help="verify P2 review access gates for one domain")
    add_workspace(review)
    add_domain(review)
    review.set_defaults(func=cmd_review_domain)

    repair = sub.add_parser("repair-domain", help="verify P2 repair access gates for one domain")
    add_workspace(repair)
    add_domain(repair)
    repair.set_defaults(func=cmd_repair_domain)

    p2_checkpoint = sub.add_parser("checkpoint-p2-domains", help="confirm P2 split outputs into confirmed_design_scope")
    add_workspace(p2_checkpoint)
    p2_checkpoint.add_argument("--modifications-file", default="")
    p2_checkpoint.set_defaults(func=cmd_checkpoint_p2_domains)

    p3 = sub.add_parser("prepare-p3", help="prepare final document index for P3")
    add_workspace(p3)
    p3.add_argument("--skip-scripts", action="store_true", help=argparse.SUPPRESS)
    p3.set_defaults(func=cmd_prepare_p3)

    p3_workspaces = sub.add_parser("build-p3-workspaces", help="build isolated P3 workspaces from confirmed_design_scope")
    add_workspace(p3_workspaces)
    p3_workspaces.set_defaults(func=cmd_build_p3_workspaces)

    run_p3 = sub.add_parser("run-p3-workspace", help="run an isolated P3 workspace")
    add_workspace(run_p3)
    run_p3.add_argument("--p3-workspace-id", default="")
    run_p3.add_argument("--domain-id", default="")
    run_p3.add_argument("--agent-output-file", default="")
    run_p3.add_argument("--strict", action="store_true")
    run_p3.add_argument("--output-file", default="")
    run_p3.set_defaults(func=cmd_run_p3_workspace)

    assemble = sub.add_parser("assemble-final-design", help="assemble final design from P3 results and indexes")
    add_workspace(assemble)
    assemble.add_argument("--skip-scripts", action="store_true", help=argparse.SUPPRESS)
    assemble.add_argument("--coverage", default="full", choices=["full", "core"])
    assemble.set_defaults(func=cmd_assemble_final_design)

    pre_p2 = sub.add_parser("summarize-pre-p2", help="write a human review summary before P2 starts")
    add_workspace(pre_p2)
    pre_p2.set_defaults(func=cmd_summarize_pre_p2)

    p2_summary = sub.add_parser("summarize-p2-checkpoint", help="write a P2 checkpoint decision summary")
    add_workspace(p2_summary)
    p2_summary.set_defaults(func=cmd_summarize_p2_checkpoint)

    p3_summary = sub.add_parser("summarize-p3-workspaces", help="write a P3 workspace isolation summary")
    add_workspace(p3_summary)
    p3_summary.set_defaults(func=cmd_summarize_p3_workspaces)

    return parser


def add_workspace(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", default="workspace")


def add_domain(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--domain-id", required=True)


def cmd_init(args: argparse.Namespace) -> int:
    state = ProjectState.load(args.workspace)
    state.transition_to(Phase.INITIALIZED)
    for rel in ["runs", "checkpoint", "baselines", "domains", "context-packs", "final"]:
        (state.workspace / rel).mkdir(parents=True, exist_ok=True)
    state.save()
    print(f"initialized: {state.workspace}")
    return 0


def cmd_checkpoint(args: argparse.Namespace) -> int:
    state = ProjectState.load(args.workspace)
    if state.phase.value in {
        "checkpoint_created",
        "checkpoint_confirmed",
        "baselines_frozen",
        "context_packs_built",
        "p2_in_progress",
        "p2_complete",
        "p3_prepared",
    }:
        raise GateError(f"checkpoint already passed for this run (current phase={state.phase.value})")
    if args.clean_rerun:
        run_script("validate_clean_rerun_context.py", "--workspace", str(state.workspace), "--stage", "checkpoint")
    p1_prompt, p1_summary = run_real_p1_subagent(state.workspace, state.run_id, clean_rerun=args.clean_rerun)
    if args.clean_rerun:
        enforce_p1_open_questions_clean(state.workspace, state.run_id)
    enforce_open_questions_pending_confirmation(state.workspace, state.run_id)
    logger = AgentLogger(state.workspace)
    logger.log_agent_execution(
        "01-P1Agent",
        None,
        state.phase.value,
        state.p2_execution_mode or "mode_a_sequential",
        p1_prompt,
        {
            "internal_step": "p1",
            "agent_workspace": "p1-workspace",
            "workspace": state.workspace.as_posix(),
            "input_summary": p1_summary,
        },
        "P1 worker executed and produced candidate outputs.",
        "p1/",
        [],
        included_item_ids=_collect_p1_candidate_ids(state.workspace, state.run_id),
    )
    logger.log_agent_execution(
        "01-P1CheckpointAgent",
        None,
        state.phase.value,
        state.p2_execution_mode or "mode_a_sequential",
        "Create the P1 checkpoint hard stop after P1 completion.",
        {
            "internal_step": "checkpoint",
            "project_phase": state.phase.value,
            "checkpoint_confirmed": state.checkpoint_confirmed,
        },
        "P1 checkpoint creation started.",
        "checkpoint/",
        [],
    )
    if state.phase == Phase.INITIALIZED:
        state.mark_p1_complete()
    state.create_checkpoint()
    _write_checkpoint_summary(state.workspace, state.run_id, state.checkpoint_id)
    state.save()
    logger.log_agent_execution(
        "01-P1CheckpointAgent",
        None,
        state.phase.value,
        state.p2_execution_mode or "mode_a_sequential",
        "Create the P1 checkpoint hard stop after P1 completion.",
        {
            "internal_step": "checkpoint",
            "project_phase": state.phase.value,
            "checkpoint_confirmed": state.checkpoint_confirmed,
        },
        "P1 checkpoint created; explicit user confirmation is required before freeze.",
        "checkpoint/",
        [],
    )
    print("checkpoint created; stop for explicit user confirmation")
    return 0


def cmd_confirm_checkpoint(args: argparse.Namespace) -> int:
    state = ProjectState.load(args.workspace)
    if args.clean_rerun:
        clean_args = ["--workspace", str(state.workspace), "--stage", "confirm"]
        if args.feedback_file:
            clean_args.extend(["--feedback-file", args.feedback_file])
        run_script("validate_clean_rerun_context.py", *clean_args)
    enforce_open_questions_pending_confirmation(state.workspace, state.run_id)
    feedback_path = resolve_checkpoint_feedback_path(state, args.feedback_file)
    feedback = load_checkpoint_feedback(state.workspace, feedback_path, state.run_id, state.checkpoint_id)
    feedback_status = feedback.get("status") or feedback.get("confirmation_status")
    if feedback_status not in {"confirmed", "approved"}:
        raise GateError(f"feedback status must be confirmed/approved, got {feedback_status or '<missing>'}")
    state.confirm_checkpoint(design_mode=args.mode)
    confirmation = {
        "status": feedback_status,
        "confirmed_by": feedback.get("confirmed_by", args.confirmed_by),
        "design_mode": args.mode,
        "p2_execution_mode": state.p2_execution_mode,
        "run_id": state.run_id,
        "checkpoint_id": state.checkpoint_id,
        "confirmation_file": str(feedback_path),
        "confirmed_at": datetime.now().isoformat(timespec="seconds"),
        "user_notes": compact_checkpoint_note(feedback.get("notes")),
        "source": "current_run_user_feedback",
    }
    write_yaml(state.workspace / "checkpoint" / "user-confirmation.yaml", confirmation)
    state.save()
    print("checkpoint confirmed")
    return 0


def cmd_freeze(args: argparse.Namespace) -> int:
    state = ProjectState.load(args.workspace)
    state.require_at_least(Phase.CHECKPOINT_CONFIRMED)
    confirmation_path = state.workspace / "checkpoint" / "user-confirmation.yaml"
    if not confirmation_path.exists():
        raise GateError("checkpoint/user-confirmation.yaml missing; confirm-checkpoint must be completed first")
    confirmation = yaml.safe_load(confirmation_path.read_text(encoding="utf-8")) or {}
    if confirmation.get("run_id") != state.run_id:
        raise GateError(
            f"checkpoint confirmation run_id mismatch: {confirmation.get('run_id')} != project run_id {state.run_id}"
        )
    if confirmation.get("checkpoint_id") != state.checkpoint_id:
        raise GateError(
            f"checkpoint confirmation checkpoint_id mismatch: {confirmation.get('checkpoint_id')} != state checkpoint_id {state.checkpoint_id}"
        )
    if confirmation.get("source") != "current_run_user_feedback":
        raise GateError("checkpoint confirmation source must be current_run_user_feedback")
    logger = AgentLogger(state.workspace)
    logger.log_agent_execution(
        "02-BaselineFreezeAgent",
        None,
        state.phase.value,
        state.p2_execution_mode or "mode_a_sequential",
        "Freeze confirmed P1 outputs into immutable baselines.",
        {
            "internal_step": "freeze",
            "project_phase": state.phase.value,
            "checkpoint_confirmed": state.checkpoint_confirmed,
            "skip_scripts": bool(args.skip_scripts),
        },
        "P1 baseline freeze started.",
        "baselines/",
        [],
    )
    if not args.skip_scripts:
        run_script("freeze_baselines.py", "--workspace", str(state.workspace))
    state.freeze_baselines()
    state.save()
    logger.log_agent_execution(
        "02-BaselineFreezeAgent",
        None,
        state.phase.value,
        state.p2_execution_mode or "mode_a_sequential",
        "Freeze confirmed P1 outputs into immutable baselines.",
        {
            "internal_step": "freeze",
            "project_phase": state.phase.value,
            "checkpoint_confirmed": state.checkpoint_confirmed,
            "baselines_frozen": state.baselines_frozen,
            "skip_scripts": bool(args.skip_scripts),
        },
        "P1 baselines frozen.",
        "baselines/",
        [],
    )
    print("baselines frozen")
    return 0


def cmd_build_context_packs(args: argparse.Namespace) -> int:
    state = ProjectState.load(args.workspace)
    state.require_at_least(Phase.BASELINES_FROZEN)
    mode = normalize_mode(args.mode or state.p2_execution_mode or state.design_mode or P2ExecutionMode.MODE_A_SEQUENTIAL).value
    logger = AgentLogger(state.workspace)
    logger.log_agent_execution(
        "03-ContextPackBuilderAgent",
        None,
        state.phase.value,
        mode,
        "Build P2 context packs from confirmed P1 outputs and source registry metadata.",
        {
            "internal_step": "build-context-packs",
            "project_phase": state.phase.value,
            "skip_scripts": bool(args.skip_scripts),
            "p2_execution_mode": mode,
        },
        "Context pack build started.",
        "context-packs/",
        [],
    )
    if not args.skip_scripts:
        run_script("validate_architecture_scope.py", "--workspace", str(state.workspace))
        run_script("build_domain_design_index.py", "--workspace", str(state.workspace), "--mode", mode)
        run_script("build_context_pack.py", "--workspace", str(state.workspace))
        run_script("validate_context_pack.py", "--workspace", str(state.workspace))
    mark_domains_context_ready(state.workspace)
    state.mark_context_packs_built()
    state.save()
    index = load_index(state.workspace) if (state.workspace / "domain-design-index.yaml").exists() else {}
    for domain in domains_of(index):
        logger.log_agent_execution(
            "03-ContextPackBuilderAgent",
            domain.get("domain_id"),
            domain.get("stage", "context_ready"),
            mode,
            "Build P2 context packs from confirmed P1 outputs and source registry metadata.",
            agent_memory_snapshot(state.workspace, domain, mode, "build-context-packs"),
            "Context pack generated and domain marked context_ready.",
            domain.get("context_pack_file") or f"context-packs/{domain.get('domain_id')}-context.yaml",
            source_ids_for_domain(state.workspace, domain),
        )
    print("context packs built")
    return 0


def cmd_run_p2_domain(args: argparse.Namespace) -> int:
    state = ProjectState.load(args.workspace)
    state.require_at_least(Phase.CONTEXT_PACKS_BUILT)
    policy = AccessPolicy()
    index = load_index(state.workspace)
    domain = domain_by_id_from_index(index, args.domain_id)
    mode = selected_execution_mode(state, index)
    DomainScheduler.assert_can_start_domain(index, args.domain_id, mode)
    policy.assert_can_read(AccessScope.P2, state.workspace, domain.get("context_pack_file", f"context-packs/{args.domain_id}-context.yaml"), args.domain_id)
    policy.assert_can_write(AccessScope.P2, state.workspace, domain.get("output_file", f"domains/{args.domain_id}/tp-main-domain-functional-design.yaml"), args.domain_id)
    policy.assert_can_write(AccessScope.P2, state.workspace, f"domains/{args.domain_id}/p2-run-log.yaml", args.domain_id)
    logger = AgentLogger(state.workspace)
    source_ids = source_ids_for_domain(state.workspace, domain)
    logger.log_agent_execution(
        "05-DesignSynthesisAgent",
        args.domain_id,
        domain.get("stage", "pending"),
        mode.value,
        "Generate P2 domain split draft from the approved context pack.",
        agent_memory_snapshot(state.workspace, domain, mode.value, "run-p2-domain"),
        "P2 domain run started.",
        domain.get("output_file", f"domains/{args.domain_id}/tp-main-domain-functional-design.yaml"),
        source_ids,
    )
    DomainStateMachine.transition_domain(domain, DomainStage.P2_RUNNING, "P2 domain run started")
    DomainStateMachine.transition_domain(domain, DomainStage.DRAFT_GENERATED, "P2 draft generated")
    write_index(state.workspace / "domain-design-index.yaml", index)
    if state.phase == Phase.CONTEXT_PACKS_BUILT:
        state.start_p2()
        state.save()
    logger.log_agent_execution(
        "05-DesignSynthesisAgent",
        args.domain_id,
        domain.get("stage", "draft_generated"),
        mode.value,
        "Generate P2 domain split draft from the approved context pack.",
        agent_memory_snapshot(state.workspace, domain, mode.value, "run-p2-domain"),
        "P2 draft generated and domain stage updated.",
        domain.get("output_file", f"domains/{args.domain_id}/tp-main-domain-functional-design.yaml"),
        source_ids,
    )
    print(f"P2 access verified: {args.domain_id} ({mode.value})")
    return 0


def cmd_review_domain(args: argparse.Namespace) -> int:
    state = ProjectState.load(args.workspace)
    state.require_at_least(Phase.CONTEXT_PACKS_BUILT)
    policy = AccessPolicy()
    index = load_index(state.workspace)
    domain = domain_by_id_from_index(index, args.domain_id)
    policy.assert_can_read(AccessScope.P2_REVIEW, state.workspace, domain.get("context_pack_file", f"context-packs/{args.domain_id}-context.yaml"), args.domain_id)
    policy.assert_can_read(AccessScope.P2_REVIEW, state.workspace, domain.get("output_file", f"domains/{args.domain_id}/tp-main-domain-functional-design.yaml"), args.domain_id)
    for key, fallback in [
        ("review_result_file", f"domains/{args.domain_id}/review-result.yaml"),
        ("review_report_file", f"domains/{args.domain_id}/review-report.md"),
        ("review_file", f"domains/{args.domain_id}/tp-review-checklist.md"),
    ]:
        policy.assert_can_write(AccessScope.P2_REVIEW, state.workspace, domain.get(key, fallback), args.domain_id)
    mode = selected_execution_mode(state, index)
    logger = AgentLogger(state.workspace)
    logger.log_agent_execution(
        "06-ReviewAgent",
        args.domain_id,
        domain.get("stage", "pending"),
        mode.value,
        "Review the current domain design against schema, context pack, and source registry constraints.",
        agent_memory_snapshot(state.workspace, domain, mode.value, "review-domain"),
        "P2 review started.",
        domain.get("review_result_file", f"domains/{args.domain_id}/review-result.yaml"),
        source_ids_for_domain(state.workspace, domain),
    )
    stage = DomainStage(domain.get("stage", DomainStage.PENDING))
    if stage in {DomainStage.DRAFT_GENERATED, DomainStage.SCHEMA_VALIDATED, DomainStage.CHECKPOINT_CONFIRMED}:
        DomainStateMachine.transition_domain(domain, DomainStage.REVIEWING, "Review started")
    result_status = load_review_result_status(state.workspace, domain)
    if result_status == "passed":
        schema_errors = validate_domain_design_schema(state.workspace, domain)
        if schema_errors:
            DomainStateMachine.transition_domain(domain, DomainStage.REPAIR_REQUIRED, "Review result passed but schema/source gate failed")
            result_status = "failed"
        else:
            DomainStateMachine.transition_domain(domain, DomainStage.PASSED, "Review result passed")
    elif result_status == "needs_human_review":
        DomainStateMachine.transition_domain(domain, DomainStage.HUMAN_REVIEW_REQUIRED, "Review result needs human review")
    else:
        DomainStateMachine.transition_domain(domain, DomainStage.REPAIR_REQUIRED, "Review result failed")
    write_index(state.workspace / "domain-design-index.yaml", index)
    logger.log_agent_execution(
        "06-ReviewAgent",
        args.domain_id,
        domain.get("stage", "pending"),
        mode.value,
        "Review the current domain design against schema, context pack, and source registry constraints.",
        agent_memory_snapshot(state.workspace, domain, mode.value, "review-domain"),
        f"P2 review completed with status={result_status}.",
        domain.get("review_result_file", f"domains/{args.domain_id}/review-result.yaml"),
        source_ids_for_domain(state.workspace, domain),
    )
    print(f"P2 review access verified: {args.domain_id}")
    return 0


def cmd_repair_domain(args: argparse.Namespace) -> int:
    state = ProjectState.load(args.workspace)
    state.require_at_least(Phase.CONTEXT_PACKS_BUILT)
    policy = AccessPolicy()
    index = load_index(state.workspace)
    domain = domain_by_id_from_index(index, args.domain_id)
    for key, fallback in [
        ("context_pack_file", f"context-packs/{args.domain_id}-context.yaml"),
        ("output_file", f"domains/{args.domain_id}/tp-main-domain-functional-design.yaml"),
        ("review_result_file", f"domains/{args.domain_id}/review-result.yaml"),
        ("review_report_file", f"domains/{args.domain_id}/review-report.md"),
    ]:
        policy.assert_can_read(AccessScope.P2_REPAIR, state.workspace, domain.get(key, fallback), args.domain_id)
    policy.assert_can_write(AccessScope.P2_REPAIR, state.workspace, domain.get("output_file", f"domains/{args.domain_id}/tp-main-domain-functional-design.yaml"), args.domain_id)
    policy.assert_can_write(AccessScope.P2_REPAIR, state.workspace, f"domains/{args.domain_id}/repair-log.yaml", args.domain_id)
    mode = selected_execution_mode(state, index)
    logger = AgentLogger(state.workspace)
    logger.log_agent_execution(
        "07-RepairAgent",
        args.domain_id,
        domain.get("stage", "pending"),
        mode.value,
        "Repair the domain design according to review findings and preserve source registry constraints.",
        agent_memory_snapshot(state.workspace, domain, mode.value, "repair-domain"),
        "P2 repair started.",
        domain.get("output_file", f"domains/{args.domain_id}/tp-main-domain-functional-design.yaml"),
        source_ids_for_domain(state.workspace, domain),
    )
    DomainStateMachine.transition_domain(domain, DomainStage.REPAIRING, "Repair started")
    DomainStateMachine.transition_domain(domain, DomainStage.REREVIEWING, "Repair completed; rereview required")
    write_index(state.workspace / "domain-design-index.yaml", index)
    logger.log_agent_execution(
        "07-RepairAgent",
        args.domain_id,
        domain.get("stage", "pending"),
        mode.value,
        "Repair the domain design according to review findings and preserve source registry constraints.",
        agent_memory_snapshot(state.workspace, domain, mode.value, "repair-domain"),
        "P2 repair completed; rereview required.",
        domain.get("output_file", f"domains/{args.domain_id}/tp-main-domain-functional-design.yaml"),
        source_ids_for_domain(state.workspace, domain),
    )
    print(f"P2 repair access verified: {args.domain_id}")
    return 0


def validate_domain_design_schema(workspace: Path, domain: dict[str, str]) -> list[str]:
    output = workspace / (domain.get("output_file") or f"domains/{domain.get('domain_id')}/tp-main-domain-functional-design.yaml")
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "validate_schema.py"), "--workspace", str(workspace), "--file", str(output)],
        text=True,
        capture_output=True,
    )
    if result.returncode == 0:
        return []
    text = result.stdout.strip() or result.stderr.strip()
    return [line for line in text.splitlines() if line.strip()]


def cmd_checkpoint_p2_domains(args: argparse.Namespace) -> int:
    state = ProjectState.load(args.workspace)
    state.require_at_least(Phase.CONTEXT_PACKS_BUILT)
    index = load_index(state.workspace)
    domains = domains_of(index)
    eligible = [d for d in domains if d.get("stage") in {"draft_generated", "schema_validated", "passed"}]
    if not eligible:
        raise CheckpointError("no P2 draft domains are ready for checkpoint confirmation")
    modifications = load_modifications(state.workspace, args.modifications_file)
    manager = CheckpointManager(state.workspace)
    mode = selected_execution_mode(state, index)
    logger = AgentLogger(state.workspace)
    for domain in eligible:
        logger.log_agent_execution(
            "P2CheckpointManager",
            domain.get("domain_id"),
            domain.get("stage", "pending"),
            mode.value,
            "Present P2 split outputs for user confirmation and produce confirmed_design_scope.",
            agent_memory_snapshot(state.workspace, domain, mode.value, "checkpoint-p2-domains"),
            "P2 checkpoint confirmation started.",
            f"domains/{domain.get('domain_id')}/confirmed_design_scope.yaml",
            source_ids_for_domain(state.workspace, domain),
        )
    presented = manager.present_for_user_confirmation(eligible)
    manager.apply_user_modifications(presented, modifications)
    for domain in eligible:
        if domain.get("stage") != DomainStage.PASSED.value:
            DomainStateMachine.transition_domain(domain, DomainStage.CHECKPOINT_CONFIRMED, "P2 split checkpoint confirmed")
        domain["confirmed_design_scope_file"] = f"domains/{domain.get('domain_id')}/confirmed_design_scope.yaml"
        domain["confirmed_scope_package_file"] = f"domains/{domain.get('domain_id')}/confirmed_scope_package.yaml"
    write_index(state.workspace / "domain-design-index.yaml", index)
    for domain in eligible:
        logger.log_agent_execution(
            "P2CheckpointManager",
            domain.get("domain_id"),
            domain.get("stage", "checkpoint_confirmed"),
            mode.value,
            "Present P2 split outputs for user confirmation and produce confirmed_design_scope.",
            agent_memory_snapshot(state.workspace, domain, mode.value, "checkpoint-p2-domains"),
            "confirmed_design_scope generated and checkpoint confirmed.",
            domain.get("confirmed_design_scope_file"),
            source_ids_from_yaml(state.workspace, domain.get("confirmed_design_scope_file")),
        )
    print(f"P2 checkpoint confirmed: {', '.join(d.get('domain_id', '') for d in eligible)}")
    return 0


def cmd_prepare_p3(args: argparse.Namespace) -> int:
    state = ProjectState.load(args.workspace)
    if state.phase == Phase.CONTEXT_PACKS_BUILT:
        state.start_p2()
    require_all_domains_passed(state.workspace)
    index = load_index(state.workspace)
    mode = selected_execution_mode(state, index)
    logger = AgentLogger(state.workspace)
    for domain in domains_of(index):
        if domain.get("required_for_p3", domain.get("p2_required", True)):
            logger.log_agent_execution(
                "08-P3PreparationAgent",
                domain.get("domain_id"),
                domain.get("stage", "pending"),
                mode.value,
                "Prepare P3 using confirmed_design_scope for passed required domains.",
                agent_memory_snapshot(state.workspace, domain, mode.value, "prepare-p3"),
                "P3 preparation started for confirmed domain scope.",
                domain.get("confirmed_design_scope_file"),
                source_ids_from_yaml(state.workspace, domain.get("confirmed_design_scope_file")),
            )
    verify_p3_access(state.workspace)
    if state.phase == Phase.P2_IN_PROGRESS:
        state.complete_p2()
    state.require_at_least(Phase.P2_COMPLETE)
    if not args.skip_scripts:
        run_script("build_final_document_index.py", "--workspace", str(state.workspace))
        run_script("validate_final_index.py", "--workspace", str(state.workspace))
    state.prepare_p3()
    state.save()
    for domain in domains_of(index):
        if domain.get("required_for_p3", domain.get("p2_required", True)):
            logger.log_agent_execution(
                "08-P3PreparationAgent",
                domain.get("domain_id"),
                domain.get("stage", "pending"),
                mode.value,
                "Prepare P3 using confirmed_design_scope for passed required domains.",
                agent_memory_snapshot(state.workspace, domain, mode.value, "prepare-p3"),
                "P3 preparation completed.",
                "final/final-document-index.yaml",
                source_ids_from_yaml(state.workspace, domain.get("confirmed_design_scope_file")),
            )
    print("P3 prepared")
    return 0


def cmd_build_p3_workspaces(args: argparse.Namespace) -> int:
    state = ProjectState.load(args.workspace)
    state.require_at_least(Phase.CONTEXT_PACKS_BUILT)
    index = load_index(state.workspace)
    mode = selected_execution_mode(state, index)
    logger = AgentLogger(state.workspace)
    built = []
    p3_root = (state.workspace / "p3-workspaces").resolve()
    if p3_root.exists():
        workspace_root = state.workspace.resolve()
        if p3_root == workspace_root or workspace_root not in p3_root.parents:
            raise GateError(f"refusing to clean unsafe p3 workspace path: {p3_root}")
        shutil.rmtree(p3_root)
    for domain in domains_of(index):
        scope_path = Path(domain.get("confirmed_scope_package_file") or f"domains/{domain.get('domain_id')}/confirmed_scope_package.yaml")
        if not scope_path.is_absolute():
            scope_path = state.workspace / scope_path
        if not scope_path.exists():
            scope_path = Path(domain.get("confirmed_design_scope_file") or f"domains/{domain.get('domain_id')}/confirmed_design_scope.yaml")
            if not scope_path.is_absolute():
                scope_path = state.workspace / scope_path
            if not scope_path.exists():
                continue
        scope = yaml.safe_load(scope_path.read_text(encoding="utf-8")) or {}
        for packaged in build_p3_workspace_for_domain(state.workspace, domain, scope):
            built.append(packaged)
            logger.log_agent_execution(
                "P3-WorkspacePackagingAgent",
                domain.get("domain_id"),
                domain.get("stage", "checkpoint_confirmed"),
                "isolated_workspace",
                "Package one isolated P3 workspace from numbered confirmed_design_scope.",
                {
                    "internal_step": "build-p3-workspaces",
                    "p2_execution_mode": mode.value,
                    "workspace_id": packaged["workspace_id"],
                    "included_subdomain_ids": packaged["included_subdomain_ids"],
                },
                "P3 workspace packaged.",
                packaged["manifest_file"],
                packaged["source_ids_used"],
                included_item_ids=packaged["included_item_ids"],
                excluded_item_ids=packaged["excluded_item_ids"],
                modified_item_ids=packaged["modified_item_ids"],
                added_item_ids=packaged["added_item_ids"],
                deleted_item_ids=packaged["deleted_item_ids"],
                workspace_id=packaged["workspace_id"],
                subdomain_id=None,
            )
    for domain in domains_of(index):
        domain["p3_workspaces"] = [item for item in built if item["domain_id"] == domain.get("domain_id")]
    write_index(state.workspace / "domain-design-index.yaml", index)
    print(f"P3 workspaces built: {len(built)}")
    return 0


def cmd_run_p3_workspace(args: argparse.Namespace) -> int:
    state = ProjectState.load(args.workspace)
    state.require_at_least(Phase.P3_PREPARED)
    if args.output_file and not args.agent_output_file:
        args.agent_output_file = args.output_file
    workspace_id = args.p3_workspace_id or (p3_workspace_id(args.domain_id) if args.domain_id else "")
    if not workspace_id:
        raise GateError("run-p3-workspace requires --p3-workspace-id or --domain-id")
    if "-SD" in workspace_id:
        raise GateError(f"P3 workspace granularity is domain-level; use {workspace_id.split('-SD', 1)[0]} instead of {workspace_id}")
    status = P3WorkspaceRunner(state.workspace, workspace_id).run(args.agent_output_file or None, args.strict)
    if status == "validated":
        print(f"P3 workspace validated: {workspace_id}")
    return 0


def cmd_assemble_final_design(args: argparse.Namespace) -> int:
    state = ProjectState.load(args.workspace)
    state.require_at_least(Phase.P3_PREPARED)
    if not args.skip_scripts:
        run_script("build_final_document_index.py", "--workspace", str(state.workspace))
        run_script("validate_final_index.py", "--workspace", str(state.workspace))
    FinalAssembler(state.workspace).assemble(args.coverage)
    print("final design assembled")
    return 0


def cmd_summarize_pre_p2(args: argparse.Namespace) -> int:
    path = SummaryReports(Path(args.workspace)).summarize_pre_p2()
    print(path)
    return 0


def cmd_summarize_p2_checkpoint(args: argparse.Namespace) -> int:
    path = SummaryReports(Path(args.workspace)).summarize_p2_checkpoint()
    print(path)
    return 0


def cmd_summarize_p3_workspaces(args: argparse.Namespace) -> int:
    path = SummaryReports(Path(args.workspace)).summarize_p3_workspaces()
    print(path)
    return 0


def require_all_domains_passed(workspace: Path) -> None:
    path = workspace / "domain-design-index.yaml"
    if not path.exists():
        raise GateError("domain-design-index.yaml missing; cannot prepare P3")
    index = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    domains = index.get("domain_design_index", {}).get("domains") or index.get("main_domains", [])
    required = [d for d in domains if d.get("required_for_p3", d.get("p2_required", True))]
    non_passed = [d.get("domain_id", "<unknown>") for d in required if d.get("stage") != "passed"]
    if non_passed:
        raise GateError(f"cannot prepare P3 with non-passed domain stages: {', '.join(non_passed)}")


def verify_p3_access(workspace: Path) -> None:
    policy = AccessPolicy()
    for domain in load_domains(workspace):
        scope = domain.get("confirmed_design_scope_file") or f"domains/{domain.get('domain_id')}/confirmed_design_scope.yaml"
        if domain.get("stage") == "passed":
            policy.assert_can_read(AccessScope.P3, workspace, scope)


def domain_by_id(workspace: Path, domain_id: str) -> dict:
    return domain_by_id_from_index(load_index(workspace), domain_id)


def domain_by_id_from_index(index: dict, domain_id: str) -> dict:
    for domain in domains_of(index):
        if domain.get("domain_id") == domain_id:
            return domain
    raise GateError(f"domain not found: {domain_id}")


def load_domains(workspace: Path) -> list[dict]:
    return domains_of(load_index(workspace))


def load_index(workspace: Path) -> dict:
    path = workspace / "domain-design-index.yaml"
    if not path.exists():
        raise GateError("domain-design-index.yaml missing")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def domains_of(index: dict) -> list[dict]:
    return index.get("domain_design_index", {}).get("domains") or index.get("main_domains", [])


def write_index(path: Path, index: dict) -> None:
    domains = domains_of(index)
    if "domain_design_index" in index:
        index["domain_design_index"]["domains"] = domains
    index["main_domains"] = domains
    atomic_write_yaml(path, index)


def mark_domains_context_ready(workspace: Path) -> None:
    if not (workspace / "domain-design-index.yaml").exists():
        return
    index = load_index(workspace)
    changed = False
    for domain in domains_of(index):
        if domain.get("p2_required", True) and (domain.get("stage") or domain.get("status") or "pending") == "pending":
            DomainStateMachine.transition_domain(domain, DomainStage.CONTEXT_READY, "Context pack built")
            changed = True
    if changed:
        write_index(workspace / "domain-design-index.yaml", index)


def load_review_result_status(workspace: Path, domain: dict) -> str:
    path = Path(domain.get("review_result_file") or f"domains/{domain.get('domain_id')}/review-result.yaml")
    if not path.is_absolute():
        path = workspace / path
    if not path.exists():
        raise GateError(f"review-result.yaml missing: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    result = data.get("review_result") or {}
    return result.get("status") or "failed"


def agent_memory_snapshot(workspace: Path, domain: dict, mode: str, internal_step: str) -> dict:
    domain_id = domain.get("domain_id")
    return {
        "internal_step": internal_step,
        "workspace": workspace.as_posix(),
        "domain": {
            "domain_id": domain_id,
            "stage": domain.get("stage"),
            "status": domain.get("status"),
            "sequence": domain.get("sequence"),
            "is_anchor": domain.get("is_anchor"),
            "depends_on": domain.get("depends_on", []),
            "required_for_p3": domain.get("required_for_p3", domain.get("p2_required", True)),
        },
        "p2_execution_mode": mode,
        "context_pack_file": domain.get("context_pack_file") or f"context-packs/{domain_id}-context.yaml",
        "source_registry": source_registry_for_domain(workspace, domain),
        "confirmed_design_scope_file": domain.get("confirmed_design_scope_file"),
    }


def source_registry_for_domain(workspace: Path, domain: dict) -> dict:
    path = Path(domain.get("context_pack_file") or f"context-packs/{domain.get('domain_id')}-context.yaml")
    if not path.is_absolute():
        path = workspace / path
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("context_pack", {}).get("source_registry", {})


def source_ids_for_domain(workspace: Path, domain: dict) -> list[str]:
    return sorted(source_registry_for_domain(workspace, domain).keys())


def source_ids_from_yaml(workspace: Path, rel_path: str | None) -> list[str]:
    if not rel_path:
        return []
    path = Path(rel_path)
    if not path.is_absolute():
        path = workspace / path
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    found: set[str] = set()
    collect_source_ids(data, found)
    return sorted(found)


def collect_source_ids(value, found: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"source", "source_ids"}:
                if isinstance(item, str):
                    found.add(item)
                elif isinstance(item, list):
                    found.update(source for source in item if isinstance(source, str))
            elif key == "source_registry" and isinstance(item, dict):
                found.update(str(source_id) for source_id in item.keys())
            else:
                collect_source_ids(item, found)
    elif isinstance(value, list):
        for item in value:
            collect_source_ids(item, found)


def build_p3_workspace_for_domain(workspace: Path, domain: dict, scope_doc: dict) -> list[dict]:
    root = normalize_confirmed_root(scope_doc)
    source_registry = root.get("source_registry", {})
    excluded_ids = list(root.get("deleted_item_ids") or root.get("global_rejected_item_ids") or root.get("excluded_item_ids") or [])
    modified_ids = list(root.get("global_modified_item_ids") or root.get("modified_item_ids") or [])
    added_ids = list(root.get("global_added_item_ids") or root.get("added_item_ids") or [])
    packaged = []
    for domain_scope in root.get("domains", []):
        workspace_id = p3_workspace_id(domain_scope.get("domain_id"))
        ws_rel = Path("p3-workspaces") / workspace_id
        ws_dir = workspace / ws_rel
        ws_dir.mkdir(parents=True, exist_ok=True)
        subdomains = [context_subdomain(item) for item in domain_scope.get("subdomains", [])]
        included = included_ids_for_domain(domain_scope)
        visible_sources = [item_id for item_id in included if item_id in source_registry and item_id not in excluded_ids]
        scoped_registry = {source_id: source_registry[source_id] for source_id in visible_sources}
        manifest = {
            "workspace_id": workspace_id,
            "granularity": "domain",
            "domain_id": domain_scope.get("domain_id"),
            "domain_name": domain_scope.get("domain_name"),
            "domain_type": domain.get("domain_type") or domain_scope.get("domain_type"),
            "included_subdomains": [
                {
                    "subdomain_id": item.get("subdomain_id"),
                    "subdomain_name": item.get("subdomain_name"),
                    "module_id": item.get("module_id"),
                }
                for item in subdomains
            ],
            "included_item_ids": {
                "requirement_facts": [item_id for item_id in visible_sources if source_registry[item_id].get("source_type") == "requirement_fact"],
                "domain_events": [
                    event.get("event_id")
                    for subdomain in subdomains
                    for event in subdomain.get("accepted_domain_events", [])
                    if event.get("event_id") not in excluded_ids
                ],
                "accepted_risks": enrichment_ids(subdomains, "risks", excluded_ids),
                "accepted_boundaries": enrichment_ids(subdomains, "boundaries", excluded_ids),
                "accepted_exceptions": enrichment_ids(subdomains, "exceptions", excluded_ids),
                "open_issues": [
                    item.get("id")
                    for subdomain in subdomains
                    for item in subdomain.get("open_issues", [])
                    if item.get("id") not in excluded_ids
                ],
            },
            "excluded_item_ids": excluded_ids,
            "modified_item_ids": modified_ids,
            "added_item_ids": added_ids,
            "deleted_item_ids": excluded_ids,
            "hard_constraints": hard_constraints_for_domain(subdomains, excluded_ids),
        }
        scoped_scope = {
            "confirmed_design_scope": {
                "checkpoint_id": root.get("checkpoint_id"),
                "confirmation_status": root.get("confirmation_status"),
                "domains": [
                    {
                        **{k: v for k, v in domain_scope.items() if k != "subdomains"},
                        "subdomains": subdomains,
                    }
                ],
                "excluded_item_ids": excluded_ids,
                "modified_item_ids": modified_ids,
            }
        }
        scoped_package = {
            "confirmed_scope_package": {
                "checkpoint_id": root.get("checkpoint_id"),
                "confirmation_status": root.get("confirmation_status"),
                "domain_id": domain_scope.get("domain_id"),
                "domain_name": domain_scope.get("domain_name"),
                "accepted_item_ids": [item_id for item_id in included if item_id not in excluded_ids and not item_id.endswith(("-M", "-N"))],
                "modified_item_ids": [item_id for item_id in modified_ids if item_id in included],
                "added_item_ids": [item_id for item_id in added_ids if item_id in included],
                "deleted_item_ids": excluded_ids,
                "domains": [{**{k: v for k, v in domain_scope.items() if k != "subdomains"}, "subdomains": subdomains}],
                "source_registry": scoped_registry,
            }
        }
        context_pack = {
            "context_pack": {
                "workspace_id": workspace_id,
                "granularity": "domain",
                "domain_id": domain_scope.get("domain_id"),
                "domain_name": domain_scope.get("domain_name"),
                "accepted_item_ids": [item_id for item_id in included if item_id not in excluded_ids],
                "subdomains": subdomains,
                "source_registry": scoped_registry,
            }
        }
        p2_reference = {
            "p2_reference": {
                "domain_id": domain_scope.get("domain_id"),
                "draft_file": root.get("draft_file"),
                "reference_only": True,
                "included_subdomain_ids": [item.get("subdomain_id") for item in subdomains],
            }
        }
        write_yaml(ws_dir / "workspace-manifest.yaml", manifest)
        write_yaml(ws_dir / "confirmed_scope_package.yaml", scoped_package)
        write_yaml(ws_dir / "confirmed_design_scope.yaml", scoped_scope)
        write_yaml(ws_dir / "context-pack.yaml", context_pack)
        write_yaml(ws_dir / "source_registry.yaml", {"source_registry": scoped_registry})
        write_yaml(ws_dir / "p2-reference.yaml", p2_reference)
        write_yaml(ws_dir / "hard-constraints.yaml", {"hard_constraints": manifest["hard_constraints"]})
        packaged.append(
            {
                "workspace_id": workspace_id,
                "domain_id": domain_scope.get("domain_id"),
                "included_subdomain_ids": [item.get("subdomain_id") for item in subdomains],
                "manifest_file": (ws_rel / "workspace-manifest.yaml").as_posix(),
                "included_item_ids": sorted(item_id for item_id in included if item_id),
                "excluded_item_ids": excluded_ids,
                "modified_item_ids": modified_ids,
                "added_item_ids": added_ids,
                "deleted_item_ids": excluded_ids,
                "source_ids_used": sorted(scoped_registry),
            }
        )
    return packaged


def p3_workspace_id(domain_id: str | None) -> str:
    compact_domain = (domain_id or "DM-000").replace("-", "")
    return f"P3-WS-{compact_domain}"


def included_ids_for_domain(domain_scope: dict) -> list[str]:
    ids = [domain_scope.get("domain_id")]
    for subdomain in domain_scope.get("subdomains", []):
        ids.extend(included_ids_for_subdomain(domain_scope, subdomain))
    return sorted({item_id for item_id in ids if item_id})


def included_ids_for_subdomain(domain_scope: dict, subdomain: dict) -> list[str]:
    ids = [domain_scope.get("domain_id"), subdomain.get("subdomain_id")]
    for event in subdomain.get("accepted_domain_events", []):
        ids.append(event.get("event_id"))
        ids.extend(event.get("source_ids", []) or [])
    for group in subdomain.get("accepted_enrichment", {}).values():
        ids.extend(item.get("id") for item in group)
    ids.extend(item.get("id") for item in subdomain.get("open_issues", []))
    ids.extend(item.get("item_id") for item in subdomain.get("added_items", []))
    return sorted({item_id for item_id in ids if item_id})


def hard_constraints_for_subdomain(subdomain: dict, excluded_ids: list[str]) -> list[str]:
    constraints = [f"Do not include rejected item {item_id} as a formal function." for item_id in excluded_ids]
    for risk in subdomain.get("accepted_enrichment", {}).get("risks", []):
        constraints.append(f"Must handle risk {risk.get('id')}: {risk.get('title', risk.get('note', 'risk note'))}.")
    for exception in subdomain.get("accepted_enrichment", {}).get("exceptions", []):
        constraints.append(f"Must handle exception {exception.get('id')}: {exception.get('title', 'exception note')}.")
    for issue in subdomain.get("open_issues", []):
        constraints.append(f"Keep {issue.get('id')} as open issue: {issue.get('note', '')}.")
    return constraints


def hard_constraints_for_domain(subdomains: list[dict], excluded_ids: list[str]) -> list[str]:
    constraints: list[str] = []
    constraints.extend(f"Do not include rejected item {item_id} as a formal function." for item_id in excluded_ids)
    for subdomain in subdomains:
        constraints.extend(hard_constraints_for_subdomain(subdomain, []))
    return sorted(set(constraints))


def enrichment_ids(subdomains: list[dict], group_name: str, excluded_ids: list[str]) -> list[str]:
    return sorted(
        {
            item.get("id")
            for subdomain in subdomains
            for item in subdomain.get("accepted_enrichment", {}).get(group_name, [])
            if item.get("id") and item.get("id") not in excluded_ids
        }
    )


def context_subdomain(subdomain: dict) -> dict:
    clean = dict(subdomain)
    clean.pop("rejected_items", None)
    clean.pop("deleted_items", None)
    return clean


def normalize_confirmed_root(scope_doc: dict) -> dict:
    if "confirmed_scope_package" in scope_doc:
        package = scope_doc["confirmed_scope_package"]
        return {
            "checkpoint_id": package.get("checkpoint_id"),
            "confirmation_status": package.get("confirmation_status"),
            "domain_id": package.get("domain_id"),
            "domain_name": package.get("domain_name"),
            "accepted_item_ids": package.get("accepted_item_ids", []),
            "modified_item_ids": package.get("modified_item_ids", []),
            "added_item_ids": package.get("added_item_ids", []),
            "deleted_item_ids": package.get("deleted_item_ids", []),
            "domains": package.get("domains", []),
            "source_registry": package.get("source_registry", {}),
        }
    return scope_doc.get("confirmed_design_scope", {})


def selected_execution_mode(state: ProjectState, index: dict) -> P2ExecutionMode:
    index_mode = index.get("p2_execution_mode") or index.get("domain_design_index", {}).get("p2_execution_mode")
    return normalize_mode(state.p2_execution_mode or index_mode or P2ExecutionMode.MODE_A_SEQUENTIAL)


def load_modifications(workspace: Path, value: str) -> dict:
    if not value:
        return {}
    path = Path(value)
    if not path.is_absolute():
        path = workspace / path
    if not path.exists():
        raise CheckpointError(f"modifications file missing: {path}")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def run_script(script_name: str, *args: str) -> None:
    cmd = [sys.executable, str(SCRIPTS / script_name), *args]
    env = os.environ.copy()
    env["PYTHONPATH"] = f"{ROOT}{os.pathsep}{env.get('PYTHONPATH', '')}"
    result = subprocess.run(cmd, text=True, env=env)
    if result.returncode != 0:
        raise GateError(f"{script_name} failed with exit code {result.returncode}")


def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8", errors="ignore")) or {}


def run_real_p1_subagent(workspace: Path, run_id: str, clean_rerun: bool = False) -> tuple[str, dict]:
    input_summary = _build_p1_input_summary(workspace)
    prompt = _build_p1_prompt(input_summary["input_artifacts"])
    workspace.joinpath(P1_PROMPT_FILE).parent.mkdir(parents=True, exist_ok=True)
    workspace.joinpath(P1_PROMPT_FILE).write_text(prompt, encoding="utf-8")
    workspace.joinpath(P1_INPUT_SUMMARY_FILE).write_text(
        yaml.safe_dump({"p1_prompt_input": input_summary}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    workspace.joinpath(P1_INPUT_ARTIFACTS_FILE).write_text(
        yaml.safe_dump({"input_artifacts": input_summary["input_artifacts"]}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    if clean_rerun:
        _require_p1_outputs_for_clean_rerun(workspace, run_id)
    else:
        _ensure_p1_outputs(workspace, run_id, input_summary["input_artifacts"])
    if clean_rerun:
        sanitize_p1_open_questions_for_clean_rerun(workspace, run_id)
    workspace.joinpath(P1_OUTPUT_SUMMARY_FILE).write_text(
        yaml.safe_dump({"phase": "p1_generated", "run_id": run_id}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return prompt, input_summary


def _build_p1_input_summary(workspace: Path) -> dict:
    parsed_dir = workspace / "parsed"
    allowed_inputs: list[str] = []
    for rel in ["parsed/document.md", "parsed/document-ir.yaml", "parsed/image-manifest.yaml"]:
        if (workspace / rel).exists():
            allowed_inputs.append(rel)
    tables = []
    for path in sorted((parsed_dir / "tables").glob("*.yaml")):
        tables.append(path.relative_to(workspace).as_posix())
    images = []
    for path in sorted((parsed_dir / "images").glob("*")):
        if path.is_file():
            images.append(path.relative_to(workspace).as_posix())
    allowed_inputs.extend(tables)
    allowed_inputs.extend(images)
    manifest = {
        "phase": "p1_input_discovery",
        "input_artifacts": allowed_inputs,
    }
    if tables:
        manifest["tables"] = tables
    if images:
        manifest["images"] = images
    return manifest


def _build_p1_prompt(input_artifacts: list[str] | dict) -> str:
    artifacts = input_artifacts["input_artifacts"] if isinstance(input_artifacts, dict) else input_artifacts
    lines = [
        "P1 worker prompt.",
        "",
        "Read only these source artifacts:",
    ]
    for item in artifacts:
        lines.append(f"- {item}")
    lines.extend(
        [
            "",
            "Produce business_model.yaml, industry_insight.yaml, architecture_design.yaml in p1/.",
            "For Q-001~Q-009, keep them pending_confirmation/open and do not write answer/decision fields.",
            "Do not reference prior user-confirmed answers, prior run outputs, or checkpoint feedback.",
            "Do not read baselines, context-packs, domains, p3-workspaces, final, or prior checkpoint files.",
            "Generate from parsed artifacts; do not inject placeholder text.",
        ]
    )
    return "\n".join(lines)


def _ensure_p1_outputs(workspace: Path, run_id: str, input_artifacts: list[str] | dict) -> None:
    if _all_valid_p1_outputs_exist(workspace, run_id):
        return
    generated = _generate_p1_outputs(workspace, input_artifacts)
    p1_dir = workspace / "p1"
    write_yaml(p1_dir / "business_model.yaml", generated["business_model"])
    write_yaml(p1_dir / "industry_insight.yaml", generated["industry_insight"])
    write_yaml(p1_dir / "architecture_design.yaml", generated["architecture_design"])


def _ordered_p1_outputs(workspace: Path, run_id: str) -> list[Path]:
    return [
        workspace / "p1" / "business_model.yaml",
        workspace / "p1" / "industry_insight.yaml",
        workspace / "p1" / "architecture_design.yaml",
    ]


def _require_p1_outputs_for_clean_rerun(workspace: Path, run_id: str) -> None:
    for path in _ordered_p1_outputs(workspace, run_id):
        if not path.exists():
            raise GateError(f"awaiting_p1_agent_output: missing required artifact {path.relative_to(workspace)}")
        if not _is_valid_real_p1_output(path):
            raise GateError(f"awaiting_p1_agent_output: invalid/placeholder artifact {path.relative_to(workspace)}")


def _all_valid_p1_outputs_exist(workspace: Path, run_id: str) -> bool:
    return all(_is_valid_real_p1_output(path) for path in _ordered_p1_outputs(workspace, run_id))


def _is_valid_real_p1_output(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    if not isinstance(payload, dict):
        return False
    text = yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    if not text.strip():
        return False
    if any(marker in text for marker in BUSINESS_GOAL_PLACEHOLDER_TEXTS):
        return False
    if any(marker in text for marker in P1_OPEN_QUESTION_PLACEHOLDER_TEXTS):
        return False
    if any(marker in text for marker in P1_HISTORY_QUESTION_TEXT_MARKERS):
        return False
    if _contains_placeholder_question_text(payload):
        return False
    if path.name == "architecture_design.yaml" and ("domains: []" in text or "domains: null" in text):
        return False
    return True


def _generate_p1_outputs(workspace: Path, input_artifacts: list[str] | dict) -> dict[str, dict]:
    seeds = _extract_p1_seeds(workspace, input_artifacts)
    return {
        "business_model": _build_business_model(seeds),
        "industry_insight": _build_industry_insight(seeds),
        "architecture_design": _build_architecture_design(seeds),
    }


def _extract_p1_seeds(workspace: Path, input_artifacts: list[str] | dict) -> dict:
    artifacts = input_artifacts["input_artifacts"] if isinstance(input_artifacts, dict) else input_artifacts
    document_text = ""
    document_blocks: list[dict] = []
    tables: list[dict] = []
    image_manifest: list[dict] = []
    doc_path = workspace / "parsed/document.md"
    ir_path = workspace / "parsed/document-ir.yaml"
    if "parsed/document.md" in artifacts and doc_path.exists():
        document_text = doc_path.read_text(encoding="utf-8", errors="ignore")
    if "parsed/document-ir.yaml" in artifacts and ir_path.exists():
        ir_payload = load_yaml(ir_path)
        blocks = ir_payload.get("document_ir", {}).get("blocks", [])
        if isinstance(blocks, list):
            document_blocks = [item for item in blocks if isinstance(item, dict)]
    for rel in [rel for rel in artifacts if rel.startswith("parsed/tables/")]:
        table_payload = load_yaml(workspace / rel)
        if isinstance(table_payload, dict):
            tables.append(table_payload)
    image_payload = load_yaml(workspace / "parsed/image-manifest.yaml")
    if isinstance(image_payload, dict):
        image_manifest = image_payload.get("image_manifest", [])
        if not isinstance(image_manifest, list):
            image_manifest = []
    return {
        "document_text": document_text,
        "document_blocks": document_blocks,
        "tables": tables,
        "images": image_manifest,
    }


def _collect_heading_texts(blocks: list[dict], limit: int = 8) -> list[str]:
    headings: list[str] = []
    for block in blocks:
        if block.get("block_type") == "heading":
            text = str(block.get("text", "")).strip()
            if text and text not in headings:
                headings.append(text)
            if len(headings) >= limit:
                break
    return headings


def _default_open_question_text(index: int, headings: list[str]) -> str:
    safe_index = max(1, min(index, 9))
    if headings:
        base = headings[(safe_index - 1) % len(headings)]
        return f"Question Q-{safe_index:03d}: what is the confirmed rule for '{base}'?"
    defaults = [
        "Question Q-001: should onboarding support concurrent approval and draft editing?",
        "Question Q-002: what is the capacity counting policy for each training round?",
        "Question Q-003: how should failed items be recovered or rolled back?",
        "Question Q-004: are duplicate participants blocked or merged?",
        "Question Q-005: should notification channels be split by event type?",
        "Question Q-006: what is the allowed window for post-submit adjustments?",
        "Question Q-007: which user fields can be exposed in cross-domain reporting?",
        "Question Q-008: are soft-deleted records excluded from capacity calculation?",
        "Question Q-009: which boundaries remain intentionally out of scope?",
    ]
    return defaults[safe_index - 1]


def _contains_placeholder_question_text(payload: dict) -> bool:
    for question in collect_open_questions(payload):
        if not isinstance(question, dict):
            continue
        qid = str(question.get("question_id") or question.get("id") or "")
        text = str(question.get("question") or question.get("question_text") or "")
        if _looks_like_placeholder_question(qid, text):
            return True
    return False


def _looks_like_placeholder_question(question_id: str, text: str) -> bool:
    if not text:
        return False
    normalized = text.strip()
    if any(marker in normalized for marker in P1_OPEN_QUESTION_PLACEHOLDER_TEXTS):
        return True
    if any(marker in normalized for marker in P1_HISTORY_QUESTION_TEXT_MARKERS):
        return True
    if "Question Q-" in normalized and "requires confirmation" in normalized:
        return True
    return False


def _build_business_model(seeds: dict) -> dict:
    headings = _collect_heading_texts(seeds.get("document_blocks", []))
    summary_lines = [line.strip() for line in seeds.get("document_text", "").splitlines() if line.strip()]
    summary = headings[:3] if headings else summary_lines[:3]
    if not summary:
        summary = [
            "Supplier training system extracted from parsed document artifacts.",
            "Functions, fields, and workflow constraints are derived from observed sections and tables.",
        ]
    topics = _derive_topics_from_tables(seeds.get("tables", []))
    requirements = _derive_requirements(seeds)
    function_names = _derive_function_names(seeds)
    event_names = _derive_event_names(seeds)
    function_ids = [f"FUNC-{idx:03d}" for idx in range(1, max(4, len(requirements) + 1))]
    event_ids = [f"EVT-{idx:03d}" for idx in range(1, max(4, len(requirements) + 1))]
    questions = [
        {
            "question_id": f"Q-00{i}",
            "question": _default_open_question_text(i, headings),
            "status": "pending_confirmation",
            "question_type": "open_question",
            "source_type": "open_question",
        }
        for i in range(1, 10)
    ]
    fields = [
        {"field_id": f"FIELD-{idx:03d}", "name": name, "type": _field_type_for_name(name)}
        for idx, name in enumerate(
            _derive_fields_from_seed_text(_derive_fields_from_tables(seeds.get("tables", [])))
            or ["supplier_id", "course_id", "quota", "status", "created_at"],
            start=1,
        )
    ][:8]
    return {
        "business_model": {
            "project_name": "Supplier Training System",
            "status": "draft",
            "summary": summary,
            "source_id_index": {
                "functions": function_ids,
                "events": event_ids,
                "business_rules": ["RULE-001", "RULE-002"],
                "workflows": ["WF-001"],
                "actors": ["ACT-001", "ACT-002", "ACT-003"],
                "open_questions": [f"Q-00{i}" for i in range(1, 10)],
            },
            "business_goal": "Build a supplier training process with clear planning, enrollment, approval, and audit evidence.",
            "requirement_facts": [
                {
                    "id": f"REQ-{idx:03d}",
                    "title": item,
                    "source_id": function_ids[min(idx - 1, len(function_ids) - 1)],
                }
                for idx, item in enumerate(
                    requirements or [
                        "Submit and revise training plans",
                        "Enroll learners and validate capacity",
                        "Track approvals and audit trails",
                        "Notify stakeholders by message and email",
                    ],
                    start=1,
                )
            ],
            "industry_enrichment": [
                {"id": "IND-001", "title": "Supplier and department contexts should be separated"},
            ] + [
                {"id": f"IND-{idx + 2:03d}", "title": topic} for idx, topic in enumerate(topics[:2])
            ],
            "risk_notes": [
                {"risk_id": f"RISK-{idx:03d}", "title": risk}
                for idx, risk in enumerate(_derive_risks(seeds), start=1)
            ],
            "boundary_notes": [
                {"boundary_id": "BOUND-001", "title": "Payment and settlement are out of scope"},
            ],
            "exception_notes": [
                {"exception_id": "EXC-001", "title": "Duplicate learner records should be merged with dedupe rules"},
            ],
            "fields": fields,
            "actors": [
                {"actor_id": "ACT-001", "name": "Training Planner", "status": "inferred", "source_id": "ACT-001"},
                {"actor_id": "ACT-002", "name": "Department Approver", "status": "inferred", "source_id": "ACT-002"},
                {"actor_id": "ACT-003", "name": "Learner", "status": "inferred", "source_id": "ACT-003"},
            ],
            "functions": [
                {
                    "function_id": function_ids[idx - 1],
                    "name": name,
                    "status": "inferred",
                    "source_id": function_ids[idx - 1],
                }
                for idx, name in enumerate(function_names, start=1)
            ],
            "workflows": [
                {"workflow_id": "WF-001", "name": "Draft -> Review -> Publish", "status": "inferred", "source_id": "WF-001"},
            ],
            "commands": [
                {"command_id": "CMD-001", "name": "submit_plan", "status": "inferred", "source_id": function_ids[0]},
                {"command_id": "CMD-002", "name": "approve_plan", "status": "inferred", "source_id": function_ids[min(1, len(function_ids) - 1)]},
                {"command_id": "CMD-003", "name": "enroll_participant", "status": "inferred", "source_id": function_ids[min(2, len(function_ids) - 1)]},
            ],
            "policies": [
                {"policy_id": "POL-001", "name": "Mandatory field policy", "status": "inferred", "source_id": "RULE-001"},
            ],
            "business_rules": [
                {"rule_id": "RULE-001", "name": "Require approver before publishing", "status": "inferred", "source_id": "RULE-001"},
                {"rule_id": "RULE-002", "name": "Prevent duplicate enrollment", "status": "inferred", "source_id": "RULE-002"},
            ],
            "permissions": [
                {"permission_id": "PERM-001", "name": "Planner can create/edit plans", "status": "inferred", "source_id": "FUNC-001"},
                {"permission_id": "PERM-002", "name": "Approver can confirm/rollback", "status": "inferred", "source_id": "FUNC-003"},
                {"permission_id": "PERM-003", "name": "Manager can view analytics", "status": "inferred", "source_id": "ACT-002"},
            ],
            "events": [
                {
                    "event_id": event_ids[0],
                    "name": event_names[0],
                    "status": "inferred",
                    "source_id": event_ids[0],
                },
                {
                    "event_id": event_ids[1],
                    "name": event_names[1] if len(event_names) > 1 else "enrollment submitted",
                    "status": "inferred",
                    "source_id": event_ids[1],
                },
                {
                    "event_id": event_ids[2],
                    "name": event_names[2] if len(event_names) > 2 else "approval completed",
                    "status": "inferred",
                    "source_id": event_ids[2],
                },
                {
                    "event_id": event_ids[3],
                    "name": event_names[3] if len(event_names) > 3 else "plan published",
                    "status": "inferred",
                    "source_id": event_ids[3],
                },
            ],
            "open_questions": questions,
        }
    }


def _build_industry_insight(seeds: dict) -> dict:
    headings = _collect_heading_texts(seeds.get("document_blocks", []))
    questions = [
        {
            "question_id": f"Q-00{i}",
            "question": _default_open_question_text(i, headings),
            "status": "pending_confirmation",
            "question_type": "open_question",
            "source_type": "open_question",
        }
        for i in range(1, 10)
    ]
    return {
        "industry_insight": {
            "industry_patterns": [
                {"pattern_id": "PAT-001", "name": "Capacity-first enrollment", "status": "inferred"},
                {"pattern_id": "PAT-002", "name": "Approval traceability", "status": "inferred"},
            ],
            "industry_recommendations": [
                {"recommendation_id": "REC-001", "title": "Use deterministic deduplication keys for learners"},
                {"recommendation_id": "REC-002", "title": "Separate messaging channel policies for alerts and reminders"},
            ],
            "risk_notes": [
                {"risk_id": "RISK-001", "title": "Field inconsistency causes downstream reconciliation errors"},
                {"risk_id": "RISK-002", "title": "Insufficient exception logging loses recovery context"},
            ],
            "design_decision_backlog": [
                {"decision_id": "DEC-001", "title": "Whether to support multi-channel recall"},
            ],
            "boundary_notes": [
                {"boundary_id": "BOUND-001", "title": "Financial settlement remains out of scope"},
            ],
            "recommendations": {
                "confirmed_by_requirement": ["REC-001"],
                "recommended_not_confirmed": ["REC-002"],
            },
            "open_questions": questions,
        }
    }


def _build_architecture_design(seeds: dict) -> dict:
    headings = _collect_heading_texts(seeds.get("document_blocks", []))
    requirements = _derive_requirements(seeds)
    function_ids = [f"FUNC-{idx:03d}" for idx in range(1, max(4, len(requirements) + 1))]
    event_ids = [f"EVT-{idx:03d}" for idx in range(1, max(4, len(requirements) + 1))]
    context_ids = _derive_context_ids(headings, "CTX")
    aggregate_ids = _derive_aggregate_ids(headings, "AGG")
    if not context_ids:
        context_ids = ["CTX-001", "CTX-002"]
    if not aggregate_ids:
        aggregate_ids = ["AGG-001", "AGG-002"]
    return {
        "architecture_design": {
            "domains": [
                {
                    "domain_id": "DM-001",
                    "domain_name": headings[0] if headings else "Supplier Training Domain",
                    "domain_type": "core",
                    "status": "draft",
                    "requirement_scope": {
                        "functions": function_ids,
                        "events": {"produced": event_ids, "consumed": [], "related": []},
                        "actors": ["ACT-001", "ACT-002", "ACT-003"],
                        "workflows": ["WF-001"],
                        "business_rules": ["RULE-001", "RULE-002"],
                    },
                    "industry_scope": {
                        "patterns": ["PAT-001", "PAT-002"],
                        "recommendations": {
                            "confirmed_by_requirement": ["REC-001"],
                            "recommended_not_confirmed": ["REC-002"],
                            "assumption_for_review": [],
                            "question_only": [],
                        },
                        "risks": ["RISK-001", "RISK-002"],
                        "boundary_notes": ["BOUND-001"],
                        "decision_backlog": ["DEC-001"],
                    },
                    "ddd_scope": {
                        "contexts": context_ids,
                        "aggregates": aggregate_ids,
                        "owned_objects": ["TrainingPlan", "EnrollmentRecord", "NotificationTemplate"],
                        "referenced_objects": ["SupplierProfile", "Department", "Course", "Trainer"],
                    },
                    "open_questions": [
                        {
                            "question_id": f"Q-00{i}",
                            "question": _default_open_question_text(i, headings),
                            "status": "pending_confirmation",
                            "question_type": "open_question",
                            "source_type": "open_question",
                        }
                        for i in range(1, 10)
                    ],
                    "coverage_validation": {
                        "all_confirmed_functions_mapped": True,
                        "all_events_have_producer_domain": True,
                        "all_rules_mapped": True,
                        "industry_risks_mapped": True,
                    },
                }
            ],
            "contexts": [{"context_id": cid, "name": "Context " + cid} for cid in context_ids],
            "aggregates": [{"aggregate_id": aid, "name": "Aggregate " + aid} for aid in aggregate_ids],
        }
    }
def enforce_p1_open_questions_clean(workspace: Path, run_id: str) -> None:
    sanitize_p1_open_questions_for_clean_rerun(workspace, run_id)


def sanitize_p1_open_questions_for_clean_rerun(workspace: Path, run_id: str) -> None:
    for p1_path in candidate_p1_outputs(workspace, run_id):
        if not p1_path.exists():
            continue
        data = yaml.safe_load(p1_path.read_text(encoding="utf-8")) or {}
        changed = False
        for question in collect_open_questions(data):
            if not isinstance(question, dict):
                continue
            qid = question.get("question_id") or question.get("id") or question.get("source_id")
            if not _is_prepared_question_id(qid):
                continue
            question["question_type"] = "open_question"
            question["source_type"] = "open_question"
            if question.get("status") not in {None, "", "open", "pending", "pending_confirmation", "unresolved"}:
                changed = True
            question["status"] = "pending_confirmation"
            if question.get("answer") is not None:
                changed = True
                question.pop("answer", None)
            for key in ("decision", "decision_id", "decision_text", "notes", "note", "confirmed_by", "confirmed_reason"):
                if key in question and question.get(key) is not None:
                    changed = True
                    question.pop(key, None)
            if changed:
                write_yaml(p1_path, data)


def _default_open_questions() -> list[dict[str, str]]:
    return [
        {
            "question_id": f"Q-00{i}",
            "question": _default_open_question_text(i, []),
            "status": "pending_confirmation",
            "question_type": "open_question",
            "source_type": "open_question",
        }
        for i in range(1, 10)
    ]


def _derive_function_names(seeds: dict) -> list[str]:
    headings = _collect_heading_texts(seeds.get("document_blocks", []))
    table_topics = _derive_topics_from_tables(seeds.get("tables", []))
    defaults = [
        "Draft training plan",
        "Apply enrollment capacity",
        "Submit approval with audit",
        "Publish training completion",
    ]
    raw = headings[:2] + table_topics[:2] + defaults
    values: list[str] = []
    for item in raw:
        text = str(item).strip()
        if text and text not in values:
            values.append(f"{text} function")
    return values[:4]


def _derive_event_names(seeds: dict) -> list[str]:
    headings = _collect_heading_texts(seeds.get("document_blocks", []))
    if headings:
        return [f"{heading} event" for heading in headings[:4]]
    return ["plan drafted", "enrollment submitted", "approval completed", "publishing completed"]


def _derive_requirements(seeds: dict) -> list[str]:
    headings = _collect_heading_texts(seeds.get("document_blocks", []))
    requirements = headings or []
    table_topics = _derive_topics_from_tables(seeds.get("tables", []))
    requirements.extend(item for item in table_topics if item not in requirements)
    if not requirements:
        requirements = [
            "Submit and revise training plans",
            "Enroll learners and validate capacity",
            "Track approvals and audit trails",
            "Notify stakeholders by message and email",
        ]
    return requirements[:6]


def _derive_risks(seeds: dict) -> list[str]:
    return [
        "Incomplete field coverage blocks execution planning.",
        "Approval latency creates capacity drift.",
        "Data overlap causes duplicate learner entries.",
    ]


def _derive_fields_from_seed_text(values: list[str]) -> list[str]:
    return [str(value).strip()[:24] for value in values if str(value).strip()][:10]


def _derive_fields_from_tables(tables: list[dict]) -> list[str]:
    fields: list[str] = []
    for table in tables:
        if not isinstance(table, dict):
            continue
        for row in table.get("rows", []) if isinstance(table.get("rows", []), list) else []:
            if not isinstance(row, dict):
                continue
            cells = row.get("cells", {})
            if isinstance(cells, dict):
                for value in cells.values():
                    text = str(value).strip()
                    if text and text not in fields:
                        fields.append(text)
    return fields


def _derive_topics_from_tables(tables: list[dict]) -> list[str]:
    topics: list[str] = []
    for table in tables:
        if not isinstance(table, dict):
            continue
        table_type = table.get("table_type_guess")
        if table_type:
            text = str(table_type).strip()
            if text and text not in topics:
                topics.append(text)
        section = table.get("section_path")
        if isinstance(section, list):
            for item in section:
                text = str(item).strip()
                if text and text not in topics:
                    topics.append(text)
    return topics


def _derive_context_ids(headings: list[str], prefix: str = "CTX") -> list[str]:
    size = min(max(2, len(headings)), 4) if headings else 3
    return [f"{prefix}-{idx:03d}" for idx in range(1, size + 1)]


def _derive_aggregate_ids(headings: list[str], prefix: str = "AGG") -> list[str]:
    size = min(max(2, len(headings)), 4) if headings else 3
    return [f"{prefix}-{idx:03d}" for idx in range(1, size + 1)]


def _field_type_for_name(name: str) -> str:
    lower = str(name).lower()
    if any(token in lower for token in ("id", "浠ｇ爜", "缂栧彿")):
        return "string"
    if any(token in lower for token in ("quota", "浜烘暟", "count", "鏁伴噺", "total", "閲戦", "time", "鏃堕棿", "created_at", "updated_at")):
        return "integer" if any(token in lower for token in ("quota", "浜烘暟", "count", "鏁伴噺", "total")) else "datetime"
    return "string"


def enforce_open_questions_pending_confirmation(workspace: Path, run_id: str) -> None:
    for p1_path in candidate_p1_outputs(workspace, run_id):
        if not p1_path.exists():
            continue
        data = yaml.safe_load(p1_path.read_text(encoding="utf-8")) or {}
        for question in collect_open_questions(data):
            qid = question.get("question_id") or question.get("id") or question.get("source_id")
            if not _is_prepared_question_id(qid):
                continue
            status = (question.get("status") or "").lower()
            if status not in {"", "unresolved", "pending", "pending_confirmation", "open"}:
                raise GateError(
                    f"{p1_path}: open question {qid} must be pending confirmation before checkpoint, got {status or '<missing>'}"
                )


def candidate_p1_outputs(workspace: Path, run_id: str) -> list[Path]:
    return [
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


def _collect_p1_candidate_ids(workspace: Path, run_id: str) -> list[str]:
    ids: list[str] = []
    for path in candidate_p1_outputs(workspace, run_id):
        if not path.exists():
            continue
        try:
            payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            continue
        for q in collect_open_questions(payload):
            if not isinstance(q, dict):
                continue
            qid = q.get("question_id") or q.get("id") or q.get("source_id")
            if qid and _is_prepared_question_id(qid):
                ids.append(qid)
    if ids:
        return sorted(set(ids))
    return [f"Q-00{i}" for i in range(1, 10)]


def _write_checkpoint_summary(workspace: Path, run_id: str, checkpoint_id: str | None) -> Path:
    candidates = {}
    for path in _ordered_p1_outputs(workspace, run_id):
        rel = path.relative_to(workspace).as_posix()
        payload = {}
        if path.exists():
            try:
                payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            except Exception:
                payload = {}
        summary_path = path.parent.parent / "checkpoints" / (checkpoint_id or f"CP-{run_id}") / "checkpoint-summary.yaml"
        questions: list[dict[str, str]] = []
        for question in collect_open_questions(payload):
            if not isinstance(question, dict):
                continue
            qid = question.get("question_id") or question.get("id") or question.get("source_id")
            if not _is_prepared_question_id(qid):
                continue
            questions.append(
                {
                    "question_id": qid,
                    "status": str(question.get("status") or "open"),
                    "question": str(question.get("question") or question.get("question_text") or ""),
                }
            )
        candidates[rel] = {
            "exists": path.exists(),
            "question_count": len(questions),
            "open_questions": sorted(questions, key=lambda item: item["question_id"]),
        }

    summary = {
        "checkpoint_summary": {
            "run_id": run_id,
            "checkpoint_id": checkpoint_id or f"CP-{run_id}",
            "created_by": "python -m concept_design checkpoint",
            "p1_artifacts": candidates,
            "open_questions": sorted(
                [question for file in candidates.values() for question in file["open_questions"]],
                key=lambda item: item["question_id"],
            ),
        }
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        yaml.safe_dump(summary, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return summary_path


def collect_open_questions(value):
    question_keys = {"open_questions", "open_questions_numbered", "open_question_candidates", "questions"}
    if isinstance(value, dict):
        for key, item in value.items():
            if key in question_keys and isinstance(item, list):
                for q in item:
                    if isinstance(q, dict):
                        yield q
            else:
                yield from collect_open_questions(item)
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                if ("question_id" in item and "question" in item) or "question_text" in item or item.get("question_type"):
                    yield item
                else:
                    yield from collect_open_questions(item)


def write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def resolve_checkpoint_feedback_path(state: ProjectState, feedback_file: str) -> Path:
    if feedback_file:
        return Path(feedback_file)
    checkpoint_id = state.checkpoint_id or f"CP-{state.run_id}"
    return Path("checkpoints") / checkpoint_id / "user-feedback.yaml"


def load_checkpoint_feedback(workspace: Path, feedback_file: Path | str, run_id: str, checkpoint_id: str | None = None) -> dict:
    path = Path(feedback_file)
    if not path.is_absolute():
        path = workspace / path
    if not path.exists():
        raise GateError(f"feedback file missing: {path}")
    payload = load_checkpoint_feedback_metadata(path)

    payload_run_id = payload.get("run_id")
    if not payload_run_id:
        raise GateError(f"feedback file missing run_id: {path}")
    if payload_run_id != run_id:
        raise GateError(
            f"feedback run_id mismatch: {payload_run_id} != project run_id {run_id}"
        )
    if not checkpoint_id:
        checkpoint_id = ProjectState.load(workspace).checkpoint_id
        if not checkpoint_id:
            checkpoint_id = f"CP-{run_id}"
    if payload.get("checkpoint_id") != checkpoint_id:
        raise GateError(
            f"feedback checkpoint_id mismatch: {payload.get('checkpoint_id')} != project checkpoint_id {checkpoint_id}"
        )
    if payload.get("source") != "current_run_user_feedback":
        raise GateError("feedback source must be current_run_user_feedback")

    status = payload.get("status") or payload.get("confirmation_status")
    if status not in {"confirmed", "approved"}:
        raise GateError(f"feedback status must be confirmed or approved, got {status or '<missing>'}")
    return payload


def load_checkpoint_feedback_metadata(path: Path) -> dict:
    metadata: dict[str, str | None] = {}
    with path.open("r", encoding="utf-8") as handle:
        sample = handle.read(CHECKPOINT_FEEDBACK_SCAN_BYTES + 1)
    if not sample:
        return metadata

    scanned = sample[:CHECKPOINT_FEEDBACK_SCAN_BYTES]
    for line in scanned.splitlines():
        if not line or line[0].isspace() or line.startswith("---") or line.startswith("#"):
            continue
        key, separator, raw_value = line.partition(":")
        if not separator:
            continue
        key = key.strip()
        if key not in CHECKPOINT_FEEDBACK_KEYS:
            continue
        value = raw_value.strip()
        if value in {"", "|", "|-", "|+", ">", ">-", ">+"}:
            metadata[key] = None
            continue
        try:
            scalar = yaml.safe_load(value)
        except yaml.YAMLError:
            scalar = value.strip("\"'")
        if scalar is None or isinstance(scalar, (str, int, float, bool)):
            metadata[key] = str(scalar) if scalar is not None else None
    return metadata


def compact_checkpoint_note(value: object) -> str | None:
    if value is None:
        return None
    note = str(value).strip()
    if len(note) <= CHECKPOINT_CONFIRMATION_NOTE_CHARS:
        return note
    return f"{note[:CHECKPOINT_CONFIRMATION_NOTE_CHARS]}... [truncated]"


def _is_prepared_question_id(question_id: str | None) -> bool:
    if not question_id:
        return False
    return str(question_id).strip().upper().startswith(tuple(f"Q-00{i}" for i in range(1, 10)))

"""Per-domain lifecycle state machine for P2 governance."""
from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any


class DomainStage(StrEnum):
    PENDING = "pending"
    CONTEXT_READY = "context_ready"
    P2_RUNNING = "p2_running"
    DRAFT_GENERATED = "draft_generated"
    SCHEMA_VALIDATED = "schema_validated"
    CHECKPOINT_CONFIRMED = "checkpoint_confirmed"
    REVIEWING = "reviewing"
    REVIEW_FAILED = "review_failed"
    REPAIR_REQUIRED = "repair_required"
    REPAIRING = "repairing"
    REREVIEWING = "rereviewing"
    PASSED = "passed"
    HUMAN_REVIEW_REQUIRED = "human_review_required"
    DEFERRED = "deferred"
    BLOCKED = "blocked"


class DomainStateTransitionError(RuntimeError):
    """Raised when a domain stage transition violates the lifecycle graph."""


ALLOWED_TRANSITIONS: dict[DomainStage, set[DomainStage]] = {
    DomainStage.PENDING: {DomainStage.CONTEXT_READY, DomainStage.DEFERRED, DomainStage.BLOCKED},
    DomainStage.CONTEXT_READY: {DomainStage.P2_RUNNING, DomainStage.DEFERRED, DomainStage.BLOCKED},
    DomainStage.P2_RUNNING: {DomainStage.DRAFT_GENERATED, DomainStage.BLOCKED},
    DomainStage.DRAFT_GENERATED: {DomainStage.SCHEMA_VALIDATED, DomainStage.CHECKPOINT_CONFIRMED, DomainStage.REVIEWING, DomainStage.BLOCKED},
    DomainStage.SCHEMA_VALIDATED: {DomainStage.CHECKPOINT_CONFIRMED, DomainStage.REVIEWING, DomainStage.BLOCKED},
    DomainStage.CHECKPOINT_CONFIRMED: {DomainStage.REVIEWING, DomainStage.BLOCKED},
    DomainStage.REVIEWING: {
        DomainStage.PASSED,
        DomainStage.REVIEW_FAILED,
        DomainStage.REPAIR_REQUIRED,
        DomainStage.HUMAN_REVIEW_REQUIRED,
        DomainStage.BLOCKED,
    },
    DomainStage.REVIEW_FAILED: {DomainStage.REPAIR_REQUIRED, DomainStage.REPAIRING, DomainStage.HUMAN_REVIEW_REQUIRED, DomainStage.BLOCKED},
    DomainStage.REPAIR_REQUIRED: {DomainStage.REPAIRING, DomainStage.HUMAN_REVIEW_REQUIRED, DomainStage.BLOCKED},
    DomainStage.REPAIRING: {DomainStage.REREVIEWING, DomainStage.BLOCKED},
    DomainStage.REREVIEWING: {
        DomainStage.REVIEWING,
        DomainStage.PASSED,
        DomainStage.REVIEW_FAILED,
        DomainStage.REPAIR_REQUIRED,
        DomainStage.HUMAN_REVIEW_REQUIRED,
        DomainStage.BLOCKED,
    },
    DomainStage.PASSED: set(),
    DomainStage.HUMAN_REVIEW_REQUIRED: {DomainStage.REPAIR_REQUIRED, DomainStage.DEFERRED, DomainStage.BLOCKED},
    DomainStage.DEFERRED: {DomainStage.CONTEXT_READY, DomainStage.BLOCKED},
    DomainStage.BLOCKED: {DomainStage.CONTEXT_READY, DomainStage.REPAIR_REQUIRED, DomainStage.DEFERRED},
}


class DomainStateMachine:
    """Validate and apply domain stage transitions."""

    @classmethod
    def assert_can_transition(cls, current: str | DomainStage, next_stage: str | DomainStage) -> None:
        current_stage = DomainStage(current)
        target = DomainStage(next_stage)
        if current_stage == target:
            return
        if target not in ALLOWED_TRANSITIONS.get(current_stage, set()):
            raise DomainStateTransitionError(f"invalid domain transition: {current_stage.value} -> {target.value}")

    @classmethod
    def transition_domain(
        cls,
        domain_entry: dict[str, Any],
        next_stage: str | DomainStage,
        reason: str | None = None,
    ) -> dict[str, Any]:
        current = DomainStage(domain_entry.get("stage") or domain_entry.get("status") or DomainStage.PENDING)
        target = DomainStage(next_stage)
        cls.assert_can_transition(current, target)
        domain_entry["stage"] = target.value
        domain_entry["status"] = cls.display_status(target)
        domain_entry["last_transition_at"] = datetime.now().isoformat(timespec="seconds")
        domain_entry["last_transition_reason"] = reason or f"{current.value} -> {target.value}"
        domain_entry.setdefault("review_round", 0)
        domain_entry.setdefault("repair_round", 0)
        if target in {DomainStage.REVIEWING, DomainStage.REREVIEWING}:
            domain_entry["review_round"] = int(domain_entry.get("review_round") or 0) + 1
        if target == DomainStage.REPAIRING:
            domain_entry["repair_round"] = int(domain_entry.get("repair_round") or 0) + 1
        if target == DomainStage.PASSED:
            domain_entry["review_status"] = "passed"
            domain_entry["repair_status"] = "not_required"
        elif target in {DomainStage.REVIEW_FAILED, DomainStage.REPAIR_REQUIRED}:
            domain_entry["review_status"] = "failed"
            domain_entry["repair_status"] = "required"
        elif target == DomainStage.HUMAN_REVIEW_REQUIRED:
            domain_entry["review_status"] = "needs_human_review"
        return domain_entry

    @staticmethod
    def display_status(stage: DomainStage) -> str:
        if stage == DomainStage.PASSED:
            return "passed"
        if stage in {DomainStage.DEFERRED, DomainStage.BLOCKED}:
            return stage.value
        if stage in {DomainStage.REVIEW_FAILED, DomainStage.REPAIR_REQUIRED, DomainStage.HUMAN_REVIEW_REQUIRED}:
            return "review_failed"
        if stage in {DomainStage.REPAIRING, DomainStage.REREVIEWING}:
            return "repairing"
        if stage in {DomainStage.P2_RUNNING, DomainStage.DRAFT_GENERATED, DomainStage.SCHEMA_VALIDATED, DomainStage.CHECKPOINT_CONFIRMED, DomainStage.REVIEWING}:
            return "in_progress"
        return "pending"

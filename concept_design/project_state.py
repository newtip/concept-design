"""Project state and phase gate validation for the concept-design orchestrator."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
import time
import uuid

import yaml


class GateError(RuntimeError):
    """Raised when an orchestrator action violates a hard gate."""


class Phase(StrEnum):
    NEW = "new"
    INITIALIZED = "initialized"
    P1_COMPLETE = "p1_complete"
    CHECKPOINT_CREATED = "checkpoint_created"
    CHECKPOINT_CONFIRMED = "checkpoint_confirmed"
    BASELINES_FROZEN = "baselines_frozen"
    CONTEXT_PACKS_BUILT = "context_packs_built"
    P2_IN_PROGRESS = "p2_in_progress"
    P2_COMPLETE = "p2_complete"
    P3_PREPARED = "p3_prepared"


PHASE_ORDER: tuple[Phase, ...] = (
    Phase.NEW,
    Phase.INITIALIZED,
    Phase.P1_COMPLETE,
    Phase.CHECKPOINT_CREATED,
    Phase.CHECKPOINT_CONFIRMED,
    Phase.BASELINES_FROZEN,
    Phase.CONTEXT_PACKS_BUILT,
    Phase.P2_IN_PROGRESS,
    Phase.P2_COMPLETE,
    Phase.P3_PREPARED,
)

ALLOWED_TRANSITIONS: dict[Phase, set[Phase]] = {
    Phase.NEW: {Phase.INITIALIZED},
    Phase.INITIALIZED: {Phase.P1_COMPLETE},
    Phase.P1_COMPLETE: {Phase.CHECKPOINT_CREATED},
    Phase.CHECKPOINT_CREATED: {Phase.CHECKPOINT_CONFIRMED},
    Phase.CHECKPOINT_CONFIRMED: {Phase.BASELINES_FROZEN},
    Phase.BASELINES_FROZEN: {Phase.CONTEXT_PACKS_BUILT},
    Phase.CONTEXT_PACKS_BUILT: {Phase.P2_IN_PROGRESS},
    Phase.P2_IN_PROGRESS: {Phase.P2_COMPLETE},
    Phase.P2_COMPLETE: {Phase.P3_PREPARED},
    Phase.P3_PREPARED: set(),
}


def _new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


@dataclass
class ProjectState:
    """Persistent state for one concept-design workspace."""

    workspace: Path
    phase: Phase = Phase.NEW
    run_id: str = field(default_factory=_new_run_id)
    checkpoint_confirmed: bool = False
    baselines_frozen: bool = False
    context_packs_built: bool = False
    p2_complete: bool = False
    design_mode: str | None = None
    p2_execution_mode: str | None = None
    checkpoint_id: str | None = None
    history: list[dict[str, Any]] = field(default_factory=list)

    @property
    def path(self) -> Path:
        return self.workspace / "project-state.yaml"

    @classmethod
    def load(cls, workspace: str | Path) -> "ProjectState":
        ws = Path(workspace)
        path = ws / "project-state.yaml"
        if not path.exists():
            return cls(workspace=ws)
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw = data.get("project_state", data)
        return cls(
            workspace=ws,
            phase=Phase(raw.get("phase", Phase.NEW)),
            run_id=raw.get("run_id") or _new_run_id(),
            checkpoint_confirmed=bool(raw.get("checkpoint_confirmed", False)),
            baselines_frozen=bool(raw.get("baselines_frozen", False)),
            context_packs_built=bool(raw.get("context_packs_built", False)),
            p2_complete=bool(raw.get("p2_complete", False)),
            design_mode=raw.get("design_mode"),
            p2_execution_mode=raw.get("p2_execution_mode") or normalize_execution_mode(raw.get("design_mode")),
            checkpoint_id=raw.get("checkpoint_id"),
            history=list(raw.get("history", []) or []),
        )

    def save(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            yaml.safe_dump({"project_state": self.to_dict()}, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase.value,
            "run_id": self.run_id,
            "checkpoint_confirmed": self.checkpoint_confirmed,
            "baselines_frozen": self.baselines_frozen,
            "context_packs_built": self.context_packs_built,
            "p2_complete": self.p2_complete,
            "design_mode": self.design_mode,
            "p2_execution_mode": self.p2_execution_mode,
            "checkpoint_id": self.checkpoint_id,
            "history": self.history,
        }

    def require_at_least(self, phase: Phase) -> None:
        if PHASE_ORDER.index(self.phase) < PHASE_ORDER.index(phase):
            raise GateError(f"requires phase >= {phase.value}; current phase is {self.phase.value}")

    def can_transition_to(self, target: Phase) -> bool:
        return target in ALLOWED_TRANSITIONS.get(self.phase, set())

    def transition_to(self, target: Phase, *, note: str = "") -> None:
        if target == self.phase:
            return
        if not self.can_transition_to(target):
            raise GateError(f"invalid transition: {self.phase.value} -> {target.value}")
        self._validate_target_gate(target)
        previous = self.phase
        self.phase = target
        self._apply_target_flags(target)
        self.history.append(
            {
                "from": previous.value,
                "to": target.value,
                "at": _now(),
                "note": note,
            }
        )

    def mark_p1_complete(self) -> None:
        self.transition_to(Phase.P1_COMPLETE, note="P1 outputs completed")

    def create_checkpoint(self) -> None:
        if not self.checkpoint_id:
            self.checkpoint_id = f"CP-{self.run_id}"
        self.transition_to(Phase.CHECKPOINT_CREATED, note="checkpoint created")

    def confirm_checkpoint(self, *, design_mode: str | None = None) -> None:
        if design_mode:
            self.design_mode = design_mode
            self.p2_execution_mode = normalize_execution_mode(design_mode)
        self.transition_to(Phase.CHECKPOINT_CONFIRMED, note="checkpoint confirmed")

    def freeze_baselines(self) -> None:
        self.transition_to(Phase.BASELINES_FROZEN, note="baselines frozen")

    def mark_context_packs_built(self) -> None:
        self.transition_to(Phase.CONTEXT_PACKS_BUILT, note="context packs built")

    def start_p2(self) -> None:
        self.transition_to(Phase.P2_IN_PROGRESS, note="P2 started")

    def complete_p2(self) -> None:
        self.transition_to(Phase.P2_COMPLETE, note="P2 complete")

    def prepare_p3(self) -> None:
        self.transition_to(Phase.P3_PREPARED, note="P3 prepared")

    def _validate_target_gate(self, target: Phase) -> None:
        if target == Phase.BASELINES_FROZEN and not self.checkpoint_confirmed:
            raise GateError("cannot freeze before checkpoint confirmation")
        if target == Phase.CONTEXT_PACKS_BUILT and not self.baselines_frozen:
            raise GateError("cannot build context packs before baselines are frozen")
        if target == Phase.P2_IN_PROGRESS and not self.context_packs_built:
            raise GateError("cannot start P2 before context packs are built")
        if target == Phase.P3_PREPARED and not self.p2_complete:
            raise GateError("cannot prepare P3 before P2 is complete")

    def _apply_target_flags(self, target: Phase) -> None:
        if target == Phase.CHECKPOINT_CONFIRMED:
            self.checkpoint_confirmed = True
        elif target == Phase.BASELINES_FROZEN:
            self.baselines_frozen = True
        elif target == Phase.CONTEXT_PACKS_BUILT:
            self.context_packs_built = True
        elif target == Phase.P2_COMPLETE:
            self.p2_complete = True


def normalize_execution_mode(value: str | None) -> str | None:
    return {
        "sequential": "mode_a_sequential",
        "parallel": "mode_b_parallel",
        "anchor": "mode_c_anchor",
    }.get(value or "", value)

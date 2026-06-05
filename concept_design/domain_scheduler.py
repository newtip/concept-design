"""Cross-domain P2 execution scheduling rules."""
from __future__ import annotations

from enum import StrEnum
from typing import Any


class P2ExecutionMode(StrEnum):
    MODE_A_SEQUENTIAL = "mode_a_sequential"
    MODE_B_PARALLEL = "mode_b_parallel"
    MODE_C_ANCHOR = "mode_c_anchor"


class DomainScheduleViolation(RuntimeError):
    """Raised when a domain cannot be started under the selected P2 mode."""


class DomainScheduler:
    """Centralized scheduler for P2 domain start decisions."""

    @classmethod
    def assert_can_start_domain(cls, domain_index: dict[str, Any], domain_id: str, mode: str | P2ExecutionMode | None) -> None:
        selected = normalize_mode(mode or domain_index.get("p2_execution_mode"))
        domain = cls._domain(domain_index, domain_id)
        if domain.get("stage") != "context_ready":
            raise DomainScheduleViolation(f"{domain_id} cannot start in {selected.value}: stage is {domain.get('stage')}")
        if selected == P2ExecutionMode.MODE_A_SEQUENTIAL:
            cls._assert_sequential(domain_index, domain)
        elif selected == P2ExecutionMode.MODE_C_ANCHOR:
            cls._assert_anchor(domain_index, domain)

    @classmethod
    def get_ready_domains(cls, domain_index: dict[str, Any], mode: str | P2ExecutionMode | None) -> list[dict[str, Any]]:
        selected = normalize_mode(mode or domain_index.get("p2_execution_mode"))
        ready = []
        for domain in cls._domains(domain_index):
            try:
                cls.assert_can_start_domain(domain_index, domain.get("domain_id", ""), selected)
            except DomainScheduleViolation:
                continue
            ready.append(domain)
        return ready

    @classmethod
    def get_blocked_domains(cls, domain_index: dict[str, Any], mode: str | P2ExecutionMode | None) -> list[dict[str, Any]]:
        selected = normalize_mode(mode or domain_index.get("p2_execution_mode"))
        blocked = []
        for domain in cls._domains(domain_index):
            if domain.get("stage") != "context_ready":
                continue
            try:
                cls.assert_can_start_domain(domain_index, domain.get("domain_id", ""), selected)
            except DomainScheduleViolation:
                blocked.append(domain)
        return blocked

    @classmethod
    def get_anchor_domain(cls, domain_index: dict[str, Any]) -> dict[str, Any]:
        anchors = [domain for domain in cls._domains(domain_index) if domain.get("is_anchor") is True]
        if not anchors:
            raise DomainScheduleViolation("mode_c_anchor requires an anchor domain")
        return sorted(anchors, key=sequence_of)[0]

    @classmethod
    def assert_anchor_passed(cls, domain_index: dict[str, Any]) -> None:
        anchor = cls.get_anchor_domain(domain_index)
        if anchor.get("stage") != "passed":
            raise DomainScheduleViolation(f"anchor domain {anchor.get('domain_id')} is not passed")

    @classmethod
    def _assert_sequential(cls, domain_index: dict[str, Any], domain: dict[str, Any]) -> None:
        for previous in sorted(cls._domains(domain_index), key=sequence_of):
            if previous is domain:
                break
            if not is_required_for_p3(previous):
                continue
            if previous.get("stage") != "passed":
                raise DomainScheduleViolation(
                    f"{domain.get('domain_id')} cannot start in mode_a_sequential: "
                    f"previous required domain {previous.get('domain_id')} is {previous.get('stage')}"
                )

    @classmethod
    def _assert_anchor(cls, domain_index: dict[str, Any], domain: dict[str, Any]) -> None:
        anchor = cls.get_anchor_domain(domain_index)
        if domain.get("domain_id") != anchor.get("domain_id") and anchor.get("stage") != "passed":
            raise DomainScheduleViolation(
                f"{domain.get('domain_id')} cannot start in mode_c_anchor: anchor {anchor.get('domain_id')} is {anchor.get('stage')}"
            )
        cls._assert_dependencies_passed(domain_index, domain, P2ExecutionMode.MODE_C_ANCHOR)

    @classmethod
    def _assert_dependencies_passed(cls, domain_index: dict[str, Any], domain: dict[str, Any], mode: P2ExecutionMode) -> None:
        for dep_id in domain.get("depends_on", []) or []:
            dep = cls._domain(domain_index, dep_id)
            if dep.get("stage") != "passed":
                raise DomainScheduleViolation(
                    f"{domain.get('domain_id')} cannot start in {mode.value}: dependency {dep_id} is {dep.get('stage')}"
                )

    @staticmethod
    def _domains(domain_index: dict[str, Any]) -> list[dict[str, Any]]:
        return domain_index.get("domain_design_index", {}).get("domains") or domain_index.get("main_domains", [])

    @classmethod
    def _domain(cls, domain_index: dict[str, Any], domain_id: str) -> dict[str, Any]:
        for domain in cls._domains(domain_index):
            if domain.get("domain_id") == domain_id:
                return domain
        raise DomainScheduleViolation(f"domain not found: {domain_id}")


def normalize_mode(mode: str | P2ExecutionMode | None) -> P2ExecutionMode:
    if isinstance(mode, P2ExecutionMode):
        return mode
    aliases = {
        None: P2ExecutionMode.MODE_A_SEQUENTIAL,
        "": P2ExecutionMode.MODE_A_SEQUENTIAL,
        "sequential": P2ExecutionMode.MODE_A_SEQUENTIAL,
        "parallel": P2ExecutionMode.MODE_B_PARALLEL,
        "anchor": P2ExecutionMode.MODE_C_ANCHOR,
    }
    if mode in aliases:
        return aliases[mode]
    return P2ExecutionMode(str(mode))


def sequence_of(domain: dict[str, Any]) -> int:
    return int(domain.get("sequence") or 999999)


def is_required_for_p3(domain: dict[str, Any]) -> bool:
    if "required_for_p3" in domain:
        return bool(domain.get("required_for_p3"))
    return bool(domain.get("p2_required", True))

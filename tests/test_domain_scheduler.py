from __future__ import annotations

import pytest

from concept_design.domain_scheduler import DomainScheduleViolation, DomainScheduler, P2ExecutionMode


def index(*domains, mode="mode_a_sequential"):
    return {"p2_execution_mode": mode, "domain_design_index": {"domains": list(domains)}}


def domain(domain_id, stage="context_ready", sequence=1, required=True, anchor=False, depends=None):
    return {
        "domain_id": domain_id,
        "stage": stage,
        "sequence": sequence,
        "required_for_p3": required,
        "is_anchor": anchor,
        "depends_on": depends or [],
    }


def ids(domains):
    return [item["domain_id"] for item in domains]


def test_mode_a_sequential_ready_and_blocked():
    ddi = index(
        domain("DM-001", "context_ready", 1, required=True),
        domain("DM-002", "context_ready", 2, required=True),
        domain("DM-003", "context_ready", 3, required=False),
    )

    assert ids(DomainScheduler.get_ready_domains(ddi, P2ExecutionMode.MODE_A_SEQUENTIAL)) == ["DM-001"]
    assert ids(DomainScheduler.get_blocked_domains(ddi, P2ExecutionMode.MODE_A_SEQUENTIAL)) == ["DM-002", "DM-003"]
    with pytest.raises(DomainScheduleViolation):
        DomainScheduler.assert_can_start_domain(ddi, "DM-002", P2ExecutionMode.MODE_A_SEQUENTIAL)


def test_mode_a_sequential_skips_non_required_without_dependency():
    ddi = index(
        domain("DM-001", "passed", 1, required=True),
        domain("DM-002", "context_ready", 2, required=False),
        domain("DM-003", "context_ready", 3, required=True),
    )

    DomainScheduler.assert_can_start_domain(ddi, "DM-003", P2ExecutionMode.MODE_A_SEQUENTIAL)


def test_mode_a_sequential_ignores_non_required_depends_on():
    ddi = index(
        domain("DM-001", "passed", 1, required=True),
        domain("DM-002", "context_ready", 2, required=False),
        domain("DM-003", "context_ready", 3, required=True, depends=["DM-002"]),
    )

    DomainScheduler.assert_can_start_domain(ddi, "DM-003", P2ExecutionMode.MODE_A_SEQUENTIAL)


def test_mode_b_parallel_ready_and_blocked():
    ddi = index(
        domain("DM-001", "context_ready", 1),
        domain("DM-002", "context_ready", 2),
        domain("DM-003", "pending", 3),
        mode="mode_b_parallel",
    )

    assert ids(DomainScheduler.get_ready_domains(ddi, P2ExecutionMode.MODE_B_PARALLEL)) == ["DM-001", "DM-002"]
    assert ids(DomainScheduler.get_blocked_domains(ddi, P2ExecutionMode.MODE_B_PARALLEL)) == []
    with pytest.raises(DomainScheduleViolation):
        DomainScheduler.assert_can_start_domain(ddi, "DM-003", P2ExecutionMode.MODE_B_PARALLEL)


def test_mode_c_anchor_ready_and_blocked_before_anchor_passed():
    ddi = index(
        domain("DM-001", "context_ready", 1, anchor=True),
        domain("DM-002", "context_ready", 2, depends=["DM-001"]),
        domain("DM-003", "context_ready", 3),
        mode="mode_c_anchor",
    )

    assert DomainScheduler.get_anchor_domain(ddi)["domain_id"] == "DM-001"
    assert ids(DomainScheduler.get_ready_domains(ddi, P2ExecutionMode.MODE_C_ANCHOR)) == ["DM-001"]
    assert ids(DomainScheduler.get_blocked_domains(ddi, P2ExecutionMode.MODE_C_ANCHOR)) == ["DM-002", "DM-003"]


def test_mode_c_anchor_depends_on_after_anchor_passed():
    ddi = index(
        domain("DM-001", "passed", 1, anchor=True),
        domain("DM-002", "context_ready", 2, depends=["DM-001"]),
        domain("DM-003", "context_ready", 3, depends=["DM-002"]),
        mode="mode_c_anchor",
    )

    DomainScheduler.assert_can_start_domain(ddi, "DM-002", P2ExecutionMode.MODE_C_ANCHOR)
    with pytest.raises(DomainScheduleViolation):
        DomainScheduler.assert_can_start_domain(ddi, "DM-003", P2ExecutionMode.MODE_C_ANCHOR)


def test_mode_c_anchor_missing_anchor_raises():
    ddi = index(domain("DM-001", "context_ready", 1), mode="mode_c_anchor")

    with pytest.raises(DomainScheduleViolation):
        DomainScheduler.get_anchor_domain(ddi)

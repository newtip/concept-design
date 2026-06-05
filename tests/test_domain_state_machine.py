from __future__ import annotations

import pytest

from concept_design.domain_state import DomainStage, DomainStateMachine, DomainStateTransitionError


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (DomainStage.PENDING, DomainStage.CONTEXT_READY),
        (DomainStage.CONTEXT_READY, DomainStage.P2_RUNNING),
        (DomainStage.P2_RUNNING, DomainStage.DRAFT_GENERATED),
        (DomainStage.DRAFT_GENERATED, DomainStage.REVIEWING),
        (DomainStage.REVIEWING, DomainStage.PASSED),
        (DomainStage.REVIEWING, DomainStage.REPAIR_REQUIRED),
        (DomainStage.REPAIR_REQUIRED, DomainStage.REPAIRING),
        (DomainStage.REPAIRING, DomainStage.REREVIEWING),
        (DomainStage.REREVIEWING, DomainStage.PASSED),
    ],
)
def test_legal_domain_stage_transitions(current, target):
    DomainStateMachine.assert_can_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (DomainStage.PENDING, DomainStage.PASSED),
        (DomainStage.DRAFT_GENERATED, DomainStage.PASSED),
        (DomainStage.REPAIR_REQUIRED, DomainStage.PASSED),
        (DomainStage.PASSED, DomainStage.P2_RUNNING),
        (DomainStage.REVIEWING, DomainStage.P2_RUNNING),
        (DomainStage.HUMAN_REVIEW_REQUIRED, DomainStage.PASSED),
    ],
)
def test_illegal_domain_stage_transitions(current, target):
    with pytest.raises(DomainStateTransitionError):
        DomainStateMachine.assert_can_transition(current, target)


def test_transition_domain_updates_metadata_and_rounds():
    domain = {"stage": "draft_generated", "status": "pending", "review_round": 0, "repair_round": 0}

    DomainStateMachine.transition_domain(domain, DomainStage.REVIEWING, "start review")

    assert domain["stage"] == "reviewing"
    assert domain["status"] == "in_progress"
    assert domain["last_transition_at"]
    assert domain["last_transition_reason"] == "start review"
    assert domain["review_round"] == 1

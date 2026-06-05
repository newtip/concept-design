from __future__ import annotations

import pytest

from concept_design.project_state import GateError, Phase, ProjectState


def test_new_state_can_be_initialized(tmp_path):
    state = ProjectState.load(tmp_path)

    state.transition_to(Phase.INITIALIZED)
    state.save()

    loaded = ProjectState.load(tmp_path)
    assert loaded.phase == Phase.INITIALIZED
    assert loaded.run_id == state.run_id


def test_cannot_skip_checkpoint_confirmation_before_freeze(tmp_path):
    state = ProjectState(workspace=tmp_path, phase=Phase.CHECKPOINT_CREATED)

    with pytest.raises(GateError, match="invalid transition"):
        state.freeze_baselines()


def test_happy_path_sets_gate_flags(tmp_path):
    state = ProjectState.load(tmp_path)

    state.transition_to(Phase.INITIALIZED)
    state.mark_p1_complete()
    state.create_checkpoint()
    state.confirm_checkpoint(design_mode="sequential")
    state.freeze_baselines()
    state.mark_context_packs_built()
    state.start_p2()
    state.complete_p2()
    state.prepare_p3()

    assert state.phase == Phase.P3_PREPARED
    assert state.checkpoint_confirmed is True
    assert state.baselines_frozen is True
    assert state.context_packs_built is True
    assert state.p2_complete is True
    assert state.design_mode == "sequential"


def test_cannot_prepare_p3_until_p2_complete(tmp_path):
    state = ProjectState(workspace=tmp_path, phase=Phase.P2_IN_PROGRESS)

    with pytest.raises(GateError, match="invalid transition"):
        state.prepare_p3()

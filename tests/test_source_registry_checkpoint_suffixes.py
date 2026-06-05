from __future__ import annotations

import pytest

from concept_design.id_registry import IdRegistry, IdRegistryError, ItemType, type_for_id
from scripts.build_source_registry import make_meta, meta_for


def test_source_registry_supports_checkpoint_suffixes_and_new_prefixes():
    assert meta_for("IMG-001") is not None
    assert meta_for("FLD-001-M") is not None
    assert meta_for("RULE-001-N") is not None
    assert make_meta("REQ-001-M", {})["source_id"] == "REQ-001-M"
    assert make_meta("IMG-001", {})["source_type"] == "image_requirement_extract"


def test_id_registry_validates_p3_workspace_and_suffix_ids():
    registry = IdRegistry()
    assert registry.register(ItemType.FIELD, "Training date") == "FLD-001"
    assert type_for_id("P3-WS-DM001") == ItemType.P3_WORKSPACE
    with pytest.raises(IdRegistryError):
        type_for_id("P3-WS-DM001-SD001")
    assert type_for_id("RULE-001-N") == ItemType.RULE
    assert type_for_id("PERM-001-M") == ItemType.PERMISSION

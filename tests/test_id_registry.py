from __future__ import annotations

import pytest

from concept_design.id_registry import IdRegistry, IdRegistryError, ItemType, as_added_id, as_modified_id


def test_register_and_validate_ids():
    registry = IdRegistry()
    req_id = registry.register(ItemType.REQUIREMENT_FACT, "Create plan")
    risk_id = registry.register(ItemType.RISK_NOTE, "Missing fields")

    assert req_id == "REQ-001"
    assert risk_id == "RISK-001"
    assert registry.validate_id(req_id, ItemType.REQUIREMENT_FACT)
    with pytest.raises(IdRegistryError):
        registry.validate_id(req_id, ItemType.RISK_NOTE)


def test_reject_duplicate_id():
    registry = IdRegistry({"REQ-001": {"item_id": "REQ-001", "item_type": "requirement_fact"}})

    with pytest.raises(IdRegistryError, match="duplicate"):
        registry.assert_unique("REQ-001")


def test_save_load_and_list_by_type(tmp_path):
    registry = IdRegistry()
    registry.register(ItemType.SUBDOMAIN, "Training Plan Drafting")
    registry.register(ItemType.DOMAIN_EVENT, "TrainingPlanSubmitted")
    path = tmp_path / "registry" / "item-registry.yaml"

    registry.save(path)
    loaded = IdRegistry.load(path)

    assert loaded.resolve("SD-001")["title"] == "Training Plan Drafting"
    assert [item["item_id"] for item in loaded.list_by_type(ItemType.DOMAIN_EVENT)] == ["EVT-001"]


def test_invalid_id_format_rejected():
    registry = IdRegistry()

    with pytest.raises(IdRegistryError):
        registry.validate_id("UNKNOWN")


def test_variant_suffix_ids_are_valid():
    registry = IdRegistry()

    assert registry.validate_id("REQ-005-N", ItemType.REQUIREMENT_FACT)
    assert registry.validate_id("REQ-003-M", ItemType.REQUIREMENT_FACT)
    assert as_added_id("REQ-005") == "REQ-005-N"
    assert as_modified_id("REQ-003") == "REQ-003-M"

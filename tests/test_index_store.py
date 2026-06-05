from __future__ import annotations

import yaml

from concept_design.index_store import atomic_write_yaml, locked_index_update


def test_atomic_write_yaml_replaces_index(tmp_path):
    path = tmp_path / "domain-design-index.yaml"
    atomic_write_yaml(path, {"main_domains": [{"domain_id": "DM-001"}]})
    atomic_write_yaml(path, {"main_domains": [{"domain_id": "DM-002"}]})

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["main_domains"][0]["domain_id"] == "DM-002"
    assert not (tmp_path / "domain-design-index.yaml.tmp").exists()
    assert not (tmp_path / "domain-design-index.yaml.lock").exists()


def test_locked_index_update_preserves_existing_yaml(tmp_path):
    path = tmp_path / "domain-design-index.yaml"
    atomic_write_yaml(path, {"main_domains": [{"domain_id": "DM-001", "stage": "pending"}]})

    def update(data):
        data["main_domains"][0]["stage"] = "passed"
        data["main_domains"].append({"domain_id": "DM-002", "stage": "context_ready"})
        return data

    locked_index_update(path, update)

    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert data["main_domains"][0]["stage"] == "passed"
    assert data["main_domains"][1]["domain_id"] == "DM-002"
    assert not (tmp_path / "domain-design-index.yaml.lock").exists()

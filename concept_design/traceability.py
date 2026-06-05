"""Traceability validators for checkpoint decisions and suffix IDs."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


DEFAULT_DESIGN_MARKERS = {"合理即可", "按合理默认设计", "reasonable default", "default design"}


def validate_checkpoint_decision_trace(workspace: str | Path) -> list[str]:
    ws = Path(workspace)
    errors: list[str] = []
    for package_path in sorted((ws / "domains").glob("*/confirmed_scope_package.yaml")):
        package = (yaml.safe_load(package_path.read_text(encoding="utf-8")) or {}).get("confirmed_scope_package", {})
        registry = package.get("source_registry", {})
        for issue in iter_open_issues(package):
            note = str(issue.get("note") or issue.get("decision") or "")
            if any(marker in note for marker in DEFAULT_DESIGN_MARKERS):
                if issue.get("decision_type") != "user_authorized_default_design":
                    errors.append(f"{package_path}: {issue.get('id') or issue.get('item_id')} missing user_authorized_default_design")
                if issue.get("decision_origin") != "checkpoint_feedback":
                    errors.append(f"{package_path}: {issue.get('id') or issue.get('item_id')} missing checkpoint_feedback origin")
                if not issue.get("must_not_be_treated_as_original_requirement", False):
                    errors.append(f"{package_path}: {issue.get('id') or issue.get('item_id')} must not be original requirement")
        for source_id, meta in registry.items():
            if meta.get("decision_type") == "user_authorized_default_design" and meta.get("decision_origin") != "checkpoint_feedback":
                errors.append(f"{package_path}: {source_id} default design source must originate from checkpoint_feedback")
    return errors


def validate_source_registry_suffixes(registry: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for source_id, meta in registry.items():
        if not isinstance(meta, dict):
            errors.append(f"{source_id}: source metadata must be object")
            continue
        if meta.get("source_id") != source_id:
            errors.append(f"{source_id}: source_id mismatch")
        base = source_id[:-2] if source_id.endswith(("-N", "-M")) else source_id
        if "-" not in base:
            errors.append(f"{source_id}: invalid source id")
        if source_id.endswith("-N") and meta.get("decision_origin") not in {None, "checkpoint_feedback"}:
            errors.append(f"{source_id}: -N source must be checkpoint-added or neutral")
        if source_id.endswith("-M") and meta.get("decision_origin") not in {None, "checkpoint_feedback"}:
            errors.append(f"{source_id}: -M source must be checkpoint-modified or neutral")
    return errors


def iter_open_issues(value: Any):
    if isinstance(value, dict):
        if "open_issues" in value and isinstance(value["open_issues"], list):
            yield from value["open_issues"]
        for item in value.values():
            yield from iter_open_issues(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_open_issues(item)

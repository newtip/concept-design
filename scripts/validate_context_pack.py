#!/usr/bin/env python3
"""Validate P2 context packs before domain design starts."""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

REQUIRED_SECTIONS = [
    "meta",
    "current_domain",
    "requirement_context",
    "industry_context",
    "domain_architecture_context",
    "related_domain_summaries",
    "negative_context",
    "decision_boundary",
    "source_registry",
]

SOURCE_REQUIRED_FIELDS = ["source_id", "category", "source_type", "status", "allowed_usage", "forbidden_usage"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    args = parser.parse_args()
    ws = Path(args.workspace)
    errors: list[str] = []
    packs = list((ws / "context-packs").glob("*.yaml"))
    if not packs:
        errors.append("context-packs/*.yaml missing")
    for file in packs:
        validate_pack(file, errors)
    if errors:
        print(f"FAILED: context pack validation ({len(errors)} errors)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASSED: context pack validation")
    return 0


def validate_pack(file: Path, errors: list[str]) -> None:
    data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    cp = data.get("context_pack", {})
    for section in REQUIRED_SECTIONS:
        if section not in cp:
            errors.append(f"{file.name}: missing context_pack.{section}")
    meta = cp.get("meta", {})
    if meta.get("status") != "frozen":
        errors.append(f"{file.name}: meta.status must be frozen")
    if not meta.get("domain_id") or not cp.get("current_domain", {}).get("domain_id"):
        errors.append(f"{file.name}: missing domain_id")
    requirement = cp.get("requirement_context", {})
    industry = cp.get("industry_context", {})
    architecture = cp.get("domain_architecture_context", {})
    domain_type = cp.get("current_domain", {}).get("domain_type")
    if cp.get("source_resolution", {}).get("missing_ids"):
        errors.append(f"{file.name}: source_resolution.missing_ids must be empty")
    if domain_type == "core":
        events = requirement.get("events", {}) or {}
        if not (requirement.get("functions") or requirement.get("workflows") or events.get("produced") or events.get("related")):
            errors.append(f"{file.name}: core domain must include functions, workflows, or events")
    elif domain_type == "supporting":
        if not (cp.get("related_domain_summaries") or architecture.get("contexts") or registry_has_any(cp.get("source_registry", {}), ["requirement", "event", "architecture"])):
            errors.append(f"{file.name}: supporting domain lacks related summaries or capability context")
    elif domain_type == "generic":
        if not (industry.get("boundary_notes") or industry.get("risk_notes") or cp.get("related_domain_summaries")):
            errors.append(f"{file.name}: generic domain lacks boundary/risk/related context")
    if "boundary_notes" not in industry or "risk_notes" not in industry:
        errors.append(f"{file.name}: industry_context must include boundary_notes and risk_notes")
    if "contexts" not in architecture or "aggregates" not in architecture:
        errors.append(f"{file.name}: domain_architecture_context must include contexts and aggregates")
    registry = cp.get("source_registry", {})
    validate_source_registry(file.name, registry, errors)
    forbidden = cp.get("negative_context", {}).get("forbidden_inference", [])
    if not forbidden:
        errors.append(f"{file.name}: negative_context.forbidden_inference is empty")


def validate_source_registry(file_name: str, registry: object, errors: list[str]) -> None:
    if not isinstance(registry, dict) or not registry:
        errors.append(f"{file_name}: source_registry must be a non-empty metadata map")
        return
    for key, meta in registry.items():
        if not isinstance(meta, dict):
            errors.append(f"{file_name}: source_registry.{key} must be metadata object, not ID array")
            continue
        for field in SOURCE_REQUIRED_FIELDS:
            if field not in meta:
                errors.append(f"{file_name}: source_registry.{key} missing {field}")
        if meta.get("source_id") != key:
            errors.append(f"{file_name}: source_registry key {key} does not match source_id {meta.get('source_id')}")
        if not isinstance(meta.get("allowed_usage"), list):
            errors.append(f"{file_name}: source_registry.{key}.allowed_usage must be list")
        if not isinstance(meta.get("forbidden_usage"), list):
            errors.append(f"{file_name}: source_registry.{key}.forbidden_usage must be list")


def registry_has_any(registry: dict, categories: list[str]) -> bool:
    return any(isinstance(meta, dict) and meta.get("category") in categories for meta in registry.values())


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate generated domain-level P3 workspace output artifacts."""
from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

import yaml


REQUIRED_ROOT_FIELDS = [
    "workspace_id",
    "granularity",
    "domain_id",
    "domain_name",
    "generated_at",
    "status",
    "input_artifacts",
    "included_item_ids",
    "excluded_item_ids",
    "modified_item_ids",
    "added_item_ids",
    "deleted_item_ids",
    "source_ids_used",
    "subdomain_designs",
    "traceability",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--file", default="")
    parser.add_argument("--p3-workspace-id", default="")
    args = parser.parse_args()
    ws = Path(args.workspace)
    if args.p3_workspace_id:
        files = [ws / "p3-workspaces" / args.p3_workspace_id / "p3-agent-output.yaml"]
    elif args.file:
        files = [Path(args.file)]
    else:
        files = list((ws / "p3-workspaces").glob("*/p3-agent-output.yaml"))
    errors: list[str] = []
    if not files:
        errors.append("no P3 workspace output files found")
    for file in files:
        validate_file(ws, file, errors)
    if errors:
        print(f"FAILED: P3 workspace output validation ({len(errors)} errors)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASSED: P3 workspace output validation")
    return 0


def validate_file(workspace: Path, file: Path, errors: list[str]) -> None:
    path = file if file.is_absolute() else workspace / file
    if not path.exists():
        errors.append(f"missing file: {path}")
        return
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    root = data.get("p3_workspace_output")
    if not isinstance(root, dict):
        errors.append(f"{path}: missing p3_workspace_output")
        return
    for field in REQUIRED_ROOT_FIELDS:
        if field not in root:
            errors.append(f"{path}: p3_workspace_output missing {field}")
    workspace_id = str(root.get("workspace_id") or "")
    if "-SD" in workspace_id:
        errors.append(f"{path}: P3 workspace must be domain-level, got subdomain workspace id {workspace_id}")
    if root.get("granularity") != "domain":
        errors.append(f"{path}: granularity must be domain")
    if root.get("subdomain_id"):
        errors.append(f"{path}: top-level subdomain_id is not allowed for domain-level P3 output")
    ws_dir = workspace / "p3-workspaces" / workspace_id
    manifest = ws_dir / "workspace-manifest.yaml"
    if workspace_id and not manifest.exists():
        errors.append(f"{path}: workspace manifest missing for {workspace_id}")
        return
    manifest_data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
    if manifest_data.get("granularity") != "domain":
        errors.append(f"{path}: workspace manifest granularity must be domain")
    if root.get("domain_id") != manifest_data.get("domain_id"):
        errors.append(f"{path}: domain_id does not match workspace manifest")
    if root.get("domain_name") and manifest_data.get("domain_name") and root.get("domain_name") != manifest_data.get("domain_name"):
        errors.append(f"{path}: domain_name does not match workspace manifest")
    validate_subdomain_coverage(path, root, manifest_data, errors)
    for field in ["included_item_ids", "excluded_item_ids", "modified_item_ids", "added_item_ids", "deleted_item_ids", "source_ids_used"]:
        if field in root and not is_string_list(root.get(field)):
            errors.append(f"{path}: {field} must be a list of strings")
    deleted = set(root.get("deleted_item_ids") or [])
    included = set(root.get("included_item_ids") or [])
    overlap = sorted(deleted & included)
    if overlap:
        errors.append(f"{path}: deleted item appears in included_item_ids: {', '.join(overlap)}")
    validate_input_artifacts(path, workspace, root, errors)
    registry_path = ws_dir / "source_registry.yaml"
    registry_doc = yaml.safe_load(registry_path.read_text(encoding="utf-8")) if registry_path.exists() else {}
    registry = registry_doc.get("source_registry", {})
    validate_sources(path, root, registry, errors)
    validate_formal_text(path, root, errors)
    validate_workspace_refs(path, root, workspace_id, errors)


def validate_subdomain_coverage(path: Path, root: dict[str, Any], manifest: dict[str, Any], errors: list[str]) -> None:
    expected = [item.get("subdomain_id") for item in manifest.get("included_subdomains", []) if item.get("subdomain_id")]
    designs = root.get("subdomain_designs")
    if not isinstance(designs, list) or not designs:
        errors.append(f"{path}: subdomain_designs must be a non-empty list")
        return
    actual = [item.get("subdomain_id") for item in designs if isinstance(item, dict)]
    if sorted(actual) != sorted(expected):
        errors.append(f"{path}: subdomain_designs must cover confirmed subdomains exactly once: expected={expected} actual={actual}")
    duplicates = sorted({item for item in actual if actual.count(item) > 1})
    if duplicates:
        errors.append(f"{path}: duplicate subdomain_designs: {', '.join(duplicates)}")


def validate_input_artifacts(path: Path, workspace: Path, root: dict[str, Any], errors: list[str]) -> None:
    artifacts = root.get("input_artifacts", {})
    if not isinstance(artifacts, dict):
        errors.append(f"{path}: input_artifacts must be a mapping")
        return
    for key, value in artifacts.items():
        artifact = workspace / value if isinstance(value, str) else None
        if artifact is None or not artifact.exists():
            errors.append(f"{path}: input_artifacts.{key} missing: {value}")


def validate_sources(path: Path, root: dict[str, Any], registry: dict[str, Any], errors: list[str]) -> None:
    source_ids_used = set(root.get("source_ids_used") or [])
    missing_sources = sorted(source_ids_used - set(registry))
    if missing_sources:
        errors.append(f"{path}: source_ids_used outside workspace registry: {', '.join(missing_sources)}")
    formal_sources = set((root.get("traceability") or {}).get("formal_source_ids") or [])
    for subdomain in root.get("subdomain_designs") or []:
        if isinstance(subdomain, dict):
            formal_sources.update((subdomain.get("traceability") or {}).get("formal_source_ids") or [])
            sub_sources = set(subdomain.get("source_ids_used") or [])
            missing = sorted(sub_sources - set(registry))
            if missing:
                errors.append(f"{path}: subdomain {subdomain.get('subdomain_id')} source_ids_used outside registry: {', '.join(missing)}")
    for source_id in sorted(formal_sources):
        meta = registry.get(source_id)
        if not meta:
            errors.append(f"{path}: formal source_id missing from registry: {source_id}")
            continue
        allowed = set(meta.get("allowed_usage") or [])
        forbidden = set(meta.get("forbidden_usage") or [])
        if not ({"formal_design", "formal_function"} & allowed) or ({"formal_design", "formal_function"} & forbidden):
            errors.append(f"{path}: source_id {source_id} is not allowed for formal P3 design")
        if meta.get("source_type") in {"industry_enrichment", "risk_note", "boundary_note", "open_question"}:
            errors.append(f"{path}: {meta.get('source_type')} {source_id} cannot be a formal P3 source")


def validate_formal_text(path: Path, root: dict[str, Any], errors: list[str]) -> None:
    formal_text = yaml.safe_dump(
        {
            "domain_data_model_design": root.get("domain_data_model_design"),
            "domain_permission_design": root.get("domain_permission_design"),
            "domain_interface_design": root.get("domain_interface_design"),
            "cross_subdomain_design": root.get("cross_subdomain_design"),
            "subdomain_designs": root.get("subdomain_designs"),
        },
        allow_unicode=True,
        sort_keys=False,
    )
    blocked_ids = set(root.get("deleted_item_ids") or []) | set(root.get("excluded_item_ids") or [])
    leaked = sorted(item_id for item_id in blocked_ids if item_id and item_id in formal_text)
    if leaked:
        errors.append(f"{path}: deleted/excluded item appears in formal design: {', '.join(leaked)}")


def validate_workspace_refs(path: Path, root: dict[str, Any], workspace_id: str, errors: list[str]) -> None:
    dumped = yaml.safe_dump(root, allow_unicode=True)
    workspace_refs = sorted(set(re.findall(r"P3-WS-[A-Za-z0-9-]+", dumped)))
    subdomain_refs = [item for item in workspace_refs if "-SD" in item]
    if subdomain_refs:
        errors.append(f"{path}: output references deprecated subdomain workspace ids: {', '.join(subdomain_refs)}")
    other_workspaces = [item for item in workspace_refs if item != workspace_id]
    if other_workspaces:
        errors.append(f"{path}: output references another P3 workspace: {', '.join(other_workspaces)}")


def is_string_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Deterministic structure validation for P2 main-domain outputs."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

MODULE_KEYS = [
    "module_positioning",
    "data_model_design",
    "function_design",
    "workflow_design",
    "page_design",
    "interface_design",
    "unsupported_design",
    "dfx_design",
    "open_issues",
]

DFX_KEYS = [
    "usability",
    "maintainability",
    "extensibility",
    "performance",
    "security",
    "observability",
    "testability",
    "reliability",
]

UNSUPPORTED_KEYS = ["unsupported_item", "unsupported_type", "reason", "impact", "workaround", "source"]
TOP_LEVEL_REQUIRED = [
    "domain",
    "domain_design_intent",
    "domain_product_structure",
    "domain_user_journeys",
    "module_relationship_design",
    "modules",
    "industry_insight_handling",
    "design_tradeoffs",
    "data_model_summary",
    "cross_domain_contract_summary",
    "unsupported_design_summary",
    "dfx_summary",
    "open_issues_summary",
    "traceability",
    "quality_checks",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--file", default="")
    args = parser.parse_args()
    ws = Path(args.workspace)
    files = [Path(args.file)] if args.file else list((ws / "domains").glob("**/*-main-domain-functional-design.yaml"))
    errors: list[str] = []
    if not files:
        errors.append("no main-domain-functional-design files found")
    for file in files:
        validate_file(ws, file, errors)
    if errors:
        print(f"FAILED: schema validation ({len(errors)} errors)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASSED: schema validation")
    return 0


def validate_file(ws: Path, file: Path, errors: list[str]) -> None:
    if not file.exists():
        errors.append(f"missing file: {file}")
        return
    data = yaml.safe_load(file.read_text(encoding="utf-8")) or {}
    keys = set(data.keys())
    if keys != {"main_domain_functional_design"}:
        errors.append(f"{file}: top-level keys must be only main_domain_functional_design, got {sorted(keys)}")
        if "input_context_ack" in keys:
            errors.append(f"{file}: input_context_ack must be inside quality_checks.context_ack")
        return
    md = data["main_domain_functional_design"] or {}
    for key in TOP_LEVEL_REQUIRED:
        if key not in md:
            errors.append(f"{file}: main_domain_functional_design missing {key}")
    validate_domain_depth(file, md, errors)
    validate_source_usage(ws, file, md, errors)
    modules = md.get("modules")
    if not isinstance(modules, list) or not modules:
        errors.append(f"{file}: modules must be a non-empty array")
        modules = []
    for idx, module in enumerate(modules, 1):
        mid = module.get("module_id", f"module[{idx}]") if isinstance(module, dict) else f"module[{idx}]"
        if not isinstance(module, dict):
            errors.append(f"{file}: {mid} is not a mapping")
            continue
        for key in MODULE_KEYS:
            if key not in module:
                errors.append(f"{file}: {mid} missing {key}")
        validate_module_positioning(file, mid, module.get("module_positioning", {}), errors)
        validate_pages(file, mid, module.get("page_design", {}), errors)
        validate_interfaces(file, mid, module.get("interface_design", {}), errors)
        validate_unsupported(file, mid, module.get("unsupported_design", []), errors)
        validate_dfx(file, mid, module.get("dfx_design", {}), errors)
        for issue in module.get("open_issues", []) or []:
            if isinstance(issue, dict):
                for key in ["issue_id", "issue", "issue_type", "impact", "affected_design_parts", "suggested_owner", "blocking", "default_strategy", "source"]:
                    if key not in issue:
                        errors.append(f"{file}: {mid} open_issues item missing {key}")
    summary = md.get("dfx_summary", {}) or {}
    for key in DFX_KEYS:
        if key not in summary:
            errors.append(f"{file}: dfx_summary missing {key}")
    validate_quality_checks(file, md.get("quality_checks", {}) or {}, errors)


def validate_domain_depth(file: Path, md: dict[str, Any], errors: list[str]) -> None:
    intent = md.get("domain_design_intent", {}) or {}
    for key in ["primary_business_object", "primary_business_object_reason", "primary_event_chain", "primary_user_roles", "primary_work_scenarios", "design_goal", "domain_boundary_summary", "source"]:
        if key not in intent:
            errors.append(f"{file}: domain_design_intent missing {key}")
    structure = md.get("domain_product_structure", {}) or {}
    for key in ["structure_strategy", "strategy_reason", "primary_workspace", "object_detail_pages", "operation_centers", "supporting_modules", "admin_configs", "embedded_capabilities", "data_views", "source"]:
        if key not in structure:
            errors.append(f"{file}: domain_product_structure missing {key}")
    journeys = md.get("domain_user_journeys")
    if not isinstance(journeys, list) or not journeys:
        errors.append(f"{file}: domain_user_journeys must be a non-empty array")
    if "industry_insight_handling" in md and not isinstance(md.get("industry_insight_handling"), list):
        errors.append(f"{file}: industry_insight_handling must be an array")
    if not isinstance(md.get("design_tradeoffs"), list):
        errors.append(f"{file}: design_tradeoffs must be an array")


def validate_module_positioning(file: Path, mid: str, positioning: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(positioning, dict):
        errors.append(f"{file}: {mid} module_positioning is not mapping")
        return
    for key in ["responsibility", "out_of_scope", "primary_actors", "primary_user_task", "product_treatment", "treatment_reason", "entry_point", "state_change", "source_functions", "source_events", "source_rules", "source_contexts", "source_aggregates"]:
        if key not in positioning:
            errors.append(f"{file}: {mid} module_positioning missing {key}")


def validate_quality_checks(file: Path, qc: dict[str, Any], errors: list[str]) -> None:
    ack = qc.get("context_ack")
    if not isinstance(ack, dict):
        errors.append(f"{file}: quality_checks.context_ack is required")
    else:
        for key in ["domain_id", "context_pack_used", "requirement_context_used", "industry_context_used", "domain_architecture_context_used", "no_forbidden_context_used"]:
            if key not in ack:
                errors.append(f"{file}: quality_checks.context_ack missing {key}")
    depth = qc.get("design_depth_check", {}) or {}
    for key in ["domain_design_intent_completed", "product_structure_completed", "user_journey_completed", "module_relationship_completed", "module_nine_parts_completed", "design_tradeoffs_completed", "industry_insight_handled"]:
        if depth.get(key) is not True:
            errors.append(f"{file}: quality_checks.design_depth_check.{key} must be true")
    source = qc.get("source_check", {}) or {}
    if source.get("all_formal_design_items_have_source") is not True:
        errors.append(f"{file}: quality_checks.source_check.all_formal_design_items_have_source must be true")
    shallow = qc.get("shallow_design_check", {}) or {}
    if shallow.get("passed") is not True:
        errors.append(f"{file}: quality_checks.shallow_design_check.passed must be true")


def validate_pages(file: Path, mid: str, page_design: dict[str, Any], errors: list[str]) -> None:
    pages = page_design.get("pages", []) if isinstance(page_design, dict) else []
    if not isinstance(pages, list) or not pages:
        errors.append(f"{file}: {mid} page_design.pages must not be empty")
        return
    for page in pages:
        if not isinstance(page, dict):
            errors.append(f"{file}: {mid} page item is not mapping")
            continue
        for key in ["page_purpose", "entry_condition", "style_summary", "first_screen_information", "data_sections", "interactions", "embedded_capabilities", "permissions", "source"]:
            if key not in page:
                errors.append(f"{file}: {mid} page {page.get('page_name', '<unnamed>')} missing {key}")


def validate_interfaces(file: Path, mid: str, interface_design: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(interface_design, dict):
        errors.append(f"{file}: {mid} interface_design is not mapping")
        return
    provided = interface_design.get("provided_interfaces", [])
    consumed = interface_design.get("consumed_external_interfaces", [])
    published = interface_design.get("published_events", [])
    consumed_events = interface_design.get("consumed_events", [])
    no_reason = interface_design.get("no_interface_reason")
    if not (provided or consumed or published or consumed_events or no_reason):
        errors.append(f"{file}: {mid} must provide interface/event design or no_interface_reason")


def validate_unsupported(file: Path, mid: str, items: Any, errors: list[str]) -> None:
    if not isinstance(items, list):
        errors.append(f"{file}: {mid} unsupported_design must be array")
        return
    for item in items:
        if not isinstance(item, dict):
            errors.append(f"{file}: {mid} unsupported_design item is not mapping")
            continue
        for key in UNSUPPORTED_KEYS:
            if key not in item:
                errors.append(f"{file}: {mid} unsupported_design item missing {key}")


def validate_dfx(file: Path, mid: str, dfx: dict[str, Any], errors: list[str]) -> None:
    if not isinstance(dfx, dict):
        errors.append(f"{file}: {mid} dfx_design is not mapping")
        return
    for key in DFX_KEYS:
        if key not in dfx:
            errors.append(f"{file}: {mid} dfx_design missing {key}")


def validate_source_usage(ws: Path, file: Path, md: dict[str, Any], errors: list[str]) -> None:
    registry = load_context_registry(ws, md)
    if not registry:
        errors.append(f"{file}: context-pack source_registry missing or empty")
        return
    for yaml_path, source_id in iter_source_refs(md):
        meta = registry.get(source_id)
        usage = usage_for_path(yaml_path)
        if not meta:
            errors.append(f"{file}: unknown source_id {source_id} at {yaml_path}")
            continue
        allowed = set(meta.get("allowed_usage") or [])
        forbidden = set(meta.get("forbidden_usage") or [])
        if usage in {"formal_design", "formal_function"}:
            if "formal_design" in forbidden or "formal_function" in forbidden:
                errors.append(f"{file}: source_id {source_id} forbidden for {usage} at {yaml_path}")
                continue
            if not ({"formal_design", "formal_function"} & allowed):
                errors.append(f"{file}: source_id {source_id} not allowed for {usage} at {yaml_path}")
                continue
            if meta.get("source_type") in {"industry_enrichment", "risk_note", "open_question"} and meta.get("status") in {"recommended_not_confirmed", "risk_note", "unresolved"}:
                errors.append(f"{file}: source_id {source_id} ({meta.get('source_type')}) cannot be used as formal design at {yaml_path}")
                continue
        elif usage not in allowed and usage in forbidden:
            errors.append(f"{file}: source_id {source_id} forbidden for {usage} at {yaml_path}")


def load_context_registry(ws: Path, md: dict[str, Any]) -> dict[str, Any]:
    ack = md.get("quality_checks", {}).get("context_ack", {}) or {}
    context_path = ack.get("context_pack_used")
    domain_id = ack.get("domain_id") or md.get("domain", {}).get("domain_id")
    candidates = []
    if isinstance(context_path, (str, Path)) and context_path:
        candidates.append(Path(context_path))
    if domain_id:
        candidates.append(Path("context-packs") / f"{domain_id}-context.yaml")
    for candidate in candidates:
        path = candidate if candidate.is_absolute() else ws / candidate
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            registry = data.get("context_pack", {}).get("source_registry", {})
            if isinstance(registry, dict):
                return registry
    return {}


def iter_source_refs(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if key in {"source", "source_ids"}:
                for source_id in normalize_source_list(item):
                    yield child_path, source_id
            else:
                yield from iter_source_refs(item, child_path)
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            yield from iter_source_refs(item, f"{path}[{idx}]")


def normalize_source_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if isinstance(item, str)]
    if isinstance(value, dict):
        return [str(item) for item in value.values() if isinstance(item, str)]
    return []


def usage_for_path(path: str) -> str:
    lowered = path.lower()
    if "dfx" in lowered:
        return "dfx"
    if "design_tradeoffs" in lowered or "tradeoff" in lowered:
        return "tradeoff"
    if "open_issues" in lowered or "open_issue" in lowered:
        return "open_issue"
    if "failure" in lowered or "unsupported" in lowered:
        return "exception_flow"
    if "function_design" in lowered or "interface_design" in lowered:
        return "formal_function"
    return "formal_design"


if __name__ == "__main__":
    raise SystemExit(main())

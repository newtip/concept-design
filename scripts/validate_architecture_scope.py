#!/usr/bin/env python3
"""Validate Agent 03 domain scopes before context-pack generation."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    args = parser.parse_args()
    ws = Path(args.workspace)

    business = load_first(ws, ["baselines/business_model.yaml", "p1/business_model.yaml", "p1/01-business-model.yaml"])
    industry = load_first(ws, ["baselines/industry_insight.yaml", "p1/industry_insight.yaml", "p1/02-industry-insight.yaml"])
    arch = load_first(ws, ["baselines/architecture_design.yaml", "p1/architecture_design.yaml", "p1/03-architecture-design.yaml"])

    errors = validate_scope(business, industry, arch)
    if errors:
        print(f"FAILED: architecture scope validation ({len(errors)} errors)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASSED: architecture scope validation")
    return 0


def validate_scope(business_doc: dict[str, Any], industry_doc: dict[str, Any], arch_doc: dict[str, Any]) -> list[str]:
    business = unwrap(business_doc, "business_model")
    industry = unwrap(industry_doc, "industry_insight")
    arch = unwrap(arch_doc, "architecture_design")
    errors: list[str] = []

    func_ids = collect_ids(business, ["source_id_index", "functions"], fallback_prefixes=("FUNC-",))
    event_ids = collect_ids(business, ["source_id_index", "events"], fallback_prefixes=("EVT-",))
    rule_ids = collect_ids(business, ["source_id_index", "business_rules"], fallback_prefixes=("RULE-", "BR-"))
    workflow_ids = collect_ids(business, ["source_id_index", "workflows"], fallback_prefixes=("WF-",))
    actor_ids = collect_ids(business, ["source_id_index", "actors"], fallback_prefixes=("ACT-", "ACTOR-"))

    pattern_ids = collect_collection_ids(industry.get("industry_patterns", []), ["pattern_id", "id"], "PAT-")
    rec_ids = collect_collection_ids(industry.get("industry_recommendations", []), ["recommendation_id", "id"], "REC-")
    risk_ids = collect_collection_ids(industry.get("risk_notes", []), ["risk_id", "id"], "RISK-")
    decision_ids = collect_collection_ids(industry.get("design_decision_backlog", []), ["decision_id", "id"], "DEC-")
    boundary_ids = collect_collection_ids(industry.get("boundary_notes", []), ["boundary_id", "id"], "BN-")

    context_ids = collect_collection_ids(arch.get("contexts", []), ["context_id", "id"], "CTX-")
    aggregate_ids = collect_collection_ids(arch.get("aggregates", []), ["aggregate_id", "id"], "AGG-")

    mapped_funcs: set[str] = set()
    produced_events: set[str] = set()
    mapped_rules: set[str] = set()
    mapped_risks: set[str] = set()

    for domain in arch.get("domains", []):
        did = domain.get("domain_id", "<missing-domain-id>")
        for key in ["requirement_scope", "industry_scope", "ddd_scope"]:
            if key not in domain or not isinstance(domain.get(key), dict):
                errors.append(f"{did}: missing {key}")
        req = domain.get("requirement_scope", {}) or {}
        ind = domain.get("industry_scope", {}) or {}
        ddd = domain.get("ddd_scope", {}) or {}

        mapped_funcs |= set(req.get("functions", []) or [])
        events = req.get("events", {}) or {}
        produced_events |= set(events.get("produced", []) or [])
        mapped_rules |= set(req.get("business_rules", []) or [])
        mapped_risks |= set(ind.get("risks", []) or [])

        check_ids(errors, did, "requirement_scope.functions", req.get("functions", []), func_ids)
        check_ids(errors, did, "requirement_scope.workflows", req.get("workflows", []), workflow_ids, allow_empty=True)
        check_ids(errors, did, "requirement_scope.actors", req.get("actors", []), actor_ids, allow_empty=True)
        check_ids(errors, did, "requirement_scope.business_rules", req.get("business_rules", []), rule_ids, allow_empty=True)
        for event_group in ["produced", "consumed", "related"]:
            check_ids(errors, did, f"requirement_scope.events.{event_group}", events.get(event_group, []), event_ids, allow_empty=True)

        check_ids(errors, did, "industry_scope.patterns", ind.get("patterns", []), pattern_ids, allow_empty=True)
        check_ids(errors, did, "industry_scope.boundary_notes", ind.get("boundary_notes", []), boundary_ids, allow_empty=True)
        check_ids(errors, did, "industry_scope.risks", ind.get("risks", []), risk_ids, allow_empty=True)
        check_ids(errors, did, "industry_scope.decision_backlog", ind.get("decision_backlog", []), decision_ids, allow_empty=True)
        recommendations = ind.get("recommendations", {}) or {}
        for status in ["confirmed_by_requirement", "recommended_not_confirmed", "assumption_for_review", "question_only"]:
            check_ids(errors, did, f"industry_scope.recommendations.{status}", recommendations.get(status, []), rec_ids, allow_empty=True)

        check_ids(errors, did, "ddd_scope.contexts", ddd.get("contexts", []), context_ids, allow_empty=True)
        check_ids(errors, did, "ddd_scope.aggregates", ddd.get("aggregates", []), aggregate_ids, allow_empty=True)
        if not req.get("functions") and domain.get("domain_type") != "generic":
            errors.append(f"{did}: non-generic domain has no requirement_scope.functions")

    if func_ids:
        missing = sorted(func_ids - mapped_funcs)
        if missing:
            errors.append(f"confirmed functions not mapped to any domain: {missing}")
    if event_ids:
        missing = sorted(event_ids - produced_events)
        if missing:
            errors.append(f"events without producer domain: {missing}")
    if rule_ids:
        missing = sorted(rule_ids - mapped_rules)
        if missing:
            errors.append(f"business rules not mapped to any domain: {missing}")
    if risk_ids:
        missing = sorted(risk_ids - mapped_risks)
        if missing:
            errors.append(f"industry risks not mapped to any domain: {missing}")

    coverage = arch.get("coverage_validation", {}) or {}
    if coverage and any(coverage.get(key) is False for key in [
        "all_confirmed_functions_mapped",
        "all_events_have_producer_domain",
        "all_rules_mapped",
        "industry_risks_mapped",
    ]):
        errors.append("coverage_validation contains false result; inspect unmapped lists")
    return errors


def check_ids(errors: list[str], domain_id: str, path: str, values: Any, allowed: set[str], allow_empty: bool = False) -> None:
    values = values or []
    if not values and not allow_empty:
        errors.append(f"{domain_id}: {path} is empty")
        return
    for value in values:
        if str(value) not in allowed:
            errors.append(f"{domain_id}: {path} references unknown id {value}")


def collect_ids(root: dict[str, Any], path: list[str], fallback_prefixes: tuple[str, ...]) -> set[str]:
    current: Any = root
    for key in path:
        current = current.get(key, {}) if isinstance(current, dict) else {}
    values = set(str(v) for v in current) if isinstance(current, list) else set()
    return values or collect_deep_prefixed(root, fallback_prefixes)


def collect_deep_prefixed(value: Any, prefixes: tuple[str, ...]) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"id", "source_id", "function_id", "event_id", "rule_id", "workflow_id", "actor_id"}:
                text = str(item)
                if text.startswith(prefixes):
                    result.add(text)
            result |= collect_deep_prefixed(item, prefixes)
    elif isinstance(value, list):
        for item in value:
            result |= collect_deep_prefixed(item, prefixes)
    elif isinstance(value, str) and value.startswith(prefixes):
        result.add(value)
    return result


def collect_collection_ids(items: Any, keys: list[str], fallback_prefix: str) -> set[str]:
    result: set[str] = set()
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict):
                for key in keys:
                    if item.get(key):
                        result.add(str(item[key]))
                        break
            elif isinstance(item, str) and item.startswith(fallback_prefix):
                result.add(item)
    return result


def unwrap(doc: dict[str, Any], key: str) -> dict[str, Any]:
    return doc.get(key, doc) if isinstance(doc, dict) else {}


def load_first(ws: Path, rels: list[str]) -> dict[str, Any]:
    for rel in rels:
        path = ws / rel
        if path.exists():
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raise SystemExit(f"Missing any of: {', '.join(rels)}")


if __name__ == "__main__":
    raise SystemExit(main())

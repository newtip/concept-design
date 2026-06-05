#!/usr/bin/env python3
"""Build baselines/source-registry.yaml as a metadata map from frozen P1 baselines."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

PREFIX_META = {
    "REQ-": ("requirement", "requirement_fact", "confirmed", ["formal_design", "formal_function", "workflow"], []),
    "IND-": ("recommendation", "industry_enrichment", "recommended_not_confirmed", ["edge_case", "exception_flow"], ["formal_design", "formal_function"]),
    "BOUND-": ("boundary", "boundary_note", "confirmed", ["boundary", "scope_constraint"], ["formal_function"]),
    "EXC-": ("exception", "exception_note", "confirmed", ["exception_flow", "workflow"], ["formal_function"]),
    "GOAL-": ("requirement", "requirement_fact", "confirmed", ["formal_design", "workflow"], []),
    "FUNC-": ("requirement", "requirement_fact", "confirmed", ["formal_design", "formal_function", "workflow"], []),
    "WF-": ("workflow", "requirement_fact", "confirmed", ["formal_design", "workflow"], []),
    "EVT-": ("event", "requirement_fact", "confirmed", ["formal_design", "workflow", "event"], []),
    "CMD-": ("command", "requirement_fact", "confirmed", ["formal_design", "formal_function"], []),
    "POL-": ("policy", "requirement_fact", "confirmed", ["formal_design"], []),
    "RULE-": ("rule", "requirement_fact", "confirmed", ["formal_design"], []),
    "BR-": ("rule", "requirement_fact", "confirmed", ["formal_design"], []),
    "ACTOR-": ("actor", "requirement_fact", "confirmed", ["formal_design", "workflow"], []),
    "ACT-": ("actor", "requirement_fact", "confirmed", ["formal_design", "workflow"], []),
    "PERM-": ("permission", "requirement_fact", "confirmed", ["formal_design", "formal_function"], []),
    "INT-": ("integration", "requirement_fact", "confirmed", ["formal_design", "interface"], []),
    "FLD-": ("field", "requirement_fact", "confirmed", ["formal_design", "data_model"], []),
    "IMG-": ("image", "image_requirement_extract", "needs_agent_extraction", ["reference", "open_issue"], ["formal_design", "formal_function"]),
    "CTX-": ("architecture", "requirement_fact", "confirmed", ["formal_design"], []),
    "AGG-": ("architecture", "requirement_fact", "confirmed", ["formal_design"], []),
    "REC-": ("recommendation", "industry_enrichment", "recommended_not_confirmed", ["edge_case", "exception_flow"], ["formal_design", "formal_function"]),
    "PAT-": ("pattern", "industry_enrichment", "recommended_not_confirmed", ["boundary", "edge_case", "exception_flow"], ["formal_function"]),
    "BN-": ("boundary", "industry_enrichment", "recommended_not_confirmed", ["boundary", "edge_case"], ["formal_function"]),
    "DEC-": ("decision", "industry_enrichment", "recommended_not_confirmed", ["boundary", "tradeoff"], ["formal_function"]),
    "RISK-": ("risk", "risk_note", "risk_note", ["dfx", "exception_flow"], ["formal_function", "confirmed_requirement"]),
    "Q-": ("question", "open_question", "unresolved", ["open_issue"], ["formal_design", "formal_function"]),
}

ID_KEYS = {
    "id",
    "source_id",
    "goal_id",
    "function_id",
    "workflow_id",
    "event_id",
    "command_id",
    "policy_id",
    "rule_id",
    "actor_id",
    "permission_id",
    "integration_id",
    "context_id",
    "aggregate_id",
    "recommendation_id",
    "pattern_id",
    "boundary_id",
    "decision_id",
    "risk_id",
    "question_id",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    args = parser.parse_args()
    ws = Path(args.workspace)
    docs = []
    for rel in ["baselines/business_model.yaml", "baselines/industry_insight.yaml", "baselines/architecture_design.yaml"]:
        path = ws / rel
        if path.exists():
            docs.append(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    registry = build_registry(docs)
    out = ws / "baselines" / "source-registry.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump({"source_registry": registry}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(out)
    return 0


def build_registry(docs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for doc in docs:
        collect_sources(doc, found)
    return dict(sorted(found.items()))


def collect_sources(value: Any, found: dict[str, dict[str, Any]]) -> None:
    if isinstance(value, dict):
        for source_id in source_ids_of(value):
            found[source_id] = make_meta(source_id, value)
        for item in value.values():
            collect_sources(item, found)
    elif isinstance(value, list):
        for item in value:
            collect_sources(item, found)
    elif isinstance(value, str) and meta_for(value):
        found.setdefault(value, make_meta(value, {}))


def source_ids_of(item: dict[str, Any]) -> list[str]:
    result = []
    for key in ID_KEYS:
        value = item.get(key)
        if isinstance(value, str) and meta_for(value):
            result.append(value)
    return result


def make_meta(source_id: str, item: dict[str, Any]) -> dict[str, Any]:
    category, source_type, default_status, allowed_usage, forbidden_usage = meta_for(source_id) or (
        "unknown",
        "requirement_fact",
        "confirmed",
        ["formal_design"],
        [],
    )
    status = item.get("status") or default_status
    if source_type == "industry_enrichment" and status == "confirmed_by_requirement":
        allowed_usage = ["formal_design", "edge_case", "exception_flow"]
        forbidden_usage = []
        status = "confirmed"
    return {
        "source_id": source_id,
        "category": category,
        "source_type": source_type,
        "title": title_of(item, source_id),
        "status": status,
        "allowed_usage": list(allowed_usage),
        "forbidden_usage": list(forbidden_usage),
    }


def meta_for(source_id: str):
    source_id = strip_variant_suffix(source_id)
    for prefix, meta in PREFIX_META.items():
        if source_id.startswith(prefix):
            return meta
    return None


def strip_variant_suffix(source_id: str) -> str:
    if source_id.endswith(("-N", "-M")):
        return source_id[:-2]
    return source_id


def title_of(item: dict[str, Any], fallback: str) -> str:
    for key in ["title", "name", "description", "recommendation", "risk", "note", "decision", "question"]:
        if item.get(key):
            return str(item[key])
    return fallback


if __name__ == "__main__":
    raise SystemExit(main())

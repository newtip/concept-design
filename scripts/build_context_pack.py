#!/usr/bin/env python3
"""Build one P2 Context Pack per domain from Agent 03 domain scopes."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from build_source_registry import build_registry


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--domain-id", default="")
    args = parser.parse_args()
    ws = Path(args.workspace)
    business = unwrap(load_first(ws, ["baselines/business_model.yaml", "p1/business_model.yaml", "p1/01-business-model.yaml"]), "business_model")
    industry = unwrap(load_first(ws, ["baselines/industry_insight.yaml", "p1/industry_insight.yaml", "p1/02-industry-insight.yaml"]), "industry_insight")
    arch = unwrap(load_first(ws, ["baselines/architecture_design.yaml", "p1/architecture_design.yaml", "p1/03-architecture-design.yaml"]), "architecture_design")
    registry = load_source_registry(ws, business, industry, arch)
    index = load_index(ws)
    outputs: list[Path] = []

    for domain in arch.get("domains", []):
        if args.domain_id and domain.get("domain_id") != args.domain_id:
            continue
        indexed = find_index_domain(index, domain.get("domain_id"))
        pack = build_pack(ws, business, industry, arch, domain, indexed, registry)
        out = ws / indexed.get("context_pack_file", f"context-packs/{domain['domain_id']}-context.yaml")
        out.parent.mkdir(parents=True, exist_ok=True)
        write_yaml(out, pack)
        alias = ws / "context-packs" / f"{indexed.get('domain_prefix')}_context.yaml"
        if alias != out:
            write_yaml(alias, pack)
        outputs.append(out)
    for output in outputs:
        print(output)
    return 0


def build_pack(ws: Path, business: dict[str, Any], industry: dict[str, Any], arch: dict[str, Any], domain: dict[str, Any], indexed: dict[str, Any], registry: dict[str, Any]) -> dict[str, Any]:
    req_scope = domain.get("requirement_scope", {}) or {}
    ind_scope = domain.get("industry_scope", {}) or {}
    ddd_scope = domain.get("ddd_scope", {}) or {}
    req_events = req_scope.get("events", {}) or {}
    rec_scope = ind_scope.get("recommendations", {}) or {}
    missing: list[dict[str, str]] = []
    def pick(root: Any, ids: Any, section: str) -> list[Any]:
        return pick_by_ids(root, ids, section, missing)

    return {
        "context_pack": {
            "meta": {
                "context_pack_id": f"CP-{domain.get('domain_id')}",
                "domain_id": domain.get("domain_id"),
                "domain_name": domain.get("domain_name"),
                "run_id": load_run_id(ws),
                "generated_at": datetime.now().isoformat(),
                "status": "frozen",
                "source": "architecture_design.domains[].requirement_scope + industry_scope + ddd_scope",
            },
            "current_domain": {
                "domain_id": domain.get("domain_id"),
                "domain_name": domain.get("domain_name"),
                "domain_prefix": indexed.get("domain_prefix"),
                "domain_type": domain.get("domain_type"),
                "responsibility": domain.get("responsibility", domain.get("boundary_reasoning", {}).get("why_this_domain_exists", "")),
                "out_of_scope": domain.get("out_of_scope", []),
                "sub_domains": indexed.get("sub_domains", []),
                "boundary_reasoning": domain.get("boundary_reasoning", {}),
            },
            "requirement_context": {
                "business_goals": pick(business, req_scope.get("business_goals", []), "requirement_context.business_goals"),
                "actors": pick(business, req_scope.get("actors", []), "requirement_context.actors"),
                "functions": pick(business, req_scope.get("functions", []), "requirement_context.functions"),
                "workflows": pick(business, req_scope.get("workflows", []), "requirement_context.workflows"),
                "commands": pick(business, req_scope.get("commands", []), "requirement_context.commands"),
                "policies": pick(business, req_scope.get("policies", []), "requirement_context.policies"),
                "events": {
                    "produced": pick(business, req_events.get("produced", []), "requirement_context.events.produced"),
                    "consumed": pick(business, req_events.get("consumed", []), "requirement_context.events.consumed"),
                    "related": pick(business, req_events.get("related", []), "requirement_context.events.related"),
                },
                "business_rules": pick(business, req_scope.get("business_rules", []), "requirement_context.business_rules"),
                "permissions": pick(business, req_scope.get("permissions", []), "requirement_context.permissions"),
                "integrations": pick(business, req_scope.get("integrations", []), "requirement_context.integrations"),
                "open_questions": pick(business, req_scope.get("open_questions", []), "requirement_context.open_questions"),
            },
            "industry_context": {
                "project_archetype": industry.get("project_archetype", {}),
                "requirement_maturity": industry.get("requirement_maturity", {}),
                "industry_patterns": pick(industry, ind_scope.get("patterns", []), "industry_context.industry_patterns"),
                "boundary_notes": pick(industry, ind_scope.get("boundary_notes", []), "industry_context.boundary_notes"),
                "industry_recommendations": {
                    "confirmed_by_requirement": pick(industry, rec_scope.get("confirmed_by_requirement", []), "industry_context.recommendations.confirmed_by_requirement"),
                    "recommended_not_confirmed": pick(industry, rec_scope.get("recommended_not_confirmed", []), "industry_context.recommendations.recommended_not_confirmed"),
                    "assumption_for_review": pick(industry, rec_scope.get("assumption_for_review", []), "industry_context.recommendations.assumption_for_review"),
                    "question_only": pick(industry, rec_scope.get("question_only", []), "industry_context.recommendations.question_only"),
                },
                "risk_notes": pick(industry, ind_scope.get("risks", []), "industry_context.risk_notes"),
                "design_decision_backlog": pick(industry, ind_scope.get("decision_backlog", []), "industry_context.design_decision_backlog"),
                "routing_summary": industry.get("routing_summary", {}),
            },
            "domain_architecture_context": {
                "contexts": pick(arch, ddd_scope.get("contexts", []), "domain_architecture_context.contexts"),
                "aggregates": pick(arch, ddd_scope.get("aggregates", []), "domain_architecture_context.aggregates"),
                "owned_objects": ddd_scope.get("owned_objects", []),
                "referenced_objects": ddd_scope.get("referenced_objects", []),
                "domain_events": pick_domain_events(arch, business, list(req_events.get("produced", []) or []) + list(req_events.get("related", []) or []), missing),
                "context_relationships": related_relationships(arch, domain),
                "shared_object_ownership": related_shared_objects(arch, domain),
            },
            "related_domain_summaries": related_domain_summaries(arch, domain),
            "negative_context": {
                "out_of_scope": domain.get("out_of_scope", []),
                "forbidden_inference": [
                    "不得新增 source_registry 中不存在的 FUNC / EVT / RULE / REC / RISK / DEC / CTX / AGG",
                    "不得把 recommended_not_confirmed 或 question_only 写成正式功能",
                    "不得读取原始 Word 或其他领域完整设计文件",
                ],
                "unavailable_information": pick(business, req_scope.get("open_questions", []), "negative_context.unavailable_information"),
            },
            "decision_boundary": {
                "can_decide": ["模块内页面组织", "接口形状", "模块局部DFX", "非阻塞open_issue表述"],
                "cannot_decide": ["新增主领域", "修改需求基线", "修改领域边界", "改变共享对象Owner", "确认未确认行业建议"],
            },
            "p1_full_context": {
                "business_model": business,
                "industry_insight": industry,
                "architecture_design": arch,
            },
            "source_registry": registry,
            "source_resolution": {"missing_ids": missing},
        }
    }


def load_source_registry(ws: Path, business: dict[str, Any], industry: dict[str, Any], arch: dict[str, Any]) -> dict[str, Any]:
    path = ws / "baselines" / "source-registry.yaml"
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        registry = data.get("source_registry", data)
        if isinstance(registry, dict) and all(isinstance(v, dict) for v in registry.values()):
            return registry
    return build_registry([{"business_model": business}, {"industry_insight": industry}, {"architecture_design": arch}])


def pick_by_ids(root: Any, ids: Any, section: str, missing: list[dict[str, str]]) -> list[Any]:
    wanted = set(str(x) for x in (ids or []))
    if not wanted:
        return []
    found: list[Any] = []
    walk_collect(root, wanted, found)
    found_ids = set()
    for item in found:
        collect_item_ids(item, found_ids)
    for item_id in sorted(wanted - found_ids):
        missing.append({"id": item_id, "section": section})
    return found


def pick_domain_events(arch: dict[str, Any], business: dict[str, Any], ids: list[str], missing: list[dict[str, str]]) -> list[Any]:
    before = len(missing)
    found = pick_by_ids(arch, ids, "domain_architecture_context.domain_events", missing)
    if found:
        return found
    del missing[before:]
    return pick_by_ids(business, ids, "domain_architecture_context.domain_events", missing)


def walk_collect(value: Any, wanted: set[str], found: list[Any]) -> None:
    if isinstance(value, dict):
        ids = {str(v) for k, v in value.items() if k.endswith("_id") or k in {"id", "source_id"}}
        if ids & wanted:
            found.append(value)
            return
        for item in value.values():
            walk_collect(item, wanted, found)
    elif isinstance(value, list):
        for item in value:
            walk_collect(item, wanted, found)


def collect_item_ids(value: Any, result: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("_id") or key in {"id", "source_id"}:
                result.add(str(item))
            collect_item_ids(item, result)
    elif isinstance(value, list):
        for item in value:
            collect_item_ids(item, result)


def related_relationships(arch: dict[str, Any], domain: dict[str, Any]) -> list[Any]:
    name = domain.get("domain_name", "")
    did = domain.get("domain_id", "")
    return [item for item in arch.get("context_relationships", []) if name in str(item) or did in str(item)]


def related_shared_objects(arch: dict[str, Any], domain: dict[str, Any]) -> list[Any]:
    name = domain.get("domain_name", "")
    did = domain.get("domain_id", "")
    return [item for item in arch.get("shared_object_ownership", []) if name in str(item) or did in str(item)]


def related_domain_summaries(arch: dict[str, Any], current: dict[str, Any]) -> list[dict[str, Any]]:
    result = []
    for domain in arch.get("domains", []):
        if domain.get("domain_id") == current.get("domain_id"):
            continue
        ddd = domain.get("ddd_scope", {}) or {}
        result.append(
            {
                "domain_id": domain.get("domain_id"),
                "domain_name": domain.get("domain_name"),
                "domain_type": domain.get("domain_type"),
                "owned_objects": ddd.get("owned_objects", []),
                "allowed_usage": ["id_reference", "snapshot", "projection", "event", "acl"],
                "forbidden_usage": ["own_lifecycle", "direct_mutation"],
            }
        )
    return result


def find_index_domain(index: dict[str, Any], domain_id: str) -> dict[str, Any]:
    domains = index.get("main_domains") or index.get("domain_design_index", {}).get("domains", [])
    for domain in domains:
        if domain.get("domain_id") == domain_id:
            return domain
    raise SystemExit(f"domain {domain_id} not found in domain-design-index.yaml")


def load_index(ws: Path) -> dict[str, Any]:
    path = ws / "domain-design-index.yaml"
    if not path.exists():
        raise SystemExit("domain-design-index.yaml missing; run build_domain_design_index.py first")
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def load_run_id(ws: Path) -> str:
    path = ws / "domain-design-index.yaml"
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data.get("run_id") or data.get("domain_design_index", {}).get("run_id", "")
    return ""


def unwrap(doc: dict[str, Any], key: str) -> dict[str, Any]:
    return doc.get(key, doc) if isinstance(doc, dict) else {}


def load_first(ws: Path, rels: list[str]) -> dict[str, Any]:
    for rel in rels:
        path = ws / rel
        if path.exists():
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raise SystemExit(f"Missing any of: {', '.join(rels)}")


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

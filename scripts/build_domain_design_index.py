#!/usr/bin/env python3
"""Build domain-design-index.yaml from architecture_design.domains."""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concept_design.index_store import atomic_write_yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--mode", default="mode_a_sequential", choices=["sequential", "parallel", "anchor", "mode_a_sequential", "mode_b_parallel", "mode_c_anchor"])
    args = parser.parse_args()
    ws = Path(args.workspace)
    arch_doc = load_first(ws, ["baselines/architecture_design.yaml", "p1/architecture_design.yaml", "p1/03-architecture-design.yaml"])
    arch = arch_doc.get("architecture_design", arch_doc)
    run_id = load_run_id(ws)
    mode = normalize_mode(args.mode)
    source_domains = arch.get("domains", [])
    execution_dependencies = p2_execution_dependencies(arch)
    anchor_id = first_core_domain_id(source_domains)
    domains = []
    for sequence, domain in enumerate(source_domains, 1):
        did = domain["domain_id"]
        prefix = domain.get("domain_prefix") or prefix_from_name(domain.get("domain_name", did))
        modules = domain.get("sub_domains") or domain.get("subdomains") or []
        domains.append(
            {
                "domain_id": did,
                "domain_name": domain.get("domain_name", ""),
                "domain_type": domain.get("domain_type", ""),
                "domain_prefix": prefix,
                "p2_required": True,
                "required_for_p3": domain.get("domain_type") == "core",
                "sequence": int(domain.get("sequence") or sequence),
                "is_anchor": bool(domain.get("is_anchor", did == anchor_id)),
                "depends_on": execution_dependencies.get(did, list(domain.get("depends_on", []) or [])),
                "reference_depends_on": list(domain.get("depends_on", []) or []),
                "design_level": "full",
                "p2_focus": p2_focus(domain.get("domain_type", "")),
                "source_functions": list(scope(domain, "requirement_scope").get("functions", [])),
                "source_events": list((scope(domain, "requirement_scope").get("events", {}) or {}).get("produced", []) + (scope(domain, "requirement_scope").get("events", {}) or {}).get("related", [])),
                "source_contexts": list(scope(domain, "ddd_scope").get("contexts", [])),
                "context_pack_file": f"context-packs/{did}-context.yaml",
                "output_file": f"domains/{did}/{prefix}-main-domain-functional-design.yaml",
                "design_file": f"domains/{did}/{prefix}-main-domain-functional-design.yaml",
                "review_file": f"domains/{did}/{prefix}-review-checklist.md",
                "review_result_file": f"domains/{did}/review-result.yaml",
                "review_report_file": f"domains/{did}/review-report.md",
                "confirmed_design_scope_file": f"domains/{did}/confirmed_design_scope.yaml",
                "repair_file": f"domains/{did}/{prefix}-repair-log.md",
                "sub_domains": normalize_modules(modules, prefix),
                "status": "pending",
                "stage": "pending",
                "last_transition_at": "",
                "last_transition_reason": "",
                "review_round": 0,
                "repair_round": 0,
                "review_status": "missing",
                "repair_status": "not_required",
                "blocked_reason": "",
                "deferred_reason": "",
                "blocking_issues": [],
            }
        )
    index = {
        "domain_design_index": {
            "project_name": arch.get("project_name", ""),
            "run_id": run_id,
                "design_mode": {"mode": args.mode, "locked": True},
                "p2_execution_mode": mode,
            "truth_sources": {
                "business_model": "baselines/business_model.yaml",
                "industry_insight": "baselines/industry_insight.yaml",
                "architecture_design": "baselines/architecture_design.yaml",
            },
            "domains": domains,
        },
        "project_name": arch.get("project_name", ""),
        "run_id": run_id,
        "p2_execution_mode": mode,
        "main_domains": domains,
    }
    write_yaml(ws / "domain-design-index.yaml", index)
    print(ws / "domain-design-index.yaml")
    return 0


def scope(domain: dict[str, Any], key: str) -> dict[str, Any]:
    return domain.get(key, {}) or {}


def p2_execution_dependencies(arch: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for item in arch.get("p2_index_seed", {}).get("main_domains", []) or []:
        did = item.get("domain_id")
        if not did:
            continue
        execution = item.get("p2_execution", {}) or {}
        result[did] = list(execution.get("depends_on_core_domains", []) or [])
    return result


def normalize_modules(modules: Any, prefix: str) -> list[dict[str, str]]:
    result = []
    for idx, item in enumerate(modules or [], 1):
        if isinstance(item, dict):
            name = item.get("name") or item.get("module_name") or item.get("sub_domain_name") or f"模块{idx}"
        else:
            name = str(item)
        result.append({"module_id": f"MOD-{prefix}-{idx:02d}", "module_name": name})
    return result


def p2_focus(domain_type: str) -> str:
    if domain_type == "core":
        return "完整业务流程、页面、接口、状态流转、数据模型和DFX设计"
    if domain_type == "supporting":
        return "支撑能力、被核心域调用方式、接口、事件、配置、日志审计和数据模型"
    return "通用能力、嵌入式页面/配置入口、接口契约、权限、审计和数据模型"


def prefix_from_name(name: str) -> str:
    ascii_chars = "".join(ch.lower() for ch in name if ch.isascii() and ch.isalnum())
    return (ascii_chars[:3] or "dm").ljust(2, "x")


def normalize_mode(value: str) -> str:
    return {
        "sequential": "mode_a_sequential",
        "parallel": "mode_b_parallel",
        "anchor": "mode_c_anchor",
    }.get(value, value)


def first_core_domain_id(domains: list[dict[str, Any]]) -> str | None:
    for domain in domains:
        if domain.get("domain_type") == "core":
            return domain.get("domain_id")
    return domains[0].get("domain_id") if domains else None


def load_run_id(ws: Path) -> str:
    state = ws / "project-state.yaml"
    if state.exists():
        data = yaml.safe_load(state.read_text(encoding="utf-8")) or {}
        return data.get("project_state", {}).get("run_id") or data.get("run_id") or new_run_id()
    return new_run_id()


def new_run_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8]


def load_first(ws: Path, rels: list[str]) -> dict[str, Any]:
    for rel in rels:
        path = ws / rel
        if path.exists():
            return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raise SystemExit(f"Missing any of: {', '.join(rels)}")


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    atomic_write_yaml(path, data)


if __name__ == "__main__":
    raise SystemExit(main())

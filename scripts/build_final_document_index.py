#!/usr/bin/env python3
"""Build final-document-index.yaml from passed domains only."""
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
    index = yaml.safe_load((ws / "domain-design-index.yaml").read_text(encoding="utf-8")) or {}
    domains = domains_of(index)
    passed = [d for d in domains if d.get("stage") == "passed" and review_passed(ws, d)]
    pending = [d for d in domains if d not in passed]
    failed_reasons = []
    for d in passed:
        for key in ["output_file", "review_file"]:
            if not resolve(ws, d.get(key)).exists():
                failed_reasons.append(f"{d.get('domain_id')}: {key} missing")
        workspaces = d.get("p3_workspaces") or []
        domain_workspaces = [item for item in workspaces if "-SD" not in str(item.get("workspace_id", ""))]
        subdomain_workspaces = [str(item.get("workspace_id")) for item in workspaces if "-SD" in str(item.get("workspace_id", ""))]
        if subdomain_workspaces:
            failed_reasons.append(f"{d.get('domain_id')}: deprecated subdomain P3 workspaces present: {', '.join(subdomain_workspaces)}")
        if len(domain_workspaces) != 1:
            failed_reasons.append(f"{d.get('domain_id')}: expected exactly one domain-level P3 workspace, found {len(domain_workspaces)}")
    pre_status = "passed" if not failed_reasons else "failed"
    final = {
        "final_document_index": {
            "pre_write_check": {"status": pre_status, "failed_reasons": failed_reasons},
            "statistics": {
                "domain_count": len(domains),
                "passed_domain_count": len(passed),
                "core_domain_count": count_type(domains, "core"),
                "supporting_domain_count": count_type(domains, "supporting"),
                "generic_domain_count": count_type(domains, "generic"),
                "p3_workspace_count": sum(len(d.get("p3_workspaces") or []) for d in passed),
                "domain_level_p3_workspace_count": sum(
                    1
                    for d in passed
                    for item in d.get("p3_workspaces") or []
                    if "-SD" not in str(item.get("workspace_id", ""))
                ),
            },
            "passed_domains": [
                {
                    "domain_id": d.get("domain_id"),
                    "domain_name": d.get("domain_name"),
                    "domain_type": d.get("domain_type"),
                    "stage": d.get("stage"),
                    "status": d.get("status"),
                    "review_status": review_status(ws, d),
                    "required_for_p3": d.get("required_for_p3", d.get("p2_required", True)),
                    "p3_workspaces": d.get("p3_workspaces", []),
                    "confirmed_scope_package_file": d.get("confirmed_scope_package_file"),
                    "confirmed_design_scope_file": d.get("confirmed_design_scope_file"),
                    "output_file": d.get("output_file"),
                    "review_file": d.get("review_file"),
                }
                for d in passed
            ],
            "pending_or_failed_domains": [
                {
                    "domain_id": d.get("domain_id"),
                    "domain_name": d.get("domain_name"),
                    "status": d.get("status"),
                    "stage": d.get("stage"),
                    "review_status": d.get("review_status"),
                    "required_for_p3": d.get("required_for_p3", d.get("p2_required", True)),
                    "p3_workspaces": d.get("p3_workspaces", []),
                    "confirmed_scope_package_file": d.get("confirmed_scope_package_file"),
                    "confirmed_design_scope_file": d.get("confirmed_design_scope_file"),
                }
                for d in pending
            ],
        }
    }
    out = ws / "final" / "final-document-index.yaml"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(final, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (ws / "final-document-index.yaml").write_text(yaml.safe_dump(final, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(out)
    return 0 if pre_status == "passed" else 1


def domains_of(index: dict[str, Any]) -> list[dict[str, Any]]:
    return index.get("domain_design_index", {}).get("domains") or index.get("main_domains", [])


def count_type(domains: list[dict[str, Any]], domain_type: str) -> int:
    return sum(1 for d in domains if d.get("domain_type") == domain_type)


def resolve(ws: Path, value: str | None) -> Path:
    if not value:
        return ws / "<missing>"
    path = Path(value)
    return path if path.is_absolute() else ws / path


def review_status(ws: Path, domain: dict[str, Any]) -> str:
    if domain.get("review_status"):
        return str(domain.get("review_status"))
    result_path = resolve(ws, domain.get("review_result_file"))
    if result_path.exists():
        data = yaml.safe_load(result_path.read_text(encoding="utf-8")) or {}
        return str((data.get("review_result") or {}).get("status") or "missing")
    return "missing"


def review_passed(ws: Path, domain: dict[str, Any]) -> bool:
    if domain.get("review_status") == "passed":
        return True
    result_path = resolve(ws, domain.get("review_result_file"))
    if not result_path.exists():
        return False
    data = yaml.safe_load(result_path.read_text(encoding="utf-8")) or {}
    return (data.get("review_result") or {}).get("status") == "passed"


if __name__ == "__main__":
    raise SystemExit(main())

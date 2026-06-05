#!/usr/bin/env python3
"""Validate final-document-index consistency with domain-design-index."""
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
    ddi = yaml.safe_load((ws / "domain-design-index.yaml").read_text(encoding="utf-8")) or {}
    fdi_path = ws / "final" / "final-document-index.yaml"
    if not fdi_path.exists():
        fdi_path = ws / "final-document-index.yaml"
    fdi = yaml.safe_load(fdi_path.read_text(encoding="utf-8")) or {}
    domains = domains_of(ddi)
    ddi_passed = sorted(d["domain_id"] for d in domains if d.get("stage") == "passed" and review_passed(ws, d))
    root = fdi.get("final_document_index", fdi)
    fdi_passed = sorted(d["domain_id"] for d in root.get("passed_domains", []))
    errors = []
    if ddi_passed != fdi_passed:
        errors.append(f"passed_domains mismatch: DDI={ddi_passed} FDI={fdi_passed}")
    if root.get("pre_write_check", {}).get("status") != "passed":
        errors.append("pre_write_check.status must be passed")
    stats = root.get("statistics", {})
    if stats.get("passed_domain_count") != len(ddi_passed):
        errors.append("statistics.passed_domain_count does not match domain-design-index")
    for item in root.get("passed_domains", []):
        for field in ["stage", "review_status", "required_for_p3", "p3_workspaces", "confirmed_scope_package_file", "confirmed_design_scope_file"]:
            if field not in item:
                errors.append(f"passed domain {item.get('domain_id')} missing {field}")
        workspaces = item.get("p3_workspaces") or []
        domain_workspaces = [entry for entry in workspaces if "-SD" not in str(entry.get("workspace_id", ""))]
        subdomain_workspaces = [str(entry.get("workspace_id")) for entry in workspaces if "-SD" in str(entry.get("workspace_id", ""))]
        if subdomain_workspaces:
            errors.append(f"passed domain {item.get('domain_id')} has deprecated subdomain P3 workspaces: {', '.join(subdomain_workspaces)}")
        if len(domain_workspaces) != 1:
            errors.append(f"passed domain {item.get('domain_id')} must have exactly one domain-level P3 workspace")
    if errors:
        print(f"FAILED: final index validation ({len(errors)} errors)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(f"PASSED: final index validation ({len(ddi_passed)} passed domains)")
    return 0


def domains_of(index: dict[str, Any]) -> list[dict[str, Any]]:
    return index.get("domain_design_index", {}).get("domains") or index.get("main_domains", [])


def review_passed(ws: Path, domain: dict[str, Any]) -> bool:
    if domain.get("review_status") == "passed":
        return True
    value = domain.get("review_result_file")
    if not value:
        return False
    path = Path(value)
    path = path if path.is_absolute() else ws / path
    if not path.exists():
        return False
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return (data.get("review_result") or {}).get("status") == "passed"


if __name__ == "__main__":
    raise SystemExit(main())

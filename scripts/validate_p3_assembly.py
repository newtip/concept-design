#!/usr/bin/env python3
"""Validate P3 assembly report and domain-level final coverage."""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    args = parser.parse_args()
    ws = Path(args.workspace)
    report_path = ws / "final" / "p3-assembly-report.yaml"
    errors: list[str] = []
    if not report_path.exists():
        errors.append("final/p3-assembly-report.yaml missing")
    else:
        report = (yaml.safe_load(report_path.read_text(encoding="utf-8")) or {}).get("p3_assembly_report", {})
        status = report.get("status")
        if status != "passed":
            errors.append("p3_assembly_report.status must be passed")
        if report.get("required_domain_count") != report.get("required_workspace_count"):
            errors.append("required_domain_count must equal required_workspace_count")
        if report.get("required_workspace_count") != report.get("validated_workspace_count"):
            errors.append("required_workspace_count must equal validated_workspace_count")
        for field in ["invalid_subdomain_workspace_ids", "missing_domain_workspace_ids", "duplicate_domain_workspace_ids", "missing_or_failed"]:
            if report.get(field):
                errors.append(f"p3_assembly_report.{field} must be empty")
        if status == "passed" and not (ws / "final" / "overview-design.md").exists():
            errors.append("passed assembly requires final/overview-design.md")
    deprecated_dirs = [item.name for item in (ws / "p3-workspaces").glob("P3-WS-*-SD*")] if (ws / "p3-workspaces").exists() else []
    if deprecated_dirs:
        errors.append(f"deprecated subdomain P3 workspace directories exist: {', '.join(deprecated_dirs)}")
    if errors:
        print(f"FAILED: P3 assembly validation ({len(errors)} errors)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASSED: P3 assembly validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

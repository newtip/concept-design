#!/usr/bin/env python3
"""Validate structured Review Agent outputs for every P2 domain."""
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

REQUIRED_MARKERS = [
    "Review 结论",
    "输入确认",
    "模块逐项检查",
    "Source ID",
    "泛化设计",
    "问题清单",
    "Re-report",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    args = parser.parse_args()
    ws = Path(args.workspace)
    index_path = ws / "domain-design-index.yaml"
    if not index_path.exists():
        raise SystemExit("domain-design-index.yaml missing")
    index = yaml.safe_load(index_path.read_text(encoding="utf-8")) or {}
    domains = index.get("main_domains") or index.get("domain_design_index", {}).get("domains", [])
    errors: list[str] = []
    for domain in domains:
        result = review_result_path(ws, domain)
        report = review_report_path(ws, domain)
        modules = [m.get("module_id") for m in domain.get("sub_domains", []) if isinstance(m, dict)]
        validate_one(result, report, domain.get("domain_id", ""), modules, errors)
    if errors:
        print(f"FAILED: review validation ({len(errors)} errors)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASSED: review validation")
    return 0


def validate_one(result_path: Path, report_path: Path, domain_id: str, module_ids: list[str], errors: list[str]) -> None:
    if not result_path.exists():
        errors.append(f"{domain_id}: review-result.yaml missing: {result_path}")
        return
    result_doc = yaml.safe_load(result_path.read_text(encoding="utf-8")) or {}
    result = result_doc.get("review_result")
    if not isinstance(result, dict):
        errors.append(f"{domain_id}: review-result.yaml missing review_result root")
        return
    validate_result_shape(result_path, domain_id, result, errors)
    status = result.get("status")
    passed = status == "passed"

    reviewed = set(str(x) for x in result.get("reviewed_modules", []) or [])
    missing = [m for m in module_ids if m and m not in reviewed]
    if missing:
        errors.append(f"{domain_id}: review_result.reviewed_modules missing {missing}")
    if int(result.get("source_check_count") or 0) < min(10, max(1, len(module_ids) * 3)):
        errors.append(f"{domain_id}: source_check_count too low")
    if passed and int(result.get("blocker_count") or 0) > 0:
        errors.append(f"{domain_id}: status=passed but blocker_count > 0")
    if passed and int(result.get("critical_count") or 0) > 0:
        errors.append(f"{domain_id}: status=passed but critical_count > 0")

    if not report_path.exists():
        errors.append(f"{domain_id}: review-report.md missing: {report_path}")
        return
    text = report_path.read_text(encoding="utf-8", errors="ignore")
    if passed and len(text) < 1200:
        errors.append(f"{domain_id}: status=passed but review report is too short ({len(text)} chars)")
    for marker in REQUIRED_MARKERS:
        if marker not in text:
            errors.append(f"{domain_id}: missing marker {marker}")
    for module_id in module_ids:
        if module_id and module_id not in text:
            errors.append(f"{domain_id}: module {module_id} not reviewed")
    if "Issue ID" not in text or "Severity" not in text or "Evidence" not in text:
        errors.append(f"{domain_id}: issue table must include Issue ID / Severity / Evidence")
    if passed and any(word in text.lower() for word in ["blocker", "critical"]):
        unresolved = [
            line for line in text.splitlines()
            if ("blocker" in line.lower() or "critical" in line.lower())
            and not any(ok in line.lower() for ok in ["resolved", "none", "no blocker", "no critical", "无", "已解决", "blocker_count: 0", "critical_count: 0"])
        ]
        if unresolved:
            errors.append(f"{domain_id}: passed review contains unresolved blocker/critical wording")


def validate_result_shape(path: Path, domain_id: str, result: dict[str, Any], errors: list[str]) -> None:
    required = [
        "domain_id",
        "status",
        "reviewed_modules",
        "issue_count",
        "blocker_count",
        "critical_count",
        "source_check_count",
        "generic_issue_count",
        "issues",
    ]
    for key in required:
        if key not in result:
            errors.append(f"{domain_id}: {path} missing review_result.{key}")
    if result.get("domain_id") != domain_id:
        errors.append(f"{domain_id}: review_result.domain_id mismatch")
    if result.get("status") not in {"passed", "failed"}:
        errors.append(f"{domain_id}: review_result.status must be passed or failed")
    if not isinstance(result.get("reviewed_modules"), list):
        errors.append(f"{domain_id}: review_result.reviewed_modules must be an array")
    for key in ["issue_count", "blocker_count", "critical_count", "source_check_count", "generic_issue_count"]:
        if not isinstance(result.get(key), int) or result.get(key) < 0:
            errors.append(f"{domain_id}: review_result.{key} must be a non-negative integer")
    issues = result.get("issues")
    if not isinstance(issues, list):
        errors.append(f"{domain_id}: review_result.issues must be an array")
        return
    if result.get("issue_count") != len(issues):
        errors.append(f"{domain_id}: issue_count does not match issues length")
    for idx, issue in enumerate(issues, 1):
        if not isinstance(issue, dict):
            errors.append(f"{domain_id}: issue[{idx}] must be a mapping")
            continue
        for key in ["issue_id", "severity", "yaml_path", "problem", "evidence", "required_fix"]:
            if not issue.get(key):
                errors.append(f"{domain_id}: issue[{idx}] missing {key}")
        if issue.get("severity") not in {"blocker", "critical", "major", "minor"}:
            errors.append(f"{domain_id}: issue[{idx}] severity is invalid")


def resolve(ws: Path, value: str | None) -> Path:
    if not value:
        return ws / "<missing-review-path>"
    path = Path(value)
    return path if path.is_absolute() else ws / path


def review_result_path(ws: Path, domain: dict[str, Any]) -> Path:
    if domain.get("review_result_file"):
        return resolve(ws, domain.get("review_result_file"))
    review_file = domain.get("review_file")
    if review_file:
        return resolve(ws, review_file).parent / "review-result.yaml"
    return ws / "domains" / str(domain.get("domain_id", "")) / "review-result.yaml"


def review_report_path(ws: Path, domain: dict[str, Any]) -> Path:
    if domain.get("review_report_file"):
        return resolve(ws, domain.get("review_report_file"))
    review_file = domain.get("review_file")
    if review_file:
        path = resolve(ws, review_file)
        if path.name == "review-report.md":
            return path
        return path.parent / "review-report.md"
    return ws / "domains" / str(domain.get("domain_id", "")) / "review-report.md"


if __name__ == "__main__":
    raise SystemExit(main())

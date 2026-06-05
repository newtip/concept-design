#!/usr/bin/env python3
"""Controlled domain status transitions for domain-design-index.yaml."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from concept_design.domain_state import DomainStage, DomainStateMachine, DomainStateTransitionError
from concept_design.index_store import atomic_write_yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--domain-id", required=True)
    parser.add_argument("--to", required=True, choices=sorted(stage.value for stage in DomainStage))
    parser.add_argument("--reason", default="")
    args = parser.parse_args()
    ws = Path(args.workspace)
    path = ws / "domain-design-index.yaml"
    index = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    domains = domains_of(index)
    domain = next((d for d in domains if d.get("domain_id") == args.domain_id), None)
    if not domain:
        print(f"domain not found: {args.domain_id}", file=sys.stderr)
        return 1
    current = domain.get("stage") or domain.get("status") or "pending"
    target = DomainStage(args.to)
    if target == DomainStage.PASSED:
        errors = preflight_pass(ws, domain)
        if errors:
            print("FAILED: cannot mark passed")
            for error in errors:
                print(f"  - {error}")
            return 1
    elif target == DomainStage.REPAIR_REQUIRED:
        status = load_review_result_status(review_result_path(ws, domain), domain.get("domain_id", ""))
        if status != "failed":
            print("FAILED: review_result.status must be failed to enter repair_required")
            return 1
    elif target == DomainStage.HUMAN_REVIEW_REQUIRED:
        status = load_review_result_status(review_result_path(ws, domain), domain.get("domain_id", ""))
        if status != "needs_human_review":
            print("FAILED: review_result.status must be needs_human_review to enter human_review_required")
            return 1
    try:
        DomainStateMachine.transition_domain(domain, target, args.reason or f"update_domain_status: {current} -> {target.value}")
    except (ValueError, DomainStateTransitionError) as exc:
        print(f"invalid transition: {exc}", file=sys.stderr)
        return 1
    write_index(path, index)
    print(f"{args.domain_id}: {current} -> {target.value}")
    return 0


def preflight_pass(ws: Path, domain: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    output = resolve(ws, domain.get("output_file"))
    review_result = review_result_path(ws, domain)
    review_report = review_report_path(ws, domain)
    if not output.exists():
        errors.append(f"output_file missing: {output}")
    validate_review_result_passed(review_result, domain.get("domain_id", ""), errors)
    if not review_report.exists():
        errors.append(f"review_report_file missing: {review_report}")
    script_dir = Path(__file__).resolve().parent
    for script, extra in [("validate_schema.py", ["--file", str(output)]), ("validate_review.py", [])]:
        cmd = [sys.executable, str(script_dir / script), "--workspace", str(ws)] + extra
        result = subprocess.run(cmd, text=True, capture_output=True)
        if result.returncode != 0:
            errors.append(f"{script} failed: {result.stdout.strip() or result.stderr.strip()}")
    return errors


def validate_review_result_passed(path: Path, domain_id: str, errors: list[str]) -> None:
    if not path.exists():
        errors.append(f"review_result_file missing: {path}")
        return
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        errors.append(f"review_result_file cannot be parsed: {exc}")
        return
    result = validate_review_result_shape(data, domain_id, errors)
    if not result:
        return
    if result.get("status") != "passed":
        errors.append("review_result.status is not passed")
    if int(result.get("blocker_count") or 0) > 0:
        errors.append("review_result.blocker_count must be 0 for passed domain")
    if int(result.get("critical_count") or 0) > 0:
        errors.append("review_result.critical_count must be 0 for passed domain")


def load_review_result_status(path: Path, domain_id: str) -> str:
    if not path.exists():
        return "missing"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return "invalid"
    errors: list[str] = []
    result = validate_review_result_shape(data, domain_id, errors)
    return str(result.get("status", "missing")) if result else "invalid"


def validate_review_result_shape(data: dict[str, Any], domain_id: str, errors: list[str]) -> dict[str, Any] | None:
    result = data.get("review_result")
    if not isinstance(result, dict):
        errors.append("review_result_file missing review_result root")
        return None
    if result.get("domain_id") != domain_id:
        errors.append("review_result.domain_id mismatch")
    if result.get("status") not in {"passed", "failed", "needs_human_review"}:
        errors.append("review_result.status must be passed, failed, or needs_human_review")
    return result


def domains_of(index: dict[str, Any]) -> list[dict[str, Any]]:
    return index.get("domain_design_index", {}).get("domains") or index.get("main_domains", [])


def write_index(path: Path, index: dict[str, Any]) -> None:
    domains = domains_of(index)
    if "domain_design_index" in index:
        index["domain_design_index"]["domains"] = domains
    index["main_domains"] = domains
    atomic_write_yaml(path, index)


def resolve(ws: Path, value: str | None) -> Path:
    if not value:
        return ws / "<missing>"
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

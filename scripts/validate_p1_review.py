#!/usr/bin/env python3
"""Validate P1 Review/Repair/Re-report files before Checkpoint."""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml

MARKERS = [
    "Review 结论",
    "输入确认",
    "需求事实检查",
    "行业洞察边界检查",
    "DDD Scope 检查",
    "覆盖率检查",
    "问题清单",
    "Re-report",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    args = parser.parse_args()
    ws = Path(args.workspace)
    run_id = load_run_id(ws)
    p1_dir = ws / "runs" / run_id / "p1"
    if not p1_dir.exists():
        p1_dir = ws / "runs" / run_id / "P1"
    errors: list[str] = []
    review = p1_dir / "p1-review-checklist.md"
    repair = p1_dir / "p1-repair-log.md"
    rereport = p1_dir / "p1-rereport.md"
    for path, label in [(review, "P1 review"), (repair, "P1 repair log"), (rereport, "P1 rereport")]:
        if not path.exists():
            errors.append(f"{label} missing: {path}")
    if review.exists():
        text = review.read_text(encoding="utf-8", errors="ignore")
        if "status:" not in text:
            errors.append("P1 review missing status")
        if "status: passed" in text.lower() and len(text) < 1200:
            errors.append("P1 review status=passed but file is too short (<1200 chars)")
        for marker in MARKERS:
            if marker not in text:
                errors.append(f"P1 review missing marker: {marker}")
        if "Issue ID" not in text or "Severity" not in text or "Evidence" not in text:
            errors.append("P1 review issue table must include Issue ID / Severity / Evidence")
    if errors:
        print(f"FAILED: P1 review validation ({len(errors)} errors)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASSED: P1 review validation")
    return 0


def load_run_id(ws: Path) -> str:
    state = ws / "project-state.yaml"
    if state.exists():
        data = yaml.safe_load(state.read_text(encoding="utf-8")) or {}
        return data.get("project_state", {}).get("run_id") or data.get("run_id") or "manual-run"
    index = ws / "domain-design-index.yaml"
    if index.exists():
        data = yaml.safe_load(index.read_text(encoding="utf-8")) or {}
        return data.get("run_id") or data.get("domain_design_index", {}).get("run_id") or "manual-run"
    return "manual-run"


if __name__ == "__main__":
    raise SystemExit(main())

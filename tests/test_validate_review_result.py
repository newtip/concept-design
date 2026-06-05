from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

from scripts.validate_review import REQUIRED_MARKERS


def write_index(ws: Path) -> None:
    (ws / "domain-design-index.yaml").write_text(
        yaml.safe_dump(
            {
                "main_domains": [
                    {
                        "domain_id": "DM-001",
                        "review_file": "domains/DM-001/legacy-review.md",
                        "sub_domains": [
                            {"module_id": "MOD-A"},
                            {"module_id": "MOD-B"},
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def write_report(ws: Path, *, include_markdown_status: bool = False) -> None:
    report = ws / "domains" / "DM-001" / "review-report.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Review Report"]
    if include_markdown_status:
        lines.append("status: passed")
    lines.extend(REQUIRED_MARKERS)
    lines.extend(["MOD-A", "MOD-B", "Issue ID | Severity | Evidence"])
    lines.append("Detailed evidence. " * 100)
    report.write_text("\n".join(lines), encoding="utf-8")


def write_result(ws: Path, status: str = "passed") -> None:
    result = ws / "domains" / "DM-001" / "review-result.yaml"
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text(
        yaml.safe_dump(
            {
                "review_result": {
                    "domain_id": "DM-001",
                    "status": status,
                    "reviewed_modules": ["MOD-A", "MOD-B"],
                    "issue_count": 0,
                    "blocker_count": 0,
                    "critical_count": 0,
                    "source_check_count": 10,
                    "generic_issue_count": 0,
                    "issues": [],
                }
            }
        ),
        encoding="utf-8",
    )


def run_validate(ws: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/validate_review.py", "--workspace", str(ws)],
        text=True,
        capture_output=True,
    )


def test_markdown_status_without_review_result_is_rejected(tmp_path):
    write_index(tmp_path)
    write_report(tmp_path, include_markdown_status=True)

    result = run_validate(tmp_path)

    assert result.returncode == 1
    assert "review-result.yaml missing" in result.stdout


def test_structured_review_result_is_status_source(tmp_path):
    write_index(tmp_path)
    write_report(tmp_path, include_markdown_status=False)
    write_result(tmp_path, status="passed")

    result = run_validate(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr

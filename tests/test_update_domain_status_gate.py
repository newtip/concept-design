from __future__ import annotations

from types import SimpleNamespace

import yaml

from scripts import update_domain_status


def domain() -> dict:
    return {
        "domain_id": "DM-001",
        "output_file": "domains/DM-001/design.yaml",
        "review_result_file": "domains/DM-001/review-result.yaml",
        "review_report_file": "domains/DM-001/review-report.md",
    }


def write_common_files(tmp_path) -> None:
    (tmp_path / "domains" / "DM-001").mkdir(parents=True, exist_ok=True)
    (tmp_path / "domains" / "DM-001" / "design.yaml").write_text("main_domain_functional_design: {}\n", encoding="utf-8")
    (tmp_path / "domains" / "DM-001" / "review-report.md").write_text("status: passed\n", encoding="utf-8")


def write_review_result(tmp_path, status: str) -> None:
    (tmp_path / "domains" / "DM-001" / "review-result.yaml").write_text(
        yaml.safe_dump(
            {
                "review_result": {
                    "domain_id": "DM-001",
                    "status": status,
                    "blocker_count": 0,
                    "critical_count": 0,
                }
            }
        ),
        encoding="utf-8",
    )


def fake_successful_subprocess(monkeypatch) -> None:
    monkeypatch.setattr(
        update_domain_status.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="", stderr=""),
    )


def test_passed_domain_requires_structured_review_result(tmp_path, monkeypatch):
    fake_successful_subprocess(monkeypatch)
    write_common_files(tmp_path)

    errors = update_domain_status.preflight_pass(tmp_path, domain())

    assert any("review_result_file missing" in error for error in errors)


def test_markdown_passed_status_cannot_override_failed_review_result(tmp_path, monkeypatch):
    fake_successful_subprocess(monkeypatch)
    write_common_files(tmp_path)
    write_review_result(tmp_path, "failed")

    errors = update_domain_status.preflight_pass(tmp_path, domain())

    assert "review_result.status is not passed" in errors


def test_passed_review_result_allows_domain_passed(tmp_path, monkeypatch):
    fake_successful_subprocess(monkeypatch)
    write_common_files(tmp_path)
    write_review_result(tmp_path, "passed")

    errors = update_domain_status.preflight_pass(tmp_path, domain())

    assert errors == []

from __future__ import annotations

import pytest
import yaml

from concept_design.access_policy import AccessPolicy, AccessScope, AccessViolation


def write_index(workspace):
    (workspace / "domain-design-index.yaml").write_text(
        yaml.safe_dump(
            {
                "domain_design_index": {
                    "domains": [
                        {
                            "domain_id": "DM-001",
                            "status": "passed",
                            "stage": "draft_generated",
                            "context_pack_file": "context-packs/DM-001-context.yaml",
                            "output_file": "domains/DM-001/tp-main-domain-functional-design.yaml",
                            "review_file": "domains/DM-001/tp-review-checklist.md",
                            "review_result_file": "domains/DM-001/review-result.yaml",
                            "review_report_file": "domains/DM-001/review-report.md",
                            "confirmed_design_scope_file": "domains/DM-001/confirmed_design_scope.yaml",
                        },
                        {
                            "domain_id": "DM-002",
                            "status": "reviewing",
                            "stage": "reviewing",
                            "context_pack_file": "context-packs/DM-002-context.yaml",
                            "output_file": "domains/DM-002/ops-main-domain-functional-design.yaml",
                            "review_file": "domains/DM-002/ops-review-checklist.md",
                            "review_result_file": "domains/DM-002/review-result.yaml",
                            "review_report_file": "domains/DM-002/review-report.md",
                            "confirmed_design_scope_file": "domains/DM-002/confirmed_design_scope.yaml",
                        },
                    ]
                }
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture
def workspace(tmp_path):
    write_index(tmp_path)
    return tmp_path


def test_p2_can_read_current_context_pack(workspace):
    AccessPolicy().assert_can_read(AccessScope.P2, workspace, "context-packs/DM-001-context.yaml", "DM-001")


def test_p2_rejects_raw_input(workspace):
    with pytest.raises(AccessViolation):
        AccessPolicy().assert_can_read(AccessScope.P2, workspace, "input/source.docx", "DM-001")


def test_p2_rejects_p1_business_model(workspace):
    with pytest.raises(AccessViolation):
        AccessPolicy().assert_can_read(AccessScope.P2, workspace, "p1/business_model.yaml", "DM-001")


def test_p2_rejects_other_domain_design_file(workspace):
    with pytest.raises(AccessViolation):
        AccessPolicy().assert_can_read(
            AccessScope.P2,
            workspace,
            "domains/DM-002/ops-main-domain-functional-design.yaml",
            "DM-001",
        )


def test_p2_rejects_domain_design_index_write(workspace):
    with pytest.raises(AccessViolation):
        AccessPolicy().assert_can_write(AccessScope.P2, workspace, "domain-design-index.yaml", "DM-001")


def test_p2_review_can_write_review_result(workspace):
    AccessPolicy().assert_can_write(AccessScope.P2_REVIEW, workspace, "domains/DM-001/review-result.yaml", "DM-001")


def test_p2_review_rejects_domain_design_index_write(workspace):
    with pytest.raises(AccessViolation):
        AccessPolicy().assert_can_write(AccessScope.P2_REVIEW, workspace, "domain-design-index.yaml", "DM-001")


def test_p2_repair_can_write_repair_log(workspace):
    data = yaml.safe_load((workspace / "domain-design-index.yaml").read_text(encoding="utf-8"))
    data["domain_design_index"]["domains"][0]["stage"] = "repair_required"
    (workspace / "domain-design-index.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    AccessPolicy().assert_can_write(AccessScope.P2_REPAIR, workspace, "domains/DM-001/repair-log.yaml", "DM-001")


def test_p3_can_read_passed_domain_design(workspace):
    write_index(workspace)
    data = yaml.safe_load((workspace / "domain-design-index.yaml").read_text(encoding="utf-8"))
    data["domain_design_index"]["domains"][0]["stage"] = "passed"
    (workspace / "domain-design-index.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")
    AccessPolicy().assert_can_read(
        AccessScope.P3,
        workspace,
        "domains/DM-001/confirmed_design_scope.yaml",
    )


def test_p3_rejects_non_passed_domain_design(workspace):
    with pytest.raises(AccessViolation):
        AccessPolicy().assert_can_read(
            AccessScope.P3,
            workspace,
            "domains/DM-002/confirmed_design_scope.yaml",
        )

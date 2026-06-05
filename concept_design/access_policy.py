"""Filesystem access governance for concept-design execution scopes."""
from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml


class AccessScope(StrEnum):
    P0 = "P0"
    P1 = "P1"
    CHECKPOINT = "CHECKPOINT"
    P2 = "P2"
    P2_REVIEW = "P2_REVIEW"
    P2_REPAIR = "P2_REPAIR"
    P3 = "P3"


class AccessViolation(RuntimeError):
    """Raised when a stage attempts to read or write a forbidden path."""


class AccessPolicy:
    """Assert stage-specific workspace read/write permissions."""

    FORBIDDEN_P2_READ_PREFIXES = ("input/", "raw/", "p0/", "p1/", "baselines/")
    FORBIDDEN_P2_WRITE_PREFIXES = ("p1/", "context-packs/", "final/")
    FORBIDDEN_INDEX_FILES = {"domain-design-index.yaml", "project-state.yaml"}

    def assert_can_read(
        self,
        scope: AccessScope,
        workspace: str | Path,
        path: str | Path,
        domain_id: str | None = None,
    ) -> None:
        ws = Path(workspace)
        rel = self._relative(ws, path)
        if scope == AccessScope.P1:
            self._assert_p1_read(rel)
        elif scope == AccessScope.P2:
            self._assert_p2_read(ws, rel, domain_id)
        elif scope == AccessScope.P2_REVIEW:
            self._assert_p2_review_read(ws, rel, domain_id)
        elif scope == AccessScope.P2_REPAIR:
            self._assert_p2_repair_read(ws, rel, domain_id)
        elif scope == AccessScope.P3:
            self._assert_p3_read(ws, rel, domain_id)

    def assert_can_write(
        self,
        scope: AccessScope,
        workspace: str | Path,
        path: str | Path,
        domain_id: str | None = None,
    ) -> None:
        ws = Path(workspace)
        rel = self._relative(ws, path)
        if scope == AccessScope.P1:
            self._assert_p1_write(rel)
        elif scope == AccessScope.P2:
            self._assert_p2_write(ws, rel, domain_id)
        elif scope == AccessScope.P2_REVIEW:
            self._assert_p2_review_write(ws, rel, domain_id)
        elif scope == AccessScope.P2_REPAIR:
            self._assert_p2_repair_write(ws, rel, domain_id)
        elif scope == AccessScope.P3:
            self._assert_p3_write(ws, rel, domain_id)

    def _assert_p1_read(self, rel: str) -> None:
        allowed = (
            "parsed/document.md",
            "parsed/document-ir.yaml",
            "parsed/image-manifest.yaml",
        )
        allowed_prefixes = ("parsed/tables/", "parsed/images/")
        if rel in allowed or rel.startswith(allowed_prefixes):
            return
        raise AccessViolation(f"P1 read is not allowed: {rel}")

    def _assert_p1_write(self, rel: str) -> None:
        raise AccessViolation(f"P1 write is not allowed: {rel}")

    def _assert_p2_read(self, ws: Path, rel: str, domain_id: str | None) -> None:
        self._require_domain(domain_id)
        self._reject_prefixes(rel, self.FORBIDDEN_P2_READ_PREFIXES, "P2 cannot read raw input, P0, P1, or baselines")
        allowed = self._domain_read_paths(ws, domain_id)
        if self._is_related_summary(rel, domain_id):
            return
        if rel in allowed:
            return
        other = self._domain_id_from_rel(rel)
        if other and other != domain_id and self._is_formal_domain_result(ws, rel, other):
            raise AccessViolation("P2 cannot read another domain's full design result")
        if self._is_formal_domain_result(ws, rel, domain_id):
            return
        raise AccessViolation(f"P2 read is not allowed: {rel}")

    def _assert_p2_write(self, ws: Path, rel: str, domain_id: str | None) -> None:
        self._require_domain(domain_id)
        self._reject_index_write(rel)
        self._reject_prefixes(rel, self.FORBIDDEN_P2_WRITE_PREFIXES, "P2 cannot write upstream, context-pack, or final artifacts")
        domain = self._domain(ws, domain_id)
        allowed = {
            self._normalize(domain.get("output_file") or f"domains/{domain_id}/tp-main-domain-functional-design.yaml"),
            f"domains/{domain_id}/p2-run-log.yaml",
        }
        if rel not in allowed:
            raise AccessViolation(f"P2 write is not allowed: {rel}")

    def _assert_p2_review_read(self, ws: Path, rel: str, domain_id: str | None) -> None:
        self._require_domain(domain_id)
        domain = self._domain(ws, domain_id)
        self._require_stage(domain, {"draft_generated", "schema_validated", "checkpoint_confirmed", "rereviewing"}, "P2_REVIEW")
        allowed = {
            self._normalize(domain.get("context_pack_file") or f"context-packs/{domain_id}-context.yaml"),
            self._normalize(domain.get("output_file") or f"domains/{domain_id}/tp-main-domain-functional-design.yaml"),
        }
        if rel not in allowed:
            raise AccessViolation(f"P2_REVIEW read is not allowed: {rel}")

    def _assert_p2_review_write(self, ws: Path, rel: str, domain_id: str | None) -> None:
        self._require_domain(domain_id)
        self._reject_index_write(rel)
        domain = self._domain(ws, domain_id)
        self._require_stage(domain, {"draft_generated", "schema_validated", "checkpoint_confirmed", "rereviewing"}, "P2_REVIEW")
        allowed = {
            self._normalize(domain.get("review_result_file") or f"domains/{domain_id}/review-result.yaml"),
            self._normalize(domain.get("review_report_file") or f"domains/{domain_id}/review-report.md"),
            self._normalize(domain.get("review_file") or f"domains/{domain_id}/tp-review-checklist.md"),
        }
        if rel not in allowed:
            raise AccessViolation(f"P2_REVIEW write is not allowed: {rel}")

    def _assert_p2_repair_read(self, ws: Path, rel: str, domain_id: str | None) -> None:
        self._require_domain(domain_id)
        domain = self._domain(ws, domain_id)
        self._require_stage(domain, {"repair_required", "review_failed"}, "P2_REPAIR")
        allowed = {
            self._normalize(domain.get("context_pack_file") or f"context-packs/{domain_id}-context.yaml"),
            self._normalize(domain.get("output_file") or f"domains/{domain_id}/tp-main-domain-functional-design.yaml"),
            self._normalize(domain.get("review_result_file") or f"domains/{domain_id}/review-result.yaml"),
            self._normalize(domain.get("review_report_file") or f"domains/{domain_id}/review-report.md"),
        }
        if rel not in allowed:
            raise AccessViolation(f"P2_REPAIR read is not allowed: {rel}")

    def _assert_p2_repair_write(self, ws: Path, rel: str, domain_id: str | None) -> None:
        self._require_domain(domain_id)
        self._reject_index_write(rel)
        domain = self._domain(ws, domain_id)
        self._require_stage(domain, {"repair_required", "review_failed"}, "P2_REPAIR")
        allowed = {
            self._normalize(domain.get("output_file") or f"domains/{domain_id}/tp-main-domain-functional-design.yaml"),
            f"domains/{domain_id}/repair-log.yaml",
        }
        if rel not in allowed:
            raise AccessViolation(f"P2_REPAIR write is not allowed: {rel}")

    def _assert_p3_read(self, ws: Path, rel: str, workspace_id: str | None = None) -> None:
        if rel.startswith("p3-workspaces/"):
            self._assert_p3_workspace_read(rel, workspace_id)
            return
        domain_id = self._domain_id_from_rel(rel)
        if not domain_id:
            if rel in {"domain-design-index.yaml", "final-document-index.yaml"} or rel.startswith("final/"):
                return
            raise AccessViolation(f"P3 read is not allowed: {rel}")
        if rel == f"domains/{domain_id}/exclusion-summary.yaml":
            return
        domain = self._domain(ws, domain_id)
        confirmed = self._normalize(domain.get("confirmed_design_scope_file") or f"domains/{domain_id}/confirmed_design_scope.yaml")
        if rel != confirmed:
            raise AccessViolation(f"P3 can only read confirmed_design_scope, got: {rel}")
        if domain.get("stage") not in {"checkpoint_confirmed", "passed"}:
            raise AccessViolation(f"P3 cannot read unconfirmed domain scope: {domain_id}")

    def _assert_p3_workspace_read(self, rel: str, workspace_id: str | None) -> None:
        parts = rel.split("/")
        if len(parts) != 3:
            raise AccessViolation(f"P3 workspace read is not allowed: {rel}")
        actual_workspace = parts[1]
        self._reject_subdomain_workspace(actual_workspace)
        allowed_files = {
            "workspace-manifest.yaml",
            "confirmed_scope_package.yaml",
            "confirmed_design_scope.yaml",
            "context-pack.yaml",
            "source_registry.yaml",
            "hard-constraints.yaml",
            "p2-reference.yaml",
        }
        if parts[2] not in allowed_files:
            raise AccessViolation(f"P3 workspace read is not allowed: {rel}")
        if workspace_id and workspace_id != actual_workspace:
            raise AccessViolation(f"P3 cannot read another workspace context: {rel}")

    def _assert_p3_write(self, ws: Path, rel: str, workspace_id: str | None) -> None:
        if rel in self.FORBIDDEN_INDEX_FILES:
            raise AccessViolation(f"P3 cannot write orchestrator-owned file: {rel}")
        forbidden_prefixes = ("input/", "raw/", "p0/", "p1/", "baselines/", "context-packs/", "domains/", "final/")
        self._reject_prefixes(rel, forbidden_prefixes, "P3 cannot write upstream, domain, context-pack, or final artifacts")
        parts = rel.split("/")
        if len(parts) != 3 or parts[0] != "p3-workspaces":
            raise AccessViolation(f"P3 write is not allowed: {rel}")
        actual_workspace = parts[1]
        self._reject_subdomain_workspace(actual_workspace)
        allowed_files = {
            "p3-agent-output.yaml",
            "p3-agent-output.md",
            "p3-run-log.yaml",
            "p3-agent-prompt.md",
            "p3-agent-input-summary.yaml",
        }
        if parts[2] not in allowed_files:
            raise AccessViolation(f"P3 write is not allowed: {rel}")
        if workspace_id and workspace_id != actual_workspace:
            raise AccessViolation(f"P3 cannot write another workspace: {rel}")

    def _domain_read_paths(self, ws: Path, domain_id: str | None) -> set[str]:
        domain = self._domain(ws, domain_id)
        return {
            self._normalize(domain.get("context_pack_file") or f"context-packs/{domain_id}-context.yaml"),
            self._normalize(domain.get("output_file") or f"domains/{domain_id}/tp-main-domain-functional-design.yaml"),
            self._normalize(domain.get("review_result_file") or f"domains/{domain_id}/review-result.yaml"),
            self._normalize(domain.get("review_report_file") or f"domains/{domain_id}/review-report.md"),
            self._normalize(domain.get("review_file") or f"domains/{domain_id}/tp-review-checklist.md"),
            f"domains/{domain_id}/repair-log.yaml",
        }

    def _is_formal_domain_result(self, ws: Path, rel: str, domain_id: str | None) -> bool:
        if not domain_id:
            return False
        domain = self._domain(ws, domain_id)
        output = self._normalize(domain.get("output_file") or f"domains/{domain_id}/tp-main-domain-functional-design.yaml")
        return rel == output or rel.endswith("-main-domain-functional-design.yaml")

    def _is_related_summary(self, rel: str, domain_id: str | None) -> bool:
        return bool(domain_id) and rel.startswith(f"domains/{domain_id}/related-domain-summaries/") and rel.endswith(".yaml")

    def _reject_index_write(self, rel: str) -> None:
        if rel in self.FORBIDDEN_INDEX_FILES:
            raise AccessViolation(f"cannot write orchestrator-owned file: {rel}")

    def _reject_prefixes(self, rel: str, prefixes: tuple[str, ...], message: str) -> None:
        if any(rel.startswith(prefix) for prefix in prefixes):
            raise AccessViolation(f"{message}: {rel}")

    def _require_domain(self, domain_id: str | None) -> None:
        if not domain_id:
            raise AccessViolation("domain_id is required for domain-scoped access")

    def _require_stage(self, domain: dict[str, Any], allowed: set[str], scope_name: str) -> None:
        stage = domain.get("stage") or domain.get("status") or "pending"
        if stage not in allowed:
            raise AccessViolation(f"{scope_name} is not allowed for domain stage {stage}")

    def _domain(self, ws: Path, domain_id: str | None) -> dict[str, Any]:
        self._require_domain(domain_id)
        for domain in self._domains(ws):
            if domain.get("domain_id") == domain_id:
                return domain
        return {"domain_id": domain_id}

    def _domains(self, ws: Path) -> list[dict[str, Any]]:
        path = ws / "domain-design-index.yaml"
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return data.get("domain_design_index", {}).get("domains") or data.get("main_domains", [])

    def _domain_id_from_rel(self, rel: str) -> str | None:
        parts = rel.split("/")
        if len(parts) >= 3 and parts[0] == "domains":
            return parts[1]
        return None

    def _relative(self, workspace: Path, path: str | Path) -> str:
        ws = workspace.resolve()
        raw = Path(path)
        target = raw if raw.is_absolute() else workspace / raw
        try:
            rel = target.resolve().relative_to(ws)
        except ValueError as exc:
            raise AccessViolation(f"path is outside workspace: {path}") from exc
        return self._normalize(rel)

    def _normalize(self, path: str | Path) -> str:
        return Path(path).as_posix().lstrip("./")

    def _reject_subdomain_workspace(self, workspace_id: str) -> None:
        if "-SD" in workspace_id:
            raise AccessViolation(
                f"P3 workspace granularity is domain-level; subdomain workspace ids are not allowed: {workspace_id}"
            )

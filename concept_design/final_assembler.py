"""Final design assembly from validated domain-level P3 agent outputs."""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .agent_logger import AgentLogger
from .project_state import GateError


CHAPTERS = [
    "第 1 章 项目概述",
    "第 2 章 需求与业务分析",
    "第 3 章 领域架构设计",
    "第 4 章 数据模型设计",
    "第 5 章 领域功能设计",
    "第 6 章 跨领域接口与协作",
    "第 7 章 权限设计",
    "第 8 章 DFX 设计",
    "第 9 章 不满足设计",
    "第 10 章 遗留问题",
    "第 11 章 后续建议",
]


@dataclass
class FinalAssembler:
    workspace: Path

    def assemble(self, coverage: str = "full") -> dict[str, Any]:
        self._ensure_final_index()
        required, preflight_errors = self._required_workspaces(coverage)
        outputs: list[dict[str, Any]] = []
        errors: list[str] = list(preflight_errors)
        for item in required:
            workspace_id = item["workspace_id"]
            output = self.workspace / "p3-workspaces" / workspace_id / "p3-agent-output.yaml"
            if not output.exists():
                errors.append(f"{workspace_id}: p3-agent-output.yaml missing")
                continue
            validation = self._validate_workspace(workspace_id)
            if validation:
                errors.extend(f"{workspace_id}: {error}" for error in validation)
                continue
            outputs.append(load_output(output))
        if errors:
            report = self._write_report("failed", coverage, required, outputs, errors)
            raise GateError(f"final assembly blocked; see {report.as_posix()}")
        report_path = self._write_report("passed", coverage, required, outputs, [])
        overview = self._write_overview(outputs, coverage, required)
        AgentLogger(self.workspace).log_agent_execution(
            "10-FinalAssemblyAgent",
            None,
            "finalized",
            "isolated_workspace",
            "Assemble final design from validated domain-level P3 agent outputs only.",
            {"internal_step": "assemble-final-design", "coverage": coverage, "required_workspace_count": len(required)},
            "Final overview and P3 assembly report generated.",
            "final/overview-design.md",
            source_ids_from_outputs(outputs),
        )
        return {"overview": overview, "report": report_path, "workspace_count": len(outputs)}

    def _ensure_final_index(self) -> None:
        if (self.workspace / "final" / "final-document-index.yaml").exists():
            return
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parents[1] / "scripts" / "build_final_document_index.py"), "--workspace", str(self.workspace)],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise GateError((result.stdout + result.stderr).strip())

    def _required_workspaces(self, coverage: str) -> tuple[list[dict[str, Any]], list[str]]:
        index = yaml.safe_load((self.workspace / "domain-design-index.yaml").read_text(encoding="utf-8")) or {}
        domains = index.get("domain_design_index", {}).get("domains") or index.get("main_domains", [])
        result: list[dict[str, Any]] = []
        errors: list[str] = []
        for domain in domains:
            if domain.get("stage") != "passed":
                continue
            if coverage == "core" and not domain.get("required_for_p3", domain.get("p2_required", True)):
                continue
            if coverage == "full" and domain.get("final_exclusion_reason"):
                continue
            workspaces = domain.get("p3_workspaces") or []
            domain_level = [item for item in workspaces if "-SD" not in str(item.get("workspace_id", ""))]
            subdomain_level = [item.get("workspace_id") for item in workspaces if "-SD" in str(item.get("workspace_id", ""))]
            if subdomain_level:
                errors.append(f"{domain.get('domain_id')}: deprecated subdomain P3 workspaces present: {', '.join(subdomain_level)}")
            if len(domain_level) != 1:
                errors.append(f"{domain.get('domain_id')}: expected exactly one domain-level P3 workspace, found {len(domain_level)}")
                continue
            item = domain_level[0]
            result.append(
                {
                    "workspace_id": item.get("workspace_id"),
                    "domain_id": domain.get("domain_id"),
                    "domain_name": domain.get("domain_name"),
                    "domain_type": domain.get("domain_type"),
                    "granularity": item.get("granularity", "domain"),
                    "required_for_p3": domain.get("required_for_p3", domain.get("p2_required", True)),
                    "final_exclusion_reason": domain.get("final_exclusion_reason", ""),
                }
            )
        if not result:
            errors.append("no domain-level P3 workspaces found; run build-p3-workspaces first")
        return result, errors

    def _validate_workspace(self, workspace_id: str) -> list[str]:
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "scripts" / "validate_p3_workspace_output.py"),
                "--workspace",
                str(self.workspace),
                "--p3-workspace-id",
                workspace_id,
            ],
            text=True,
            capture_output=True,
        )
        if result.returncode == 0:
            return []
        text = result.stdout + result.stderr
        return [line.strip(" -") for line in text.splitlines() if line.strip() and not line.startswith("FAILED:")]

    def _write_report(
        self,
        status: str,
        coverage: str,
        required: list[dict[str, Any]],
        outputs: list[dict[str, Any]],
        errors: list[str],
    ) -> Path:
        path = self.workspace / "final" / "p3-assembly-report.yaml"
        valid_ids = [root_output(item).get("workspace_id") for item in outputs]
        required_ids = [item.get("workspace_id") for item in required]
        report = {
            "p3_assembly_report": {
                "status": status,
                "generated_at": utc_now(),
                "coverage": coverage,
                "is_complete_overview_design": status == "passed" and coverage == "full",
                "required_domain_count": len(required),
                "required_workspace_count": len(required_ids),
                "validated_workspace_count": len(valid_ids),
                "required_workspaces": required,
                "validated_workspace_ids": valid_ids,
                "invalid_subdomain_workspace_ids": [item for item in required_ids if item and "-SD" in item],
                "missing_domain_workspace_ids": [item for item in required_ids if item not in valid_ids],
                "duplicate_domain_workspace_ids": duplicates(required_ids),
                "domain_coverage": [
                    {
                        "domain_id": item.get("domain_id"),
                        "domain_name": item.get("domain_name"),
                        "workspace_id": item.get("workspace_id"),
                        "granularity": item.get("granularity", "domain"),
                        "validated": item.get("workspace_id") in valid_ids,
                    }
                    for item in required
                ],
                "missing_or_failed": errors,
            }
        }
        write_yaml(path, report)
        return path

    def _write_overview(self, outputs: list[dict[str, Any]], coverage: str, required: list[dict[str, Any]]) -> Path:
        final_index = yaml.safe_load((self.workspace / "final" / "final-document-index.yaml").read_text(encoding="utf-8")) or {}
        root = final_index.get("final_document_index", final_index)
        stats = root.get("statistics", {})
        output_roots = [root_output(item) for item in outputs]
        lines = ["# 完整版概要设计" if coverage == "full" else "# 核心域概要设计草案", ""]
        lines.extend(
            [
                f"- 生成时间：{utc_now()}",
                f"- 覆盖模式：{coverage}",
                f"- 领域总数：{stats.get('domain_count', 0)}",
                f"- 已通过领域数：{stats.get('passed_domain_count', 0)}",
                f"- 已校验 P3 工作区数：{len(output_roots)}",
                "",
                "## P3 领域输出覆盖矩阵",
                "",
                "| domain_id | domain_name | workspace_id | granularity | required_for_final | validation |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        valid_ids = {item.get("workspace_id") for item in output_roots}
        for item in required:
            lines.append(
                f"| {item.get('domain_id')} | {item.get('domain_name')} | {item.get('workspace_id')} | {item.get('granularity', 'domain')} | true | {'passed' if item.get('workspace_id') in valid_ids else 'missing'} |"
            )
        lines.append("")
        lines.extend(self._chapter_project_overview(stats, output_roots))
        lines.extend(self._chapter_requirements(output_roots))
        lines.extend(self._chapter_architecture(output_roots))
        lines.extend(self._chapter_data_model(output_roots))
        lines.extend(self._chapter_functions(output_roots))
        lines.extend(self._chapter_interfaces(output_roots))
        lines.extend(self._chapter_permissions(output_roots))
        lines.extend(self._chapter_dfx(output_roots))
        lines.extend(self._chapter_unsupported(output_roots))
        lines.extend(self._chapter_open_issues(output_roots))
        lines.extend(self._chapter_suggestions(output_roots))
        lines.extend(["## 需求与决策追踪矩阵", ""])
        lines.append("| source_id | source_type | origin_stage | decision_type | status | domain_id | subdomain_id | 进入章节 | 是否正式设计 |")
        lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for row in trace_rows(self.workspace, outputs):
            lines.append(
                "| {source_id} | {source_type} | {origin_stage} | {decision_type} | {status} | {domain_id} | {subdomain_id} | {chapter} | {formal} |".format(
                    **row
                )
            )
        path = self.workspace / "final" / "overview-design.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def _chapter_project_overview(self, stats: dict[str, Any], outputs: list[dict[str, Any]]) -> list[str]:
        return [
            f"## {CHAPTERS[0]}",
            "",
            f"本概要设计由 {len(outputs)} 个领域级 P3 工作区汇总生成，覆盖已通过评审并进入最终装配范围的领域。",
            f"当前领域统计：核心域 {stats.get('core_domain_count', 0)} 个，支撑域 {stats.get('supporting_domain_count', 0)} 个，通用域 {stats.get('generic_domain_count', 0)} 个。",
            "",
        ]

    def _chapter_requirements(self, outputs: list[dict[str, Any]]) -> list[str]:
        lines = [f"## {CHAPTERS[1]}", ""]
        for root in outputs:
            lines.append(f"### {root.get('domain_id')} {root.get('domain_name')}")
            lines.append(f"- 使用 source_id：{', '.join(root.get('source_ids_used') or [])}")
            lines.append(f"- 删除项：{', '.join(root.get('deleted_item_ids') or []) or '无'}")
            lines.append(f"- 修改项：{', '.join(root.get('modified_item_ids') or []) or '无'}")
        lines.append("")
        return lines

    def _chapter_architecture(self, outputs: list[dict[str, Any]]) -> list[str]:
        lines = [f"## {CHAPTERS[2]}", ""]
        for root in outputs:
            lines.append(f"### {root.get('domain_id')} {root.get('domain_name')}")
            for subdomain in root.get("subdomain_designs") or []:
                lines.append(f"- {subdomain.get('subdomain_id')}: {subdomain.get('subdomain_name')}")
        lines.append("")
        return lines

    def _chapter_data_model(self, outputs: list[dict[str, Any]]) -> list[str]:
        lines = [f"## {CHAPTERS[3]}", ""]
        for root in outputs:
            lines.append(f"### {root.get('domain_id')} 数据模型")
            append_block(lines, root.get("domain_data_model_design"))
            for subdomain in root.get("subdomain_designs") or []:
                lines.append(f"#### {subdomain.get('subdomain_id')} {subdomain.get('subdomain_name')}")
                append_block(lines, subdomain.get("data_model_design"))
        lines.append("")
        return lines

    def _chapter_functions(self, outputs: list[dict[str, Any]]) -> list[str]:
        lines = [f"## {CHAPTERS[4]}", ""]
        for root in outputs:
            lines.append(f"### {root.get('domain_id')} {root.get('domain_name')}")
            append_block(lines, root.get("function_design") or root.get("domain_function_design"))
            for subdomain in root.get("subdomain_designs") or []:
                lines.append(f"#### {subdomain.get('subdomain_id')} {subdomain.get('subdomain_name')}")
                append_block(lines, subdomain.get("function_design"))
                append_block(lines, subdomain.get("workflow_design"))
                append_block(lines, subdomain.get("page_design"))
        lines.append("")
        return lines

    def _chapter_interfaces(self, outputs: list[dict[str, Any]]) -> list[str]:
        lines = [f"## {CHAPTERS[5]}", ""]
        for root in outputs:
            lines.append(f"### {root.get('domain_id')} 接口与协作")
            append_block(lines, root.get("domain_interface_design"))
            append_block(lines, root.get("cross_subdomain_design"))
            for subdomain in root.get("subdomain_designs") or []:
                append_block(lines, subdomain.get("interface_design"))
        lines.append("")
        return lines

    def _chapter_permissions(self, outputs: list[dict[str, Any]]) -> list[str]:
        lines = [f"## {CHAPTERS[6]}", ""]
        for root in outputs:
            lines.append(f"### {root.get('domain_id')} 权限")
            append_block(lines, root.get("domain_permission_design"))
            for subdomain in root.get("subdomain_designs") or []:
                append_block(lines, subdomain.get("permission_design"))
        lines.append("")
        return lines

    def _chapter_dfx(self, outputs: list[dict[str, Any]]) -> list[str]:
        lines = [f"## {CHAPTERS[7]}", ""]
        for root in outputs:
            lines.append(f"### {root.get('domain_id')} DFX")
            append_block(lines, root.get("dfx_design"))
            for subdomain in root.get("subdomain_designs") or []:
                append_block(lines, subdomain.get("dfx_design"))
        lines.append("")
        return lines

    def _chapter_unsupported(self, outputs: list[dict[str, Any]]) -> list[str]:
        lines = [f"## {CHAPTERS[8]}", ""]
        for root in outputs:
            items = root.get("unsupported_design") or root.get("excluded_item_ids") or []
            lines.append(f"### {root.get('domain_id')} 不满足范围")
            append_block(lines, items)
            for subdomain in root.get("subdomain_designs") or []:
                append_block(lines, subdomain.get("unsupported_design"))
        lines.append("")
        return lines

    def _chapter_open_issues(self, outputs: list[dict[str, Any]]) -> list[str]:
        lines = [f"## {CHAPTERS[9]}", ""]
        for root in outputs:
            lines.append(f"### {root.get('domain_id')} 遗留问题")
            append_block(lines, root.get("open_issues"))
            for subdomain in root.get("subdomain_designs") or []:
                append_block(lines, subdomain.get("open_issues"))
        lines.append("")
        return lines

    def _chapter_suggestions(self, outputs: list[dict[str, Any]]) -> list[str]:
        lines = [f"## {CHAPTERS[10]}", ""]
        for root in outputs:
            lines.append(f"- {root.get('domain_id')}：后续优先处理未决问题、异常回退、跨子领域数据一致性和运行监控闭环。")
        lines.append("")
        return lines


def append_block(lines: list[str], value: Any) -> None:
    if not value:
        lines.append("- 无")
        return
    if isinstance(value, str):
        lines.append(f"- {value}")
    elif isinstance(value, list):
        for item in value:
            append_block(lines, item)
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"- {key}:")
                append_block(lines, item)
            else:
                lines.append(f"- {key}: {item}")
    else:
        lines.append(f"- {value}")


def load_output(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def root_output(output: dict[str, Any]) -> dict[str, Any]:
    return output.get("p3_workspace_output", output)


def trace_rows(workspace: Path, outputs: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for output in outputs:
        root = root_output(output)
        workspace_id = root.get("workspace_id")
        registry = yaml.safe_load((workspace / "p3-workspaces" / workspace_id / "source_registry.yaml").read_text(encoding="utf-8")) or {}
        sources = registry.get("source_registry", {})
        formal = set((root.get("traceability") or {}).get("formal_source_ids") or [])
        source_to_subdomain = (root.get("traceability") or {}).get("source_to_subdomain_map") or {}
        for subdomain in root.get("subdomain_designs") or []:
            formal.update((subdomain.get("traceability") or {}).get("formal_source_ids") or [])
            for source_id in subdomain.get("source_ids_used") or []:
                source_to_subdomain.setdefault(source_id, subdomain.get("subdomain_id"))
        for source_id in root.get("source_ids_used", []):
            meta = sources.get(source_id, {})
            rows.append(
                {
                    "source_id": source_id,
                    "source_type": str(meta.get("source_type", "")),
                    "origin_stage": str(meta.get("origin_stage", "source_registry")),
                    "decision_type": str(meta.get("decision_type", "")),
                    "status": str(meta.get("status", "")),
                    "domain_id": str(root.get("domain_id", "")),
                    "subdomain_id": str(source_to_subdomain.get(source_id, "domain")),
                    "chapter": "第 5 章 领域功能设计" if source_id in formal else "第 8/10 章 DFX 或遗留问题",
                    "formal": "是" if source_id in formal else "否",
                }
            )
    return rows


def source_ids_from_outputs(outputs: list[dict[str, Any]]) -> list[str]:
    ids: set[str] = set()
    for output in outputs:
        ids.update(root_output(output).get("source_ids_used") or [])
    return sorted(ids)


def duplicates(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    result: set[str] = set()
    for value in values:
        if not value:
            continue
        if value in seen:
            result.add(value)
        seen.add(value)
    return sorted(result)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

"""Human checkpoint summary report builders."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass
class SummaryReports:
    workspace: Path

    def summarize_pre_p2(self) -> Path:
        baselines = sorted(path.relative_to(self.workspace).as_posix() for path in (self.workspace / "baselines").glob("*.yaml"))
        registry = load_registry(self.workspace)
        source_types = Counter(meta.get("source_type", "unknown") for meta in registry.values())
        prefixes = Counter(prefix_of(source_id) for source_id in registry)
        packs = []
        for path in sorted((self.workspace / "context-packs").glob("*.yaml")):
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            cp = data.get("context_pack", {})
            packs.append(
                {
                    "file": path.relative_to(self.workspace).as_posix(),
                    "domain_id": cp.get("meta", {}).get("domain_id") or cp.get("domain_id"),
                    "source_types": sorted({meta.get("source_type") for meta in cp.get("source_registry", {}).values() if isinstance(meta, dict)}),
                }
            )
        index = load_index(self.workspace)
        domains = index.get("domain_design_index", {}).get("domains") or index.get("main_domains", [])
        payload = {
            "summary_report": {
                "report_type": "pre_p2",
                "baseline_files": baselines,
                "source_type_counts": dict(source_types),
                "source_prefix_counts": dict(prefixes),
                "context_packs": packs,
                "p2_execution_mode": index.get("p2_execution_mode") or index.get("domain_design_index", {}).get("p2_execution_mode", "mode_a_sequential"),
                "domain_schedule": [
                    {
                        "domain_id": d.get("domain_id"),
                        "sequence": d.get("sequence"),
                        "stage": d.get("stage"),
                        "required_for_p3": d.get("required_for_p3", d.get("p2_required", True)),
                    }
                    for d in sorted(domains, key=lambda item: item.get("sequence", 0))
                ],
            }
        }
        return self._write("pre-p2-summary", payload)

    def summarize_p2_checkpoint(self) -> Path:
        domains = []
        blockers = []
        for scope_path in sorted((self.workspace / "domains").glob("*/confirmed_scope_package.yaml")):
            package = (yaml.safe_load(scope_path.read_text(encoding="utf-8")) or {}).get("confirmed_scope_package", {})
            referenced = set(package.get("accepted_item_ids", [])) | set(package.get("modified_item_ids", [])) | set(package.get("added_item_ids", []))
            subdomains = []
            for domain in package.get("domains", []):
                for subdomain in domain.get("subdomains", []):
                    ids = collect_ids(subdomain)
                    subdomains.append(
                        {
                            "subdomain_id": subdomain.get("subdomain_id"),
                            "subdomain_name": subdomain.get("subdomain_name"),
                            "referenced_item_ids": sorted(ids),
                        }
                    )
                    referenced -= ids
            if referenced:
                blockers.append({"domain_id": package.get("domain_id"), "unplaced_item_ids": sorted(referenced)})
            domains.append(
                {
                    "domain_id": package.get("domain_id"),
                    "accepted_item_ids": package.get("accepted_item_ids", []),
                    "modified_item_ids": package.get("modified_item_ids", []),
                    "added_item_ids": package.get("added_item_ids", []),
                    "deleted_item_ids": package.get("deleted_item_ids", []),
                    "subdomains": subdomains,
                }
            )
        payload = {"summary_report": {"report_type": "p2_checkpoint", "domains": domains, "blockers": blockers}}
        return self._write("p2-checkpoint-summary", payload)

    def summarize_p3_workspaces(self) -> Path:
        workspaces = []
        for manifest_path in sorted((self.workspace / "p3-workspaces").glob("*/workspace-manifest.yaml")):
            manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
            included = collect_ids(manifest.get("included_item_ids", {}))
            workspaces.append(
                {
                    "workspace_id": manifest.get("workspace_id"),
                    "granularity": manifest.get("granularity", "domain"),
                    "domain_id": manifest.get("domain_id"),
                    "domain_name": manifest.get("domain_name"),
                    "included_subdomain_ids": [
                        item.get("subdomain_id")
                        for item in manifest.get("included_subdomains", [])
                        if item.get("subdomain_id")
                    ],
                    "included_count": len(included),
                    "excluded_count": len(manifest.get("excluded_item_ids", [])),
                    "modified_count": len(manifest.get("modified_item_ids", [])),
                    "added_count": len(manifest.get("added_item_ids", [])),
                    "deleted_count": len(manifest.get("deleted_item_ids", [])),
                    "has_img": any(item.startswith("IMG-") for item in included),
                    "has_rule_variant": any(item.startswith("RULE-") and item.endswith(("-N", "-M")) for item in included),
                    "has_fld": any(item.startswith("FLD-") for item in included),
                }
            )
        payload = {"summary_report": {"report_type": "p3_workspaces", "workspace_count": len(workspaces), "workspaces": workspaces}}
        return self._write("p3-workspace-summary", payload)

    def _write(self, name: str, payload: dict[str, Any]) -> Path:
        out_dir = self.workspace / "reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        yaml_path = out_dir / f"{name}.yaml"
        md_path = out_dir / f"{name}.md"
        yaml_path.write_text(yaml.safe_dump(payload, allow_unicode=True, sort_keys=False), encoding="utf-8")
        md_path.write_text(render_markdown(payload), encoding="utf-8")
        return yaml_path


def load_registry(workspace: Path) -> dict[str, Any]:
    for path in [workspace / "baselines" / "source-registry.yaml", workspace / "registry" / "source-registry.yaml"]:
        if path.exists():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return data.get("source_registry", data)
    return {}


def load_index(workspace: Path) -> dict[str, Any]:
    path = workspace / "domain-design-index.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else {}


def collect_ids(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("_id") and isinstance(item, str):
                found.add(item)
            found.update(collect_ids(item))
    elif isinstance(value, list):
        for item in value:
            found.update(collect_ids(item))
    elif isinstance(value, str) and "-" in value:
        found.add(value)
    return found


def prefix_of(source_id: str) -> str:
    base = source_id.removesuffix("-N").removesuffix("-M")
    parts = base.split("-")
    return parts[0] if parts else source_id


def render_markdown(payload: dict[str, Any]) -> str:
    root = payload["summary_report"]
    lines = [f"# {root.get('report_type')} summary", ""]
    for key, value in root.items():
        if key == "report_type":
            continue
        lines.append(f"## {key}")
        if isinstance(value, list):
            for item in value:
                lines.append(f"- {item}")
        else:
            lines.append(str(value))
        lines.append("")
    return "\n".join(lines)

"""P2 domain split checkpoint management."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Any

import yaml

from .id_registry import as_added_id, as_modified_id


class CheckpointError(RuntimeError):
    """Raised when a P2 checkpoint cannot be confirmed."""


@dataclass
class CheckpointManager:
    workspace: Path

    def collect_p2_outputs(self, domains: list[dict[str, Any]]) -> list[dict[str, Any]]:
        outputs = []
        for domain in domains:
            if domain.get("stage") not in {"draft_generated", "schema_validated", "passed"}:
                continue
            design_path = self._resolve(domain.get("design_file") or domain.get("output_file"))
            if not design_path.exists():
                raise CheckpointError(f"{domain.get('domain_id')}: P2 draft missing: {design_path}")
            data = yaml.safe_load(design_path.read_text(encoding="utf-8")) or {}
            md = data.get("main_domain_functional_design", data)
            outputs.append(
                {
                    "domain_id": domain.get("domain_id"),
                    "domain_name": domain.get("domain_name"),
                    "design_file": self._rel(design_path),
                    "subdomains": collect_subdomains(domain, md),
                    "domain_events": collect_domain_events(md),
                    "enrichment_items": collect_enrichment_items(self._load_registry(domain)),
                    "modules": collect_modules(md),
                    "risks": [],
                    "boundary_notes": [],
                    "source_registry": self._load_registry(domain),
                }
            )
        return outputs

    def present_for_user_confirmation(self, domains: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self.collect_p2_outputs(domains)

    def apply_user_modifications(
        self,
        confirmed_domains: list[dict[str, Any]],
        modifications: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        modifications = modifications or {}
        result = []
        for domain_scope in confirmed_domains:
            domain_id = domain_scope["domain_id"]
            mod = modifications.get(domain_id, {})
            numbered = build_numbered_scope(domain_scope, mod)
            scope = {
                "confirmed_design_scope": {
                    "checkpoint_id": mod.get("checkpoint_id", "CP-001"),
                    "confirmation_status": "confirmed_with_modifications" if has_numbered_feedback(mod) else "confirmed",
                    "domain_id": domain_id,
                    "domain_name": domain_scope.get("domain_name"),
                    "confirmed_at": datetime.now().isoformat(timespec="seconds"),
                    "draft_file": domain_scope.get("design_file"),
                    "domains": [numbered],
                    "confirmed_scope_package_file": f"domains/{domain_id}/confirmed_scope_package.yaml",
                    "global_rejected_item_ids": numbered["global_rejected_item_ids"],
                    "global_modified_item_ids": numbered["global_modified_item_ids"],
                    "global_added_item_ids": numbered["global_added_item_ids"],
                    "deleted_item_ids": numbered["deleted_item_ids"],
                    "accepted_item_ids": numbered["accepted_item_ids"],
                    "added_item_ids": numbered["global_added_item_ids"],
                    "excluded_item_ids": numbered["deleted_item_ids"],
                    "modified_item_ids": numbered["global_modified_item_ids"],
                    "open_issue_ids": [item.get("id") for sub in numbered.get("subdomains", []) for item in sub.get("open_issues", [])],
                    "modules": apply_module_modifications(domain_scope.get("modules", []), mod),
                    "risks": list(mod.get("risks", [])) + list(domain_scope.get("risks", [])),
                    "boundary_notes": list(mod.get("boundary_notes", [])) + list(mod.get("notes", [])) + list(domain_scope.get("boundary_notes", [])),
                    "deleted_items": list(mod.get("delete_modules", [])),
                    "source_registry": domain_scope.get("source_registry", {}),
                }
            }
            self._validate_scope_sources(scope)
            out = self.workspace / "domains" / domain_id / "confirmed_design_scope.yaml"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(yaml.safe_dump(scope, allow_unicode=True, sort_keys=False), encoding="utf-8")
            package = build_confirmed_scope_package(scope["confirmed_design_scope"])
            package_out = self.workspace / "domains" / domain_id / "confirmed_scope_package.yaml"
            package_out.write_text(yaml.safe_dump(package, allow_unicode=True, sort_keys=False), encoding="utf-8")
            result.append(scope)
        return result

    def _validate_scope_sources(self, scope: dict[str, Any]) -> None:
        root = scope["confirmed_design_scope"]
        registry = root.get("source_registry", {})
        for path, source_id in iter_source_refs(root):
            meta = registry.get(source_id)
            if not meta:
                raise CheckpointError(f"{root.get('domain_id')}: unknown source_id {source_id} at {path}")
            allowed = set(meta.get("allowed_usage") or [])
            forbidden = set(meta.get("forbidden_usage") or [])
            if "formal_design" in forbidden or "formal_function" in forbidden:
                raise CheckpointError(f"{root.get('domain_id')}: source_id {source_id} forbidden for confirmed design at {path}")
            if not ({"formal_design", "formal_function"} & allowed):
                raise CheckpointError(f"{root.get('domain_id')}: source_id {source_id} is not allowed for confirmed design at {path}")

    def _load_registry(self, domain: dict[str, Any]) -> dict[str, Any]:
        context_path = self._resolve(domain.get("context_pack_file") or f"context-packs/{domain.get('domain_id')}-context.yaml")
        if not context_path.exists():
            raise CheckpointError(f"{domain.get('domain_id')}: context pack missing: {context_path}")
        data = yaml.safe_load(context_path.read_text(encoding="utf-8")) or {}
        registry = data.get("context_pack", {}).get("source_registry", {})
        if not isinstance(registry, dict):
            raise CheckpointError(f"{domain.get('domain_id')}: context pack source_registry must be metadata map")
        return registry

    def _resolve(self, value: str | None) -> Path:
        if not value:
            return self.workspace / "<missing>"
        path = Path(value)
        return path if path.is_absolute() else self.workspace / path

    def _rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.workspace.resolve()).as_posix()


def collect_modules(md: dict[str, Any]) -> list[dict[str, Any]]:
    modules = []
    for module in md.get("modules", []) or []:
        if not isinstance(module, dict):
            continue
        positioning = module.get("module_positioning", {}) or {}
        source = []
        for key in ["source_functions", "source_events", "source_rules", "source_contexts", "source_aggregates"]:
            source.extend(positioning.get(key, []) or [])
        modules.append(
            {
                "module_id": module.get("module_id"),
                "module_name": module.get("module_name"),
                "responsibility": positioning.get("responsibility"),
                "source": sorted(set(normalize_source_ids(source))),
            }
        )
    return modules


def normalize_source_ids(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str):
            result.append(value)
        elif isinstance(value, dict):
            for key in ["source_id", "id", "function_id", "event_id", "rule_id", "context_id", "aggregate_id"]:
                item = value.get(key)
                if isinstance(item, str):
                    result.append(item)
            nested = value.get("source_ids")
            if isinstance(nested, list):
                result.extend(item for item in nested if isinstance(item, str))
        elif isinstance(value, list):
            result.extend(normalize_source_ids(value))
    return result


def collect_subdomains(domain: dict[str, Any], md: dict[str, Any]) -> list[dict[str, Any]]:
    subdomains = []
    configured = domain.get("subdomains") or domain.get("sub_domains") or []
    for idx, subdomain in enumerate(configured, start=1):
        sid = subdomain.get("subdomain_id") or f"SD-{idx:03d}"
        subdomains.append(
            {
                "subdomain_id": sid,
                "subdomain_name": subdomain.get("subdomain_name") or subdomain.get("module_name") or f"Subdomain {idx}",
                "module_id": subdomain.get("module_id"),
            }
        )
    if subdomains:
        return subdomains
    for idx, module in enumerate(md.get("modules", []) or [], start=1):
        subdomains.append(
            {
                "subdomain_id": f"SD-{idx:03d}",
                "subdomain_name": module.get("module_name") or f"Subdomain {idx}",
                "module_id": module.get("module_id"),
            }
        )
    return subdomains


def collect_domain_events(md: dict[str, Any]) -> list[dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    primary_chain = md.get("domain_design_intent", {}).get("primary_event_chain", []) or []
    if isinstance(primary_chain, str):
        primary_chain = [primary_chain]
    for event in primary_chain:
        if isinstance(event, dict):
            event_id = event.get("event_id") or event.get("id") or event.get("name")
            source_ids = event.get("source") or event.get("source_ids") or ([event_id] if event_id else [])
            name = event.get("event_name") or event.get("name") or event_id
        else:
            event_id = str(event)
            source_ids = [event_id]
            name = event_id
        if event_id and is_registry_id(str(event_id)):
            events[str(event_id)] = {"event_id": str(event_id), "name": name, "source_ids": source_ids}
    for module in md.get("modules", []) or []:
        for event in module.get("interface_design", {}).get("published_events", []) or []:
            if isinstance(event, dict):
                event_id = event.get("event_id")
                if event_id:
                    events[event_id] = {
                        "event_id": event_id,
                        "name": event.get("event_name") or event_id,
                        "source_ids": event.get("source", [event_id]),
                    }
            elif isinstance(event, str) and is_registry_id(event):
                events[event] = {"event_id": event, "name": event, "source_ids": [event]}
    return list(events.values())


def is_registry_id(value: str) -> bool:
    return re.match(r"^[A-Z]+(?:-[A-Z]+)?-\d{3}(?:-[MN])?$", value) is not None


def collect_enrichment_items(registry: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped = {"risks": [], "boundaries": [], "exceptions": [], "open_questions": [], "industry": []}
    for source_id, meta in registry.items():
        source_type = meta.get("source_type")
        item = {"id": source_id, "title": meta.get("title"), "source_id": source_id}
        if source_type == "risk_note":
            grouped["risks"].append(item | {"handling_policy": "must_handle_in_design"})
        elif source_type == "boundary_note":
            grouped["boundaries"].append(item | {"handling_policy": "scope_constraint"})
        elif source_type == "exception_note":
            grouped["exceptions"].append(item | {"handling_policy": "must_handle_in_workflow"})
        elif source_type == "open_question":
            grouped["open_questions"].append({"id": source_id, "decision": "keep_as_open_issue", "note": meta.get("title")})
        elif source_type == "industry_enrichment":
            grouped["industry"].append(item)
    return grouped


def has_numbered_feedback(mod: dict[str, Any]) -> bool:
    return any(key in mod for key in ["accepted_item_ids", "rejected_items", "deleted_items", "modified_items", "added_items", "open_issues"])


def build_numbered_scope(domain_scope: dict[str, Any], mod: dict[str, Any]) -> dict[str, Any]:
    rejected_items = list(mod.get("rejected_items", [])) + list(mod.get("deleted_items", []))
    modified_items = [normalize_modified_item(item) for item in mod.get("modified_items", [])]
    added_items = [normalize_added_item(item) for item in mod.get("added_items", [])]
    rejected_ids = {item.get("item_id") for item in rejected_items}
    modified_by_id = {item.get("original_item_id", item.get("item_id")): item for item in modified_items}
    default_ids = default_accepted_ids(domain_scope)
    accepted_ids = (set(mod.get("accepted_item_ids") or default_ids) - rejected_ids) - set(modified_by_id)
    modified_ids = {item.get("item_id") for item in modified_items}
    added_ids = {item.get("item_id") for item in added_items}

    subdomains = []
    events = [apply_item_modification(event, modified_by_id) for event in domain_scope.get("domain_events", []) if event.get("event_id") in accepted_ids]
    events.extend(item for item in added_items if item_type_hint(item.get("item_id")) == "event")
    enrichment = domain_scope.get("enrichment_items", {})
    for subdomain in domain_scope.get("subdomains", []):
        subdomain = apply_item_modification(subdomain, modified_by_id)
        sid = subdomain.get("subdomain_id")
        if sid not in accepted_ids and sid not in modified_ids:
            continue
        subdomains.append(
            {
                "subdomain_id": subdomain.get("subdomain_id"),
                "subdomain_name": subdomain.get("subdomain_name"),
                "accepted_domain_events": events,
                "accepted_enrichment": {
                    "risks": [item for item in enrichment.get("risks", []) if item.get("id") in accepted_ids],
                    "boundaries": [item for item in enrichment.get("boundaries", []) if item.get("id") in accepted_ids],
                    "exceptions": [item for item in enrichment.get("exceptions", []) if item.get("id") in accepted_ids],
                },
                "open_issues": normalize_open_issues(mod.get("open_issues", []), enrichment.get("open_questions", []), accepted_ids),
                "added_items": added_items,
                "deleted_items": rejected_items,
                "rejected_items": rejected_items,
            }
        )
    for item in added_items:
        if item_type_hint(item.get("item_id")) == "subdomain":
            subdomains.append(
                {
                    "subdomain_id": item.get("item_id"),
                    "subdomain_name": item.get("subdomain_name") or item.get("title"),
                    "accepted_domain_events": events,
                    "accepted_enrichment": {"risks": [], "boundaries": [], "exceptions": []},
                    "open_issues": [],
                    "added_items": added_items,
                    "deleted_items": rejected_items,
                    "rejected_items": rejected_items,
                }
            )

    return {
        "domain_id": domain_scope.get("domain_id"),
        "domain_name": domain_scope.get("domain_name"),
        "subdomains": subdomains,
        "accepted_item_ids": sorted(accepted_ids),
        "global_rejected_item_ids": sorted(item_id for item_id in rejected_ids if item_id),
        "global_modified_item_ids": sorted(item_id for item_id in modified_ids if item_id),
        "global_added_item_ids": sorted(item_id for item_id in added_ids if item_id),
        "deleted_item_ids": sorted(item_id for item_id in rejected_ids if item_id),
        "source_id_map": {item_id: item_id for item_id in sorted(accepted_ids | modified_ids | added_ids) if isinstance(item_id, str)},
    }


def default_accepted_ids(domain_scope: dict[str, Any]) -> list[str]:
    ids = [domain_scope.get("domain_id")]
    ids.extend(item.get("subdomain_id") for item in domain_scope.get("subdomains", []))
    ids.extend(item.get("event_id") for item in domain_scope.get("domain_events", []))
    enrichment = domain_scope.get("enrichment_items", {})
    for key in ["risks", "boundaries", "exceptions", "open_questions"]:
        ids.extend(item.get("id") for item in enrichment.get(key, []))
    return [item_id for item_id in ids if item_id]


def apply_item_modification(item: dict[str, Any], modified_by_id: dict[str, dict[str, Any]]) -> dict[str, Any]:
    item_id = item.get("item_id") or item.get("id") or item.get("subdomain_id") or item.get("event_id")
    updated = dict(item)
    mod = modified_by_id.get(item_id)
    if mod:
        updated[mod.get("field")] = mod.get("after")
        new_id = mod.get("item_id")
        if item_id != new_id:
            if "subdomain_id" in updated:
                updated["subdomain_id"] = new_id
            elif "event_id" in updated:
                updated["event_id"] = new_id
            else:
                updated["id"] = new_id
            updated["original_item_id"] = item_id
    return updated


def normalize_modified_item(item: dict[str, Any]) -> dict[str, Any]:
    original = item.get("original_item_id") or item.get("item_id")
    updated = dict(item)
    updated["original_item_id"] = original
    updated["item_id"] = item.get("modified_item_id") or as_modified_id(original)
    return updated


def normalize_added_item(item: dict[str, Any]) -> dict[str, Any]:
    updated = dict(item)
    raw_id = item.get("item_id") or item.get("id")
    if raw_id:
        updated["item_id"] = raw_id if raw_id.endswith("-N") else as_added_id(raw_id)
    else:
        raise CheckpointError("added_items require item_id")
    return updated


def item_type_hint(item_id: str | None) -> str:
    if not item_id:
        return ""
    if item_id.startswith("SD-"):
        return "subdomain"
    if item_id.startswith("EVT-"):
        return "event"
    return "item"


def build_confirmed_scope_package(root: dict[str, Any]) -> dict[str, Any]:
    return {
        "confirmed_scope_package": {
            "checkpoint_id": root.get("checkpoint_id"),
            "confirmation_status": root.get("confirmation_status"),
            "domain_id": root.get("domain_id"),
            "domain_name": root.get("domain_name"),
            "confirmed_at": root.get("confirmed_at"),
            "accepted_item_ids": root.get("accepted_item_ids", []),
            "modified_item_ids": root.get("modified_item_ids", []),
            "added_item_ids": root.get("added_item_ids", []),
            "deleted_item_ids": root.get("deleted_item_ids", []),
            "open_issue_ids": root.get("open_issue_ids", []),
            "domains": root.get("domains", []),
            "source_registry": root.get("source_registry", {}),
        }
    }


def normalize_open_issues(feedback: list[dict[str, Any]], defaults: list[dict[str, Any]], accepted_ids: set[str]) -> list[dict[str, Any]]:
    issues = []
    seen = set()
    for item in feedback:
        item_id = item.get("item_id") or item.get("id")
        if item_id:
            issue = {"id": item_id, "decision": item.get("decision", "keep_as_open_issue"), "note": item.get("note", "")}
            if is_user_authorized_default(item):
                issue.update(
                    {
                        "decision_type": "user_authorized_default_design",
                        "decision_origin": "checkpoint_feedback",
                        "decision_basis": "用户授权 Agent 按合理默认设计",
                        "authorized_by_question_id": item_id,
                        "must_not_be_treated_as_original_requirement": True,
                        "allowed_to_generate_default_details": True,
                    }
                )
            issues.append(issue)
            seen.add(item_id)
    for item in defaults:
        if item.get("id") in accepted_ids and item.get("id") not in seen:
            issues.append(item)
    return issues


def is_user_authorized_default(item: dict[str, Any]) -> bool:
    text = " ".join(str(item.get(key, "")) for key in ["decision", "note", "reason"])
    return any(marker in text for marker in ["合理即可", "按合理默认设计", "reasonable default", "default design"])


def apply_module_modifications(modules: list[dict[str, Any]], mod: dict[str, Any]) -> list[dict[str, Any]]:
    deletes = set(mod.get("delete_modules", []) or [])
    overrides = mod.get("module_overrides", {}) or {}
    additions = mod.get("add_modules", []) or []
    result = []
    for module in modules:
        mid = module.get("module_id")
        if mid in deletes:
            continue
        updated = dict(module)
        updated.update(overrides.get(mid, {}))
        result.append(updated)
    result.extend(additions)
    return result


def iter_source_refs(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{path}.{key}"
            if key in {"source", "source_ids"}:
                for source_id in normalize_sources(item):
                    yield child, source_id
            elif key != "source_registry":
                yield from iter_source_refs(item, child)
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            yield from iter_source_refs(item, f"{path}[{idx}]")


def normalize_sources(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []

"""Global item ID registry for numbered traceability."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

import yaml


class ItemType(StrEnum):
    REQUIREMENT_FACT = "requirement_fact"
    INDUSTRY_ENRICHMENT = "industry_enrichment"
    RISK_NOTE = "risk_note"
    BOUNDARY_NOTE = "boundary_note"
    EXCEPTION_NOTE = "exception_note"
    OPEN_QUESTION = "open_question"
    DOMAIN = "domain"
    SUBDOMAIN = "subdomain"
    DOMAIN_EVENT = "domain_event"
    MODULE = "module"
    WORKFLOW = "workflow"
    INTERFACE = "interface"
    PAGE = "page"
    P3_WORKSPACE = "p3_workspace"
    RULE = "rule"
    FIELD = "field"
    PERMISSION = "permission"
    INTEGRATION = "integration"
    IMAGE = "image"


PREFIX_BY_TYPE = {
    ItemType.REQUIREMENT_FACT: "REQ",
    ItemType.INDUSTRY_ENRICHMENT: "IND",
    ItemType.RISK_NOTE: "RISK",
    ItemType.BOUNDARY_NOTE: "BOUND",
    ItemType.EXCEPTION_NOTE: "EXC",
    ItemType.OPEN_QUESTION: "Q",
    ItemType.DOMAIN: "DM",
    ItemType.SUBDOMAIN: "SD",
    ItemType.DOMAIN_EVENT: "EVT",
    ItemType.MODULE: "MOD",
    ItemType.WORKFLOW: "WF",
    ItemType.INTERFACE: "API",
    ItemType.PAGE: "PAGE",
    ItemType.P3_WORKSPACE: "P3-WS",
    ItemType.RULE: "RULE",
    ItemType.FIELD: "FLD",
    ItemType.PERMISSION: "PERM",
    ItemType.INTEGRATION: "INT",
    ItemType.IMAGE: "IMG",
}

TYPE_BY_PREFIX = {prefix: item_type for item_type, prefix in PREFIX_BY_TYPE.items()}


class IdRegistryError(RuntimeError):
    """Raised for invalid or duplicate traceability IDs."""


@dataclass
class IdRegistry:
    items: dict[str, dict[str, Any]] = field(default_factory=dict)

    def register(self, item_type: ItemType | str, title: str, payload: dict[str, Any] | None = None, suffix: str = "") -> str:
        item_type = ItemType(item_type)
        if suffix and suffix not in {"-N", "-M"}:
            raise IdRegistryError(f"invalid item_id suffix: {suffix}")
        prefix = PREFIX_BY_TYPE[item_type]
        next_number = self._next_number(prefix)
        item_id = f"{prefix}-{next_number:03d}{suffix}"
        self.items[item_id] = {
            "item_id": item_id,
            "item_type": item_type.value,
            "title": title,
            "payload": payload or {},
        }
        return item_id

    def validate_id(self, item_id: str, expected_type: ItemType | str | None = None) -> bool:
        item_type = type_for_id(item_id)
        if expected_type is not None and item_type != ItemType(expected_type):
            raise IdRegistryError(f"{item_id} is {item_type.value}, expected {ItemType(expected_type).value}")
        return True

    def assert_unique(self, item_id: str) -> None:
        if item_id in self.items:
            raise IdRegistryError(f"duplicate item_id: {item_id}")

    def resolve(self, item_id: str) -> dict[str, Any]:
        self.validate_id(item_id)
        if item_id not in self.items:
            raise IdRegistryError(f"unknown item_id: {item_id}")
        return self.items[item_id]

    def list_by_type(self, item_type: ItemType | str) -> list[dict[str, Any]]:
        item_type = ItemType(item_type).value
        return [item for item in self.items.values() if item.get("item_type") == item_type]

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump({"item_registry": {"items": self.items}}, allow_unicode=True, sort_keys=False), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "IdRegistry":
        path = Path(path)
        if not path.exists():
            return cls()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        return cls(items=data.get("item_registry", {}).get("items", {}))

    def _next_number(self, prefix: str) -> int:
        pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)(?:-[NM])?$")
        numbers = [int(match.group(1)) for item_id in self.items for match in [pattern.match(item_id)] if match]
        return max(numbers, default=0) + 1


def default_registry_path(workspace: str | Path) -> Path:
    return Path(workspace) / "registry" / "item-registry.yaml"


def type_for_id(item_id: str) -> ItemType:
    if item_id.startswith("P3-WS-"):
        if "-SD" in item_id:
            raise IdRegistryError(f"P3 workspace IDs must be domain-level, got: {item_id}")
        return ItemType.P3_WORKSPACE
    for prefix in sorted(TYPE_BY_PREFIX, key=len, reverse=True):
        if item_id.startswith(f"{prefix}-"):
            suffix = item_id[len(prefix) + 1 :]
            if re.fullmatch(r"\d+(?:-[NM])?", suffix):
                return TYPE_BY_PREFIX[prefix]
    raise IdRegistryError(f"invalid item_id format: {item_id}")


def as_added_id(item_id: str) -> str:
    type_for_id(item_id)
    base = strip_variant_suffix(item_id)
    return f"{base}-N"


def as_modified_id(item_id: str) -> str:
    type_for_id(item_id)
    base = strip_variant_suffix(item_id)
    return f"{base}-M"


def strip_variant_suffix(item_id: str) -> str:
    return re.sub(r"-(N|M)$", "", item_id)

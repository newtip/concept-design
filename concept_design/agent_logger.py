"""Structured audit logging for agent executions."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOG_RELATIVE_PATH = Path("logs") / "agent_execution.jsonl"


@dataclass
class AgentLogger:
    workspace: Path | str

    @property
    def log_file(self) -> Path:
        return Path(self.workspace) / LOG_RELATIVE_PATH

    def log_agent_execution(
        self,
        agent_name: str,
        domain_id: str | None,
        stage: str,
        execution_mode: str,
        prompt: str,
        memory_snapshot: dict[str, Any],
        output_summary: str,
        output_file: str | None,
        source_ids_used: list[str] | None,
        included_item_ids: list[str] | None = None,
        excluded_item_ids: list[str] | None = None,
        modified_item_ids: list[str] | None = None,
        added_item_ids: list[str] | None = None,
        deleted_item_ids: list[str] | None = None,
        workspace_id: str | None = None,
        subdomain_id: str | None = None,
    ) -> dict[str, Any]:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "agent_name": agent_name,
            "domain_id": domain_id,
            "stage": stage,
            "execution_mode": execution_mode,
            "prompt": prompt,
            "memory_snapshot": make_json_safe(memory_snapshot),
            "workspace_id": workspace_id,
            "subdomain_id": subdomain_id,
            "included_item_ids": sorted(set(included_item_ids or [])),
            "excluded_item_ids": sorted(set(excluded_item_ids or [])),
            "modified_item_ids": sorted(set(modified_item_ids or [])),
            "added_item_ids": sorted(set(added_item_ids or [])),
            "deleted_item_ids": sorted(set(deleted_item_ids or [])),
            "source_ids_used": sorted(set(source_ids_used or [])),
            "output_summary": output_summary,
            "output_file": output_file,
        }
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        with self.log_file.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return record


def log_agent_execution(
    workspace: Path | str,
    agent_name: str,
    domain_id: str | None,
    stage: str,
    execution_mode: str,
    prompt: str,
    memory_snapshot: dict[str, Any],
    output_summary: str,
    output_file: str | None,
    source_ids_used: list[str] | None,
    included_item_ids: list[str] | None = None,
    excluded_item_ids: list[str] | None = None,
    modified_item_ids: list[str] | None = None,
    added_item_ids: list[str] | None = None,
    deleted_item_ids: list[str] | None = None,
    workspace_id: str | None = None,
    subdomain_id: str | None = None,
) -> dict[str, Any]:
    return AgentLogger(workspace).log_agent_execution(
        agent_name=agent_name,
        domain_id=domain_id,
        stage=stage,
        execution_mode=execution_mode,
        prompt=prompt,
        memory_snapshot=memory_snapshot,
        output_summary=output_summary,
        output_file=output_file,
        source_ids_used=source_ids_used,
        included_item_ids=included_item_ids,
        excluded_item_ids=excluded_item_ids,
        modified_item_ids=modified_item_ids,
        added_item_ids=added_item_ids,
        deleted_item_ids=deleted_item_ids,
        workspace_id=workspace_id,
        subdomain_id=subdomain_id,
    )


def make_json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): make_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [make_json_safe(item) for item in value]
    if isinstance(value, tuple | set):
        return [make_json_safe(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)

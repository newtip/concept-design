"""P3 isolated workspace execution helpers."""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from .access_policy import AccessPolicy, AccessScope
from .agent_logger import AgentLogger
from .project_state import GateError


INPUT_FILES = [
    "workspace-manifest.yaml",
    "confirmed_scope_package.yaml",
    "confirmed_design_scope.yaml",
    "context-pack.yaml",
    "source_registry.yaml",
    "p2-reference.yaml",
    "hard-constraints.yaml",
]

CONTROLLED_OUTPUT_FILES = [
    "p3-agent-output.yaml",
    "p3-agent-output.md",
    "p3-run-log.yaml",
    "p3-agent-prompt.md",
    "p3-agent-input-summary.yaml",
]


@dataclass
class P3WorkspaceRunner:
    workspace: Path
    workspace_id: str

    @property
    def workspace_dir(self) -> Path:
        return self.workspace / "p3-workspaces" / self.workspace_id

    def run(self, agent_output_file: str | None = None, strict: bool = False) -> str:
        self._assert_ready()
        manifest = self._load_yaml("workspace-manifest.yaml")
        policy = AccessPolicy()
        for name in INPUT_FILES:
            policy.assert_can_read(AccessScope.P3, self.workspace, self._rel(name), self.workspace_id)
        prompt_path = self.workspace_dir / "p3-agent-prompt.md"
        summary_path = self.workspace_dir / "p3-agent-input-summary.yaml"
        policy.assert_can_write(AccessScope.P3, self.workspace, self._rel(prompt_path.name), self.workspace_id)
        policy.assert_can_write(AccessScope.P3, self.workspace, self._rel(summary_path.name), self.workspace_id)
        prompt_path.write_text(self._build_prompt(manifest), encoding="utf-8")
        write_yaml(summary_path, self._build_input_summary(manifest))

        if agent_output_file:
            self._import_agent_output(agent_output_file)

        output_path = self.workspace_dir / "p3-agent-output.yaml"
        if not output_path.exists():
            self._log(
                manifest,
                "P3 agent input bundle generated; awaiting real agent output.",
                "p3-agent-input-summary.yaml",
            )
            print("awaiting_agent_output")
            return "awaiting_agent_output" if not strict else self._raise_missing()

        self._validate_output()
        run_log = {
            "p3_run_log": {
                "workspace_id": self.workspace_id,
                "status": "validated",
                "validated_at": utc_now(),
                "output_file": self._rel("p3-agent-output.yaml"),
            }
        }
        policy.assert_can_write(AccessScope.P3, self.workspace, self._rel("p3-run-log.yaml"), self.workspace_id)
        write_yaml(self.workspace_dir / "p3-run-log.yaml", run_log)
        root = output_root(output_path)
        self._log(
            manifest,
            "P3 workspace agent output validated.",
            "p3-agent-output.yaml",
            root.get("source_ids_used", []),
        )
        return "validated"

    def _assert_ready(self) -> None:
        if "-SD" in self.workspace_id:
            raise GateError(f"P3 workspace granularity is domain-level; subdomain workspace ids are not allowed: {self.workspace_id}")
        if not self.workspace_dir.exists():
            raise GateError(f"P3 workspace not found: {self.workspace_id}")
        missing = [name for name in INPUT_FILES if not (self.workspace_dir / name).exists()]
        if missing:
            raise GateError(f"P3 workspace package incomplete: missing {', '.join(missing)}")

    def _import_agent_output(self, agent_output_file: str) -> None:
        src = Path(agent_output_file)
        if not src.is_absolute():
            src = self.workspace / src
        src = src.resolve()
        upstream_forbidden = ("input", "raw", "p0", "p1", "baselines", "context-packs", "domains", "final")
        try:
            rel = src.relative_to(self.workspace.resolve()).as_posix()
        except ValueError:
            rel = ""
        if rel and (rel.split("/", 1)[0] in upstream_forbidden or rel.startswith("p3-workspaces/") and self.workspace_id not in rel.split("/")[:2]):
            raise GateError(f"agent-output-file cannot be an upstream or other-workspace artifact: {agent_output_file}")
        if not src.exists():
            raise GateError(f"agent-output-file missing: {agent_output_file}")
        AccessPolicy().assert_can_write(AccessScope.P3, self.workspace, self._rel("p3-agent-output.yaml"), self.workspace_id)
        shutil.copyfile(src, self.workspace_dir / "p3-agent-output.yaml")

    def _validate_output(self) -> None:
        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parents[1] / "scripts" / "validate_p3_workspace_output.py"),
                "--workspace",
                str(self.workspace),
                "--p3-workspace-id",
                self.workspace_id,
            ],
            text=True,
            capture_output=True,
        )
        if result.returncode != 0:
            raise GateError((result.stdout + result.stderr).strip())

    def _build_prompt(self, manifest: dict[str, Any]) -> str:
        return "\n".join(
            [
                f"# P3 Workspace Agent Input: {self.workspace_id}",
                "",
                "Use only the isolated files in this P3 workspace.",
                "Do not read raw input, P1/P2 full outputs, baselines, or other P3 workspaces.",
                "Write real agent design output to p3-agent-output.yaml using the P3 workspace output schema.",
                "The output granularity must be domain and must include subdomain_designs for every confirmed subdomain.",
                "",
                f"- domain_id: {manifest.get('domain_id')}",
                f"- domain_name: {manifest.get('domain_name')}",
                f"- granularity: {manifest.get('granularity', 'domain')}",
                f"- included_subdomains: {manifest.get('included_subdomains', [])}",
            ]
        )

    def _build_input_summary(self, manifest: dict[str, Any]) -> dict[str, Any]:
        registry = self._load_yaml("source_registry.yaml").get("source_registry", {})
        return {
            "p3_agent_input_summary": {
                "workspace_id": self.workspace_id,
                "granularity": manifest.get("granularity", "domain"),
                "domain_id": manifest.get("domain_id"),
                "domain_name": manifest.get("domain_name"),
                "included_subdomains": manifest.get("included_subdomains", []),
                "input_files": INPUT_FILES,
                "included_item_ids": manifest.get("included_item_ids", {}),
                "excluded_item_ids": manifest.get("excluded_item_ids", []),
                "modified_item_ids": manifest.get("modified_item_ids", []),
                "added_item_ids": manifest.get("added_item_ids", []),
                "deleted_item_ids": manifest.get("deleted_item_ids", []),
                "source_ids_available": sorted(registry),
            }
        }

    def _log(self, manifest: dict[str, Any], summary: str, output_file: str, source_ids: list[str] | None = None) -> None:
        flat_included = flatten_item_ids(manifest.get("included_item_ids", {}))
        AgentLogger(self.workspace).log_agent_execution(
            "P3WorkspaceAgent",
            manifest.get("domain_id"),
            "p3_workspace_execution",
            "isolated_workspace",
            f"Run P3 workspace pipeline for {self.workspace_id}.",
            {
                "internal_step": "run-p3-workspace",
                "workspace_id": self.workspace_id,
                "granularity": manifest.get("granularity", "domain"),
                "included_subdomain_ids": [item.get("subdomain_id") for item in manifest.get("included_subdomains", [])],
                "input_files": INPUT_FILES,
            },
            summary,
            self._rel(output_file),
            source_ids or flat_included,
            included_item_ids=flat_included,
            excluded_item_ids=manifest.get("excluded_item_ids", []),
            modified_item_ids=manifest.get("modified_item_ids", []),
            added_item_ids=manifest.get("added_item_ids", []),
            deleted_item_ids=manifest.get("deleted_item_ids", []),
            workspace_id=self.workspace_id,
            subdomain_id=None,
        )

    def _load_yaml(self, name: str) -> dict[str, Any]:
        return yaml.safe_load((self.workspace_dir / name).read_text(encoding="utf-8")) or {}

    def _rel(self, name: str) -> str:
        return (Path("p3-workspaces") / self.workspace_id / name).as_posix()

    def _raise_missing(self) -> str:
        raise GateError(f"P3 workspace {self.workspace_id} is awaiting agent output")


def flatten_item_ids(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            found.extend(flatten_item_ids(item))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str):
                found.append(item)
            else:
                found.extend(flatten_item_ids(item))
    elif isinstance(value, str):
        found.append(value)
    return sorted(set(found))


def output_root(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("p3_workspace_output", data)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

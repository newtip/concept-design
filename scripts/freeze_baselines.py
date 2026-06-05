#!/usr/bin/env python3
"""Freeze P1 outputs into baselines after user checkpoint confirmation."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--confirmation-file", default="checkpoint/user-confirmation.yaml")
    args = parser.parse_args()
    ws = Path(args.workspace)
    confirmation_path = ws / args.confirmation_file
    confirmation = load_yaml(confirmation_path) if confirmation_path.exists() else {}
    run_id = load_run_id(ws)
    errors = validate_confirmation(confirmation, run_id)
    if errors:
        print(f"FAILED: cannot freeze baselines ({len(errors)} errors)")
        for error in errors:
            print(f"  - {error}")
        return 1

    run_id = load_run_id(ws)
    p1_dir = find_p1_dir(ws, run_id)
    mapping = [
        ("business_model", find_first(p1_dir, ["business_model.yaml", "01-business-model.yaml"]), ws / "baselines" / "business_model.yaml"),
        ("industry_insight", find_first(p1_dir, ["industry_insight.yaml", "02-industry-insight.yaml"]), ws / "baselines" / "industry_insight.yaml"),
        ("architecture_design", find_first(p1_dir, ["architecture_design.yaml", "03-architecture-design.yaml"]), ws / "baselines" / "architecture_design.yaml"),
    ]
    frozen_at = datetime.now().isoformat(timespec="seconds")
    for label, source, target in mapping:
        if source is None:
            print(f"FAILED: missing P1 output for {label}")
            return 1
        data = load_yaml(source)
        errors = validate_frozen_content(label, data)
        if errors:
            print(f"FAILED: {label} cannot freeze")
            for error in errors:
                print(f"  - {error}")
            return 1
        data = mark_frozen(data, label, frozen_at, confirmation)
        target.parent.mkdir(parents=True, exist_ok=True)
        write_yaml(target, data)
        print(target)
    return 0


def validate_confirmation(data: dict[str, Any], run_id: str) -> list[str]:
    if not data:
        return ["checkpoint/user-confirmation.yaml missing or empty"]
    status = data.get("status") or data.get("confirmation_status")
    if status not in {"confirmed", "approved"}:
        return ["user confirmation status must be confirmed or approved"]
    if data.get("run_id") != run_id:
        return [f"confirmation run_id mismatch: {data.get('run_id')} != project run_id {run_id}"]
    return []


def validate_frozen_content(label: str, data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    root = data.get(label, data)
    if label == "business_model":
        for item in walk_dicts(root):
            if item.get("source_type") == "inferred" and item.get("status") in {"confirmed", "baseline"}:
                errors.append("inferred item cannot enter confirmed baseline")
    if label == "industry_insight":
        for item in root.get("industry_recommendations", []) or []:
            if item.get("status") in {"recommended_not_confirmed", "question_only"} and item.get("can_be_confirmed_requirement") is True:
                errors.append(f"{item.get('recommendation_id')}: unconfirmed recommendation cannot become requirement")
    if label == "architecture_design":
        for domain in root.get("domains", []) or []:
            did = domain.get("domain_id")
            for key in ["requirement_scope", "industry_scope", "ddd_scope"]:
                if key not in domain:
                    errors.append(f"{did}: missing {key}")
    return errors


def mark_frozen(data: dict[str, Any], label: str, frozen_at: str, confirmation: dict[str, Any]) -> dict[str, Any]:
    data["status"] = "frozen"
    data["frozen_at"] = frozen_at
    data["confirmation"] = {
        "source": "checkpoint/user-confirmation.yaml",
        "status": confirmation.get("status") or confirmation.get("confirmation_status"),
        "confirmed_by": confirmation.get("confirmed_by", "user"),
    }
    root = data.setdefault(label, data.get(label, {}))
    if isinstance(root, dict):
        root["status"] = "frozen"
        root["frozen_at"] = frozen_at
    return data


def walk_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_dicts(child)


def find_p1_dir(ws: Path, run_id: str) -> Path:
    for rel in [f"runs/{run_id}/p1", f"runs/{run_id}/P1", "p1"]:
        path = ws / rel
        if path.exists():
            return path
    return ws / "p1"


def find_first(folder: Path, names: list[str]) -> Path | None:
    for name in names:
        path = folder / name
        if path.exists():
            return path
    return None


def load_run_id(ws: Path) -> str:
    state = ws / "project-state.yaml"
    if state.exists():
        data = load_yaml(state)
        return data.get("project_state", {}).get("run_id") or data.get("run_id") or "manual-run"
    return "manual-run"


def load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

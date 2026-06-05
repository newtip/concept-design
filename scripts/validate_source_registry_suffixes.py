#!/usr/bin/env python3
"""Validate source_registry IDs with checkpoint suffixes."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from concept_design.traceability import validate_source_registry_suffixes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--file", default="")
    args = parser.parse_args()
    ws = Path(args.workspace)
    files = [Path(args.file)] if args.file else list((ws / "context-packs").glob("*.yaml")) + list((ws / "p3-workspaces").glob("*/source_registry.yaml"))
    errors: list[str] = []
    for file in files:
        path = file if file.is_absolute() else ws / file
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        registry = data.get("source_registry") or data.get("context_pack", {}).get("source_registry", {})
        errors.extend(f"{path}: {error}" for error in validate_source_registry_suffixes(registry))
    if errors:
        print(f"FAILED: source registry suffix validation ({len(errors)} errors)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASSED: source registry suffix validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate parsed/document-ir.yaml before Agent 01 consumes it."""
from __future__ import annotations

import argparse
from pathlib import Path

import yaml


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    args = parser.parse_args()
    ws = Path(args.workspace)
    path = ws / "parsed" / "document-ir.yaml"
    errors: list[str] = []
    if not path.exists():
        errors.append(f"MISSING: {path}")
    else:
        root = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        ir = root.get("document_ir", {})
        blocks = ir.get("blocks", [])
        if not blocks:
            errors.append("document_ir.blocks is empty")
        seen: set[str] = set()
        for block in blocks:
            bid = block.get("block_id")
            if not bid:
                errors.append("block missing block_id")
            elif bid in seen:
                errors.append(f"duplicate block_id: {bid}")
            seen.add(bid)
            if block.get("block_type") not in {"heading", "paragraph", "table"}:
                errors.append(f"{bid}: invalid block_type {block.get('block_type')}")
            if "order" not in block:
                errors.append(f"{bid}: missing order")
            if block.get("block_type") == "table" and not block.get("table_id"):
                errors.append(f"{bid}: table block missing table_id")
    if errors:
        print("FAILED: document-ir validation")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASSED: document-ir validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

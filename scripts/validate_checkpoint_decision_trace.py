#!/usr/bin/env python3
"""Validate checkpoint decision provenance trace metadata."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from concept_design.traceability import validate_checkpoint_decision_trace


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    args = parser.parse_args()
    errors = validate_checkpoint_decision_trace(args.workspace)
    if errors:
        print(f"FAILED: checkpoint decision trace validation ({len(errors)} errors)")
        for error in errors:
            print(f"  - {error}")
        return 1
    print("PASSED: checkpoint decision trace validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

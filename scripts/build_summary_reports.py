#!/usr/bin/env python3
"""Build human checkpoint summary reports."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from concept_design.summary_reports import SummaryReports


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    parser.add_argument("--report", choices=["pre-p2", "p2-checkpoint", "p3-workspaces"], required=True)
    args = parser.parse_args()
    builder = SummaryReports(Path(args.workspace))
    if args.report == "pre-p2":
        path = builder.summarize_pre_p2()
    elif args.report == "p2-checkpoint":
        path = builder.summarize_p2_checkpoint()
    else:
        path = builder.summarize_p3_workspaces()
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

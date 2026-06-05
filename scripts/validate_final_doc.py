#!/usr/bin/env python3
"""Validate final overview-design.md quality and coverage."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml


CHAPTERS = [
    "第 1 章 项目概述",
    "第 2 章 需求与业务分析",
    "第 3 章 领域架构设计",
    "第 4 章 数据模型设计",
    "第 5 章 领域功能设计",
    "第 6 章 跨领域接口与协作",
    "第 7 章 权限设计",
    "第 8 章 DFX 设计",
    "第 9 章 不满足设计",
    "第 10 章 遗留问题",
    "第 11 章 后续建议",
]

PLACEHOLDERS = ["TODO", "待补充", "占位", "本章内容汇总自", "placeholder"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", default="workspace")
    args = parser.parse_args()
    ws = Path(args.workspace)
    doc = ws / "final" / "overview-design.md"
    fdi_path = ws / "final" / "final-document-index.yaml"
    if not fdi_path.exists():
        fdi_path = ws / "final-document-index.yaml"
    errors: list[str] = []
    if not doc.exists():
        errors.append(f"overview-design.md missing: {doc}")
    if not fdi_path.exists():
        errors.append(f"final-document-index.yaml missing: {fdi_path}")
    if errors:
        return fail(errors)
    text = doc.read_text(encoding="utf-8", errors="ignore")
    fdi = yaml.safe_load(fdi_path.read_text(encoding="utf-8")) or {}
    root = fdi.get("final_document_index", fdi)
    passed = {d["domain_id"]: d for d in root.get("passed_domains", [])}
    pending = {d["domain_id"]: d for d in root.get("pending_or_failed_domains", [])}
    for token in PLACEHOLDERS:
        if token in text:
            errors.append(f"final document contains placeholder token: {token}")
    if "P3-WS-DM" in text and re.search(r"P3-WS-DM\d{3}-SD", text):
        errors.append("final document references deprecated subdomain P3 workspace ids")
    if "# 完整版概要设计" not in text and "# 核心域概要设计草案" not in text:
        errors.append("final document missing expected title")
    for did in re.findall(r"\bDM-\d{3}\b", text):
        if did not in passed and did not in pending:
            errors.append(f"document references unknown domain_id {did}")
    for did, domain in passed.items():
        name = str(domain.get("domain_name", ""))
        if name and name not in text:
            errors.append(f"passed domain {did}/{name} missing from final document")
    for chapter in CHAPTERS:
        if chapter not in text:
            errors.append(f"final document missing chapter: {chapter}")
    for required in ["P3 领域输出覆盖矩阵", "需求与决策追踪矩阵", "数据模型", "功能", "接口", "权限", "DFX"]:
        if required not in text:
            errors.append(f"final document missing required content marker: {required}")
    for header in ["source_id", "source_type", "origin_stage", "decision_type", "status", "domain_id", "subdomain_id"]:
        if header not in text:
            errors.append(f"trace matrix missing column {header}")
    stats = root.get("statistics", {})
    for key in ["domain_count", "passed_domain_count"]:
        value = stats.get(key)
        if value is not None and str(value) not in text:
            errors.append(f"statistic {key}={value} not found in final document")
    if errors:
        return fail(errors)
    print("PASSED: final document validation")
    return 0


def fail(errors: list[str]) -> int:
    print(f"FAILED: final document validation ({len(errors)} errors)")
    for error in errors:
        print(f"  - {error}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

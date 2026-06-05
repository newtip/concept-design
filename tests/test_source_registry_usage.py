from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import yaml


FIXTURE = Path(__file__).parent / "fixtures" / "minimal_workspace"


def copy_workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    shutil.copytree(FIXTURE, ws)
    return ws


def run_script(script: str, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run([sys.executable, script, *args], text=True, capture_output=True)
    if ok:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode != 0
    return result


def test_validate_context_pack_accepts_metadata_map(tmp_path):
    ws = copy_workspace(tmp_path)

    run_script("scripts/validate_context_pack.py", "--workspace", str(ws))


def test_validate_context_pack_rejects_legacy_id_arrays(tmp_path):
    ws = copy_workspace(tmp_path)
    path = ws / "context-packs" / "DM-001-context.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["context_pack"]["source_registry"] = {"functions": ["FUNC-001"]}
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    result = run_script("scripts/validate_context_pack.py", "--workspace", str(ws), ok=False)

    assert "source_registry.functions must be metadata object" in result.stdout


def test_validate_context_pack_rejects_mismatched_source_id(tmp_path):
    ws = copy_workspace(tmp_path)
    path = ws / "context-packs" / "DM-001-context.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data["context_pack"]["source_registry"]["FUNC-001"]["source_id"] = "FUNC-999"
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    result = run_script("scripts/validate_context_pack.py", "--workspace", str(ws), ok=False)

    assert "does not match source_id" in result.stdout


def test_build_source_registry_outputs_metadata_map(tmp_path):
    ws = copy_workspace(tmp_path)
    (ws / "baselines").mkdir(exist_ok=True)
    for name in ["business_model.yaml", "industry_insight.yaml", "architecture_design.yaml"]:
        shutil.copy2(ws / "p1" / name, ws / "baselines" / name)

    run_script("scripts/build_source_registry.py", "--workspace", str(ws))

    registry = yaml.safe_load((ws / "baselines" / "source-registry.yaml").read_text(encoding="utf-8"))["source_registry"]
    assert registry["FUNC-001"]["source_type"] == "requirement_fact"
    assert "formal_design" in registry["FUNC-001"]["allowed_usage"]
    assert registry["REC-002"]["source_type"] == "industry_enrichment"
    assert "formal_design" in registry["REC-002"]["forbidden_usage"]
    assert registry["Q-001"]["source_type"] == "open_question"


def test_confirmed_requirement_used_for_formal_design_passes(tmp_path):
    ws = copy_workspace(tmp_path)

    run_script(
        "scripts/validate_schema.py",
        "--workspace",
        str(ws),
        "--file",
        str(ws / "domains" / "DM-001" / "tp-main-domain-functional-design.yaml"),
    )


def test_recommended_not_confirmed_used_for_formal_design_is_rejected(tmp_path):
    ws = copy_workspace(tmp_path)
    design = ws / "domains" / "DM-001" / "tp-main-domain-functional-design.yaml"
    data = yaml.safe_load(design.read_text(encoding="utf-8"))
    data["main_domain_functional_design"]["domain_design_intent"]["source"] = ["REC-002"]
    design.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    result = run_script("scripts/validate_schema.py", "--workspace", str(ws), "--file", str(design), ok=False)

    assert "REC-002" in result.stdout
    assert "formal" in result.stdout


def test_open_question_used_for_formal_design_is_rejected(tmp_path):
    ws = copy_workspace(tmp_path)
    design = ws / "domains" / "DM-001" / "tp-main-domain-functional-design.yaml"
    data = yaml.safe_load(design.read_text(encoding="utf-8"))
    data["main_domain_functional_design"]["domain_product_structure"]["source"] = ["Q-001"]
    design.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    result = run_script("scripts/validate_schema.py", "--workspace", str(ws), "--file", str(design), ok=False)

    assert "Q-001" in result.stdout
    assert "formal" in result.stdout


def test_risk_note_used_for_dfx_passes(tmp_path):
    ws = copy_workspace(tmp_path)
    design = ws / "domains" / "DM-001" / "tp-main-domain-functional-design.yaml"
    data = yaml.safe_load(design.read_text(encoding="utf-8"))
    dfx = data["main_domain_functional_design"]["modules"][0]["dfx_design"]
    dfx["reliability"] = [{"strategy": "Keep draft unchanged after failed submit.", "source": ["RISK-001"]}]
    design.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    run_script("scripts/validate_schema.py", "--workspace", str(ws), "--file", str(design))


def test_unknown_source_id_is_rejected(tmp_path):
    ws = copy_workspace(tmp_path)
    design = ws / "domains" / "DM-001" / "tp-main-domain-functional-design.yaml"
    data = yaml.safe_load(design.read_text(encoding="utf-8"))
    data["main_domain_functional_design"]["modules"][0]["function_design"]["functions"][0]["source"] = ["MISSING-001"]
    design.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")

    result = run_script("scripts/validate_schema.py", "--workspace", str(ws), "--file", str(design), ok=False)

    assert "MISSING-001" in result.stdout
    assert "unknown source_id" in result.stdout

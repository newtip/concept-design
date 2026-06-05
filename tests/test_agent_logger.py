from __future__ import annotations

import json
from pathlib import Path

from concept_design.agent_logger import AgentLogger


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_agent_logger_creates_structured_jsonl(tmp_path):
    logger = AgentLogger(tmp_path)

    record = logger.log_agent_execution(
        agent_name="05-DesignSynthesisAgent",
        domain_id="DM-001",
        stage="p2_running",
        execution_mode="mode_a_sequential",
        prompt="Generate a domain draft.",
        memory_snapshot={"context_pack_file": Path("context-packs/DM-001-context.yaml")},
        output_summary="Draft generated.",
        output_file="domains/DM-001/tp-main-domain-functional-design.yaml",
        source_ids_used=["REQ-001", "IND-001", "REQ-001"],
        included_item_ids=["REQ-001", "EVT-001"],
        excluded_item_ids=["EVT-004"],
        modified_item_ids=["SD-002"],
        added_item_ids=["REQ-005-N"],
        deleted_item_ids=["EVT-004"],
        workspace_id="P3-WS-DM001",
        subdomain_id=None,
    )

    log_file = tmp_path / "logs" / "agent_execution.jsonl"
    assert log_file.exists()
    rows = read_jsonl(log_file)
    assert rows == [record]
    assert rows[0]["timestamp"].endswith("Z")
    assert rows[0]["agent_name"] == "05-DesignSynthesisAgent"
    assert rows[0]["domain_id"] == "DM-001"
    assert rows[0]["stage"] == "p2_running"
    assert rows[0]["execution_mode"] == "mode_a_sequential"
    assert rows[0]["prompt"] == "Generate a domain draft."
    assert rows[0]["memory_snapshot"]["context_pack_file"] == "context-packs/DM-001-context.yaml"
    assert rows[0]["output_summary"] == "Draft generated."
    assert rows[0]["output_file"] == "domains/DM-001/tp-main-domain-functional-design.yaml"
    assert rows[0]["source_ids_used"] == ["IND-001", "REQ-001"]
    assert rows[0]["included_item_ids"] == ["EVT-001", "REQ-001"]
    assert rows[0]["excluded_item_ids"] == ["EVT-004"]
    assert rows[0]["modified_item_ids"] == ["SD-002"]
    assert rows[0]["added_item_ids"] == ["REQ-005-N"]
    assert rows[0]["deleted_item_ids"] == ["EVT-004"]
    assert rows[0]["workspace_id"] == "P3-WS-DM001"
    assert rows[0]["subdomain_id"] is None


def test_agent_logger_appends_multi_agent_multi_step_records(tmp_path):
    logger = AgentLogger(tmp_path)

    logger.log_agent_execution(
        "05-DesignSynthesisAgent",
        "DM-001",
        "context_ready",
        "mode_b_parallel",
        "Start P2.",
        {"internal_step": "run-p2-domain"},
        "started",
        "domains/DM-001/tp-main-domain-functional-design.yaml",
        ["REQ-001"],
    )
    logger.log_agent_execution(
        "P2CheckpointManager",
        "DM-002",
        "draft_generated",
        "mode_b_parallel",
        "Confirm split.",
        {"internal_step": "checkpoint-p2-domains"},
        "confirmed",
        "domains/DM-002/confirmed_design_scope.yaml",
        ["REQ-002"],
    )

    rows = read_jsonl(tmp_path / "logs" / "agent_execution.jsonl")
    assert [row["agent_name"] for row in rows] == ["05-DesignSynthesisAgent", "P2CheckpointManager"]
    assert [row["domain_id"] for row in rows] == ["DM-001", "DM-002"]
    assert [row["memory_snapshot"]["internal_step"] for row in rows] == ["run-p2-domain", "checkpoint-p2-domains"]

# 流水线契约

## 完整流水线

```
P1 需求与领域架构分析
  ├── STAGE_1  Agent 01 需求提炼
  ├── STAGE_2  Agent 02 行业洞察
  └── STAGE_3  Agent 03 DDD 架构设计

CP 需求与领域蓝图确认
  ├── Agent 04 生成 Checkpoint 卡片
  ├── `python -m concept_design checkpoint --workspace workspace`
  ├── 用户确认（硬停；未确认不得冻结）
  ├── `python -m concept_design confirm-checkpoint --workspace workspace --mode <mode>`
  └── `python -m concept_design freeze --workspace workspace`

P2 主领域功能设计
  └── Agent 05 × N（每个主领域独立设计）
      └── Agent 06 Review → Agent 07 Repair → Agent 06 Re-report

P3 文档化输出
  └── Agent 08 汇总生成最终文档
```

## 阶段准入/准出门禁

### P1 准入门禁
- 用户提供了需求文档或需求描述
- workspace 已初始化

### P1 准出门禁
- business_model.yaml 存在且通过质量门
- industry_insight.yaml 存在且通过质量门
- architecture_design.yaml 存在且通过质量门
- 三个 Agent 的 prompt + output 已保存

### CP 准入门禁
- P1 三个 Agent 全部通过

### CP 准出门禁
- 用户明确回复"确认"或提供了修改意见并已落实
- 设计模式已选择
- project-state.yaml phase >= checkpoint_confirmed
- requirement-baseline.yaml 已冻结
- domain-architecture-baseline.yaml 已冻结
- 只有 checkpoint 确认后才允许执行 freeze_baselines.py
- domain-design-index.yaml 只能在冻结后创建

### P2 准出门禁（每个主领域）
- Review status = passed
- 所有 failed issue 已修复或进入 open_issues
- prompt + output + review + repair 已保存

### P2 Access Governance
- P2 Agent 只能读取当前领域 `context-packs/{domain_id}-context.yaml` 和当前领域允许产物。
- P2 Agent 禁止读取 `input/**`、`raw/**`、`p0/**`、`p1/**`、`baselines/**`。
- P2 Agent 禁止读取其他 domain 的完整设计文件；跨域信息只能通过 `related-domain-summaries/*.yaml` 获得。
- P2 Agent 禁止写 `domain-design-index.yaml`、`project-state.yaml`、`p1/**`、`context-packs/**`、`final/**`。
- P2 Review 只能写当前 domain 的 `review-result.yaml`、`review-report.md`、`tp-review-checklist.md`，不得更新 `domain-design-index.yaml`。
- P2 Repair 只能写当前 domain 的设计文件和 `repair-log.yaml`，不得更新 `project-state.yaml` 或 `domain-design-index.yaml`。
- P3 只能读取 `stage=passed` 的正式 domain 设计文件；non-passed domain 只允许读取 exclusion summary。

### P2 Domain State Machine
- `domain.stage` 是 P2 生命周期唯一机器门禁；`domain.status` 只是展示状态。
- 合法主链路为 `pending -> context_ready -> p2_running -> draft_generated -> reviewing -> passed`。
- Review 失败必须进入 `repair_required` 或 `review_failed`，Repair 后必须进入 `rereviewing`，重新 Review passed 后才允许 P3。
- 禁止 `pending -> passed`、`draft_generated -> passed`、`repair_required -> passed`。
- P3 准入必须检查所有 required domain 的 `stage=passed`，不得只检查 `status=passed`。

### P2 Execution Mode Governance
- 默认模式是 `mode_a_sequential`：按 `domains[].sequence` 严格推进，当前 domain 前面的 `required_for_p3=true` domain 必须 `stage=passed`。
- `mode_b_parallel`：所有 `stage=context_ready` 的 domain 可以并行启动，但仍必须通过 DomainStage 和 AccessPolicy。
- `mode_c_anchor`：`is_anchor=true` 的 anchor domain 必须先 passed，非 anchor domain 才能启动；`depends_on` 中的 domain 也必须 passed。
- `p2_execution_mode` 可以来自 `project-state.yaml` 或 `domain-design-index.yaml`，两者都有时以 project-state 为准。
- 任何模式下，non-passed domain 不得被其他 domain 当作正式设计依据读取。

### Source Registry Usage
- Context Pack 中的 `source_registry` 必须是 metadata map，不再允许旧版分类 ID 数组。
- 每个 source 必须包含 `source_id/category/source_type/status/allowed_usage/forbidden_usage`。
- P2 拆分阶段可以读取 context-pack 内的 P1 全量信息，包括行业增强、风险和待澄清问题。
- 正式设计项只能引用 `allowed_usage` 包含 `formal_design` 或 `formal_function` 的 source。
- `recommended_not_confirmed`、`risk_note`、`open_question` 不得伪装成正式需求或正式功能；它们只能用于边界、异常、DFX、风险处理或 open issue。

### P2 Split Checkpoint
- P2 拆分/draft 生成后必须执行 `checkpoint-p2-domains`。
- 用户可在 checkpoint 中删除不合理拆分项、修正模块命名/职责、添加风险或边界备注。
- 确认结果保存为 `workspace/domains/{domain_id}/confirmed_design_scope.yaml`。
- `confirmed_design_scope` 是 P3 / 后续正式设计唯一可用输入；不得读取未确认的 P2 临时拆分结果。
- checkpoint 后仍必须遵守 source_registry usage 约束，增强信息、风险和 open question 不能伪装成正式需求。

### Agent Execution Logging
- P1, P2, and P3 orchestrated agent executions append JSON Lines records to `workspace/logs/agent_execution.jsonl`.
- Each record contains `agent_name`, `domain_id`, `stage`, `execution_mode`, `prompt`, `memory_snapshot`, `source_ids_used`, `output_summary`, and `output_file`.
- Logs are append-only audit artifacts for prompt, memory, output, and source usage analysis.
- Logs do not grant read/write permission and must not bypass ProjectState, DomainStage, DomainScheduler, AccessPolicy, or source_registry gates.

### Numbered Traceability And P3 Workspaces
- All P1/P2 key items must carry stable IDs: `REQ`, `IND`, `RISK`, `BOUND`, `EXC`, `Q`, `DM`, `SD`, `EVT`, `MOD`, `WF`, `API`, `PAGE`, and `P3-WS`.
- `registry/item-registry.yaml` is the global item registry for ID validation and lookup.
- P2 checkpoint feedback must use item IDs for accepted, rejected, modified, and open issue decisions.
- `confirmed_design_scope.yaml` is the numbered scope contract and must retain accepted, rejected, modified, open issue, and source trace IDs.
- Added checkpoint items use `-N`, modified checkpoint items use `-M`, and deleted originals are listed in `deleted_item_ids`.
- `confirmed_scope_package.yaml` is the canonical package for P3 workspace trimming and records accepted, added, modified, and deleted IDs.
- `build-p3-workspaces` creates isolated domain-level `p3-workspaces/{workspace_id}/` packs for accepted domains and their confirmed subdomains.
- Official P3 workspace IDs must be `P3-WS-DMxxx`. `P3-WS-DMxxx-SDxxx` is deprecated and must be rejected by AccessPolicy, output validation, and final assembly.
- Each passed domain must have exactly one official P3 workspace; confirmed subdomains live inside `included_subdomains` and the P3 output `subdomain_designs`.
- Each P3 workspace may load only its manifest, confirmed scope, trimmed context pack, source registry, P2 reference summary, and hard constraints.
- Rejected items and unrelated domain context must not appear in P3 workspace context packs.
- Agent logs must record `included_item_ids`, `excluded_item_ids`, `modified_item_ids`, `workspace_id`, and `subdomain_id` when available.

### P3 准出门禁
- 所有 required 主领域 `stage=passed`
- 最终文档覆盖全部章节
- 不新增任何未确认内容

## 状态文件

`workspace/project-state.yaml`：
```yaml
project_state:
  phase: "new|initialized|p1_complete|checkpoint_created|checkpoint_confirmed|baselines_frozen|context_packs_built|p2_in_progress|p2_complete|p3_prepared"
  run_id: ""
  checkpoint_confirmed: false
  baselines_frozen: false
  context_packs_built: false
  p2_complete: false
  design_mode: "sequential|parallel|anchor"
  history: []
```

`domain-design-index.yaml` 中每个 domain 必须包含：

```yaml
status: "pending|in_progress|review_failed|repairing|passed|deferred|blocked"
stage: "pending|context_ready|p2_running|draft_generated|schema_validated|reviewing|review_failed|repair_required|repairing|rereviewing|passed|human_review_required|deferred|blocked"
last_transition_at: ""
last_transition_reason: ""
review_round: 0
repair_round: 0
context_pack_file: "context-packs/{domain_id}-context.yaml"
design_file: "domains/{domain_id}/{prefix}-main-domain-functional-design.yaml"
review_result_file: "domains/{domain_id}/review-result.yaml"
blocked_reason: ""
deferred_reason: ""
p2_execution_mode: "mode_a_sequential|mode_b_parallel|mode_c_anchor"
sequence: 1
is_anchor: false
depends_on: []
required_for_p3: true
source_registry:
  REQ-001:
    source_id: REQ-001
    category: requirement
    source_type: requirement_fact
    status: confirmed
    allowed_usage: [formal_design, formal_function]
    forbidden_usage: []
```

## Executable Orchestrator Gates

- `init` creates a fresh workspace state.
- `checkpoint` marks P1 complete and creates the CP hard stop.
- `confirm-checkpoint` is the only transition that unlocks baseline freezing.
- `freeze` calls `freeze_baselines.py` only after checkpoint confirmation.
- `build-context-packs` requires frozen baselines.
- `prepare-p3` requires every P2-required domain in `domain-design-index.yaml` to be `passed`.
- `run-p2-domain`, `review-domain`, `repair-domain`, and `prepare-p3` must pass
  `concept_design.access_policy.AccessPolicy` checks before touching files.

## P3 Workspace Execution And Final Assembly

- `build-p3-workspaces` packages each passed domain into one isolated
  domain-level `p3-workspaces/{workspace_id}/` directory.
- `run-p3-workspace` may run only after `prepare-p3` and may read only the
  current workspace package files allowed by `AccessPolicy`.
- `run-p3-workspace` must not generate business design content by script. It
  creates `p3-agent-prompt.md` and `p3-agent-input-summary.yaml`; if no
  `p3-agent-output.yaml` or `--agent-output-file` is present, it returns
  `awaiting_agent_output`.
- P3 workspace outputs must preserve numbered traceability:
  `included_item_ids`, `excluded_item_ids`, `modified_item_ids`,
  `added_item_ids`, and `deleted_item_ids`.
- P3 workspace outputs must use `granularity: domain`, must not include a
  top-level `subdomain_id`, and must include every confirmed subdomain exactly
  once under `subdomain_designs`.
- `validate_p3_workspace_output.py` validates the P3 output structure and
  rejects any deleted ID that appears in included input IDs.
- `assemble-final-design` runs after `prepare-p3` and assembles final artifacts
  from passed domain indexes and validated domain-level `p3-agent-output.yaml`
  files only. Default final coverage is all passed domains unless a domain has
  an explicit `final_exclusion_reason`.
  If any required workspace output is missing or invalid, it writes
  `final/p3-assembly-report.yaml` and does not generate or overwrite
  `final/overview-design.md`.
- `summarize-pre-p2`, `summarize-p2-checkpoint`, and
  `summarize-p3-workspaces` generate human-review summaries under `reports/`
  so confirmed items are not silently dropped between gates.
- `parse_docx.py` must extract DOCX embedded images into `parsed/images/` and
  write `parsed/image-manifest.yaml` so image/flowchart requirements are
  traceable inputs for later Agent inspection.

# Development Rules

This repository is being upgraded from a prompt package into an executable
orchestrator. Keep orchestration rules explicit, testable, and split across
small modules.

## Hard Gates

- Never skip the checkpoint hard stop.
- Never freeze baselines before the checkpoint is explicitly confirmed.
- Checkpoint confirmation must use current-run feedback (`checkpoint/user-feedback.yaml`
  or an explicit `--feedback-file`) and must include matching `run_id`.
- Never let P2 read raw Word files or full baseline documents.
- Never let P2 read `input/**`, `raw/**`, `p0/**`, `p1/**`, `baselines/**`, or another
  domain's full design output.
- Never let P3 read domains whose machine `stage` is not `passed`.
- Never let a domain become `passed` unless its structured review result is
  `passed`.
- Never place all orchestration logic in one large script.

## Implementation Rules

- `concept_design.project_state.ProjectState` is the single gatekeeper for
  phase transitions.
- CLI commands must load `ProjectState`, validate the requested transition,
  then run scripts.
- Existing scripts may remain focused on artifact generation or validation,
  but cross-stage access rules belong in the orchestrator/state layer.
- `concept_design.access_policy.AccessPolicy` is the single gatekeeper for
  stage filesystem reads and writes.
- `concept_design.domain_state.DomainStage` is the only machine gate for each
  domain lifecycle; `status` is display state only.
- P3 admission must require every required domain to have `stage=passed`.
- P2 execution mode is a hard scheduler gate:
  `mode_a_sequential` is default, `mode_b_parallel` allows context-ready domains
  to start independently, and `mode_c_anchor` requires the anchor domain to pass
  before non-anchor domains start.
- No execution mode may bypass `DomainStage` or `AccessPolicy`.
- P2 agents receive context only through `context-packs/{domain_id}-context.yaml`;
  full baselines are frozen truth sources for orchestrator scripts, not direct
  P2 agent input.
- Context packs must expose `source_registry` as a metadata map. P2 may inspect
  full P1 context inside the pack for slicing and risk analysis, but formal
  design items may cite only sources whose `allowed_usage` includes
  `formal_design` or `formal_function`.
- `recommended_not_confirmed`, `risk_note`, and `open_question` sources must not
  be promoted into formal requirements or formal functions.
- After P2 split/draft generation, `checkpoint-p2-domains` must create
  `confirmed_design_scope.yaml`; later P3/formal design inputs must use that
  confirmed scope, not transient split drafts.
- Every orchestrated agent-equivalent execution in P1, P2, and P3 must append
  structured audit records to `logs/agent_execution.jsonl`, including prompt,
  memory snapshot, output summary, stage, execution mode, and source IDs used.
- P3 workspace execution must use `run-p3-workspace` against an isolated
  `p3-workspaces/{workspace_id}/` package and must log numbered inputs,
  excluded/deleted IDs, modified IDs, added IDs, workspace ID, domain ID, and
  subdomain ID.
- Final assembly must use `assemble-final-design` after `prepare-p3`; it must
  build from passed domain indexes and validated `p3-agent-output.yaml`
  artifacts, not raw P1/P2 candidates.
- `run-p3-workspace` must not fabricate P3 business design. Without a real
  Agent output it may only generate `p3-agent-prompt.md` and
  `p3-agent-input-summary.yaml`, then return `awaiting_agent_output`.
- `assemble-final-design` must fail and write `final/p3-assembly-report.yaml`
  when any required P3 workspace output is missing or invalid; it must not
  create or overwrite `final/overview-design.md` in that state.
- Stage summaries are human-review guardrails: use `summarize-pre-p2`,
  `summarize-p2-checkpoint`, and `summarize-p3-workspaces` to expose what will
  move across the next gate.
- Agent execution logs are audit artifacts only; they must not bypass
  `ProjectState`, `DomainStage`, `DomainScheduler`, `AccessPolicy`, or
  `source_registry` usage gates.
- DOCX parsing must preserve image traceability by extracting embedded
  `word/media/*` assets into `parsed/images/` and writing
  `parsed/image-manifest.yaml`.
- P1/P2 key facts, enrichments, risks, boundaries, exceptions, questions,
  domains, subdomains, events, modules, workflows, interfaces, pages, and P3
  workspaces must be referenced by stable item IDs.
- P2 checkpoint feedback must be item-ID based: accepted, rejected, modified,
  and open issue decisions are recorded into `confirmed_design_scope.yaml`.
- Checkpoint item variants use suffixes: added items must use `-N`, modified
  items must use `-M`, and deleted original IDs must be recorded in
  `deleted_item_ids`.
- `confirmed_scope_package.yaml` is the canonical P3 trimming input; P3
  workspaces may load accepted, added, and modified IDs only.
- P3 work must use isolated `p3-workspaces/{workspace_id}/` packs trimmed by
  accepted item IDs; rejected items and unrelated subdomain context must not
  appear in P3 workspace context packs.
- P3 workspace granularity is domain-level only. Official workspace IDs must be
  `P3-WS-DMxxx`; `P3-WS-DMxxx-SDxxx` is deprecated and must be rejected by
  packaging, access, validation, and final assembly.
- A domain-level P3 workspace may contain multiple confirmed subdomains inside
  `included_subdomains` and `subdomain_designs`, but there must be exactly one
  official P3 workspace per passed domain.
- Final assembly defaults to full coverage of all `stage=passed` domains unless
  a domain has an explicit `final_exclusion_reason`; it must generate a readable
  overview, not placeholder chapter text.
- Tests must cover every new gate before a stage is considered complete.

## Release Hygiene

- Do not include runtime `workspace/` outputs in the skill package.
- Keep generated project state inside the selected workspace.
- Run `pytest` after every implementation stage.

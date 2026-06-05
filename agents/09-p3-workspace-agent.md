# 09 P3 Workspace Agent

## Purpose

Generate detailed P3 concept design for one isolated subdomain workspace.

## Inputs

Only read the current workspace files:

- `workspace-manifest.yaml`
- `confirmed_scope_package.yaml`
- `confirmed_design_scope.yaml`
- `context-pack.yaml`
- `source_registry.yaml`
- `p2-reference.yaml`
- `hard-constraints.yaml`

## Output

- `p3-agent-output.yaml`
- Optional explanatory notes in `p3-agent-output.md`

## Hard Rules

- Do not read raw input, P0/P1/P2 full artifacts, baselines, or other P3 workspaces.
- Formal design may cite only sources allowed for `formal_design` or
  `formal_function`.
- `recommended_not_confirmed`, `risk_note`, `boundary_note`, and
  `open_question` are reference-only unless explicitly confirmed by checkpoint.
- Deleted, rejected, or excluded IDs must not appear in formal function, page,
  interface, workflow, or data-model design.

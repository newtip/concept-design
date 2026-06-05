# concept-design executable orchestrator

This repository turns the concept-design prompt package into a deterministic
orchestrator with phase gates, domain gates, access policy checks, numbered
checkpoint packages, isolated P3 workspaces, and structured agent audit logs.

## Runtime Dependencies

- Python 3.11+
- PyYAML
- python-docx
- pytest

`scripts/parse_docx.py` uses `python-docx` first so Chinese paragraphs and
tables are extracted correctly, then reads the DOCX zip package to extract
embedded images into `parsed/images/`. If `python-docx` cannot open a minimal
synthetic fixture, the parser falls back to direct DOCX zip parsing.

Optional dependencies may be useful for downstream Agent execution, but the
current deterministic test suite only requires the dependencies above.

## Core Commands

```bash
python -m concept_design init --workspace <workspace>
python -m concept_design checkpoint --workspace <workspace>
python -m concept_design confirm-checkpoint --workspace <workspace> --mode sequential --feedback-file checkpoint/user-feedback.yaml
python -m concept_design freeze --workspace <workspace>
python -m concept_design build-context-packs --workspace <workspace>

python -m concept_design run-p2-domain --workspace <workspace> --domain-id DM-001
python -m concept_design review-domain --workspace <workspace> --domain-id DM-001
python -m concept_design repair-domain --workspace <workspace> --domain-id DM-001

python -m concept_design checkpoint-p2-domains --workspace <workspace>
python -m concept_design build-p3-workspaces --workspace <workspace>
python -m concept_design prepare-p3 --workspace <workspace>
python -m concept_design summarize-p3-workspaces --workspace <workspace>
python -m concept_design run-p3-workspace --workspace <workspace> --p3-workspace-id P3-WS-DM001
python -m concept_design run-p3-workspace --workspace <workspace> --domain-id DM-001
python -m concept_design run-p3-workspace --workspace <workspace> --p3-workspace-id P3-WS-DM001 --agent-output-file <agent-output.yaml>
python -m concept_design assemble-final-design --workspace <workspace>
```

`run-p3-workspace` never invents P3 business content. If
`p3-agent-output.yaml` is missing and no `--agent-output-file` is provided, it
generates `p3-agent-prompt.md` plus `p3-agent-input-summary.yaml` and reports
`awaiting_agent_output`.

`confirm-checkpoint` is hard-gated by `checkpoint/user-feedback.yaml` for the
current `project-state.run_id`. The file must exist and record at least:

- `run_id`
- `status` (must be `confirmed` or `approved`)
- `confirmed_by` (optional, defaulted to CLI user)

Older checkpoint confirmation files from previous runs are rejected.

P3 workspace IDs are domain-grained (`P3-WS-DM001`). Deprecated subdomain
workspace IDs such as `P3-WS-DM001-SD001` are rejected by the runner,
validators, and access policy.

Stage summary commands:

```bash
python -m concept_design summarize-pre-p2 --workspace <workspace>
python -m concept_design summarize-p2-checkpoint --workspace <workspace>
python -m concept_design summarize-p3-workspaces --workspace <workspace>
```

## Document Parsing

```bash
python scripts/parse_docx.py --input requirements.docx --workspace <workspace>
```

Outputs:

- `parsed/document-ir.yaml`
- `parsed/document.md`
- `parsed/tables/*.yaml`
- `parsed/image-manifest.yaml`
- `parsed/images/IMG-*.{png,jpg,...}`

If a requirement flow is represented by an image, the image is extracted and
listed in `image-manifest.yaml` so an Agent can inspect or reason over it later.

## Validation

```bash
python -m pytest -q
python -m compileall -q concept_design scripts tests
python scripts/validate_p3_workspace_output.py --workspace <workspace>
python scripts/validate_p3_assembly.py --workspace <workspace>
python scripts/validate_checkpoint_decision_trace.py --workspace <workspace>
python scripts/validate_source_registry_suffixes.py --workspace <workspace>
```

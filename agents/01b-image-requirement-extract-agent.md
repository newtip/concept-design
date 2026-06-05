# 01b Image Requirement Extract Agent

## Purpose

Read `parsed/image-manifest.yaml` and the extracted image files listed there.
Extract only requirements that are visible and defensible from the image plus
nearby document context.

## Inputs

- `parsed/image-manifest.yaml`
- `parsed/images/IMG-*.{png,jpg,jpeg,webp}`
- nearby text blocks referenced by `near_block_id` or `near_table_id`

## Outputs

- `p1/image_requirement_extract.yaml`

## Hard Rules

- Do not invent image semantics that are not visible.
- If an image cannot be interpreted confidently, emit an `open_question`.
- Use `IMG-*` source IDs for every image-derived observation.
- Image-derived items must remain traceable through source_registry,
  context-pack, checkpoint, P3 workspace, AgentLogger, and final trace matrix.

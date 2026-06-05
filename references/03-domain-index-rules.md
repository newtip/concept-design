# 领域设计索引规则

## 定位

`domain-design-index.yaml` 是 P2 的单一真相源，类似 `narrations.ts` 控制音频合成。

## 格式

```yaml
project_name: ""
run_id: ""

truth_sources:
  requirement_baseline: "workspace/baselines/requirement-baseline.yaml"
  domain_architecture_baseline: "workspace/baselines/domain-architecture-baseline.yaml"

design_mode:
  mode: "sequential|parallel|anchor_first"
  anchor_enabled: false
  anchor_domain_id: ""
  anchor_status: "not_required|pending|passed|failed"

main_domains:
  - domain_id: "DM-001"
    domain_name: ""
    domain_prefix: ""
    domain_type: "core|supporting|generic"
    sub_domains: []
    source_contexts: []
    source_events: []
    source_functions: []
    output_file: "workspace/domains/domain_xxx/xxx-main-domain-functional-design.yaml"
    prompt_file: "workspace/runs/{run_id}/domains/domain_xxx/prompt.md"
    review_file: "workspace/runs/{run_id}/domains/domain_xxx/review-checklist.md"
    repair_file: "workspace/runs/{run_id}/domains/domain_xxx/repair-log.md"
    status: "pending|designing|reviewing|repairing|passed|blocked"
    review_status: "missing|pending|in_progress|passed|failed"
    review_file: "workspace/runs/{run_id}/domains/domain_xxx/review-checklist.md"
    repair_file: "workspace/runs/{run_id}/domains/domain_xxx/repair-log.md"
    rereport_file: "workspace/runs/{run_id}/domains/domain_xxx/rereport.md"
    blocking_issues: []
    design_level: "full|reference_only|platform_capability"
    design_level_reason: ""
```

## 硬规则

```text
1. 不在 domain-design-index.yaml 中的主领域，不允许被设计。
2. 每个主领域只能写自己的 output_file。
3. 每个主领域必须有独立 prefix。
4. 每个主领域必须有独立 review_file 和 repair_file。
5. status 不为 passed 的主领域，不允许进入最终文档。
6. P3 只能从 domain-design-index.yaml 指向的 passed 产物读取内容。
7. 如果设计中发现领域边界问题，写入 open_issues，不改 index。
8. P2 每个主领域设计完成后，必须立即更新 status 和 review_status。
9. design_level=reference_only 或 platform_capability 的领域不进入 P2，但 P3 第3章需列出。
10. 必须有 design_level_reason 解释为何不进入完整 P2。
```

## status 生命周期

```
pending → designing → reviewing → repairing → passed
                     ↓              ↓
                   blocked         failed → repairing
```

## review_status 与 P3 准入

| review_status | 含义 | P3 行为 |
|--------------|------|---------|
| missing | 无 Review 文件 | 禁止进入 P3 |
| pending | 已生成待 Review | 禁止进入 P3 |
| in_progress | Review 进行中 | 禁止进入 P3 |
| passed | Review 通过 | 可进入 P3 |
| failed | Review 未通过 | 禁止进入 P3，需 Repair |

**P3 Writer 的准入条件：review_status=passed 且 status=passed。**

## 统计字段（P3 前生成）

```yaml
statistics:
  total_domains: 10
  core_domains: 5
  supporting_domains: 2
  generic_domains: 3
  designed_domains: 5          # design_level=full
  passed_domains: 0            # status=passed
  context_count: 11            # 来自 baseline
  aggregate_count: 11          # 来自 baseline
  event_count: 17              # 来自 baseline
```
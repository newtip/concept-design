# {{domain_name}} Review Checklist

```yaml
review_meta:
  domain_id: "{{domain_id}}"
  status: "{{passed|failed}}"
  reviewed_modules: []
  issue_count: 0
  blocker_count: 0
  source_check_count: 0
  generic_issue_count: 0
```

## 1. Review 结论

status: {{passed|failed}}
review_date: {{date}}
reviewer: "06-review-agent"

## 2. 输入确认

| 输入 | 是否存在 | 说明 |
|---|---|---|
| context-pack | {{yes/no}} | 必须包含 requirement_context / industry_context / domain_architecture_context |
| requirement_context | {{yes/no}} | P2 正式设计的需求事实来源 |
| industry_context | {{yes/no}} | 只能作为风险、边界和决策提醒 |
| domain_architecture_context | {{yes/no}} | Context、Aggregate、Owner 边界来源 |

## 3. 模块逐项检查

| module_id | 模块 | 模块关系 | 数据模型 | 功能 | 流程 | 页面 | 接口 | DFX | 遗留问题 |
|---|---|---|---|---|---|---|---|---|---|
| {{module_id}} | {{module_name}} | {{pass/fail}} | {{pass/fail}} | {{pass/fail}} | {{pass/fail}} | {{pass/fail}} | {{pass/fail}} | {{pass/fail}} | {{pass/fail}} |

## 4. Source ID 检查

| 设计项 | source_id | 是否存在于 source_registry | 结论 | Evidence |
|---|---|---|---|---|
| {{yaml_path}} | {{source_id}} | {{yes/no}} | {{pass/fail}} | {{evidence}} |

## 5. 泛化设计检查

| 位置 | 泛化词 | 问题 | 修复建议 | Evidence |
|---|---|---|---|---|
| {{yaml_path}} | {{term}} | {{problem}} | {{fix}} | {{evidence}} |

## 6. 问题清单

| Issue ID | Severity | YAML Path | Problem | Evidence | Required Fix |
|---|---|---|---|---|---|
| {{ISSUE-001}} | {{blocker/critical/major/minor}} | {{path}} | {{problem}} | {{evidence}} | {{fix}} |

## 7. Re-report

是否允许进入 P3：{{yes/no}}

如 status=failed，必须列出 blocker/critical issue；修复后必须重新 Review。

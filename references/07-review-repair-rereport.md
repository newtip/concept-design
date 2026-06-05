# Review / Repair / Re-report 闭环

## 铁律

```text
禁止: 设计 Agent 自评通过
禁止: Review Agent 只写整体评价不逐项检查
禁止: Review 后不修复直接汇报给用户
禁止: 修复后不重新 Review
```

## Review Agent 检查维度（14 项）

```text
 1. 是否只基于双基线设计？
 2. 是否没有重新提取需求？
 3. 是否没有重新做行业增强？
 4. 是否没有重新做 DDD？
 5. 是否覆盖当前主领域所有子领域/模块？
 6. 是否先完成模块关系设计？
 7. 每个模块是否有 data_model_design？
 8. 数据模型是否遵守 Owner/Reference/Snapshot/Projection/ACL？
 9. 同名对象跨领域是否处理正确？
10. 跨领域交互是否通过契约？
11. 页面是否说明样式、数据、交互、权限？
12. 接口是否说明调用方向、失败处理和事件？
13. 不满足设计是否明确？
14. DFX 是否落到模块风险？
15. 遗留问题是否保留？
16. traceability 是否完整？
```

## Review 输出格式

```markdown
# {主领域} Review Checklist

## 1. 结论
status: passed / failed

## 2. 检查摘要

## 3. 问题清单

| Issue ID | Severity | Slice Type | File/YAML Path | Problem | Evidence | Required Fix | Need Human Review |

## 4. 必须修复项

## 5. 可延后项

## 6. 是否触发人工审核

以下变更需要人工审核：
- 领域边界修改
- 共享对象 Owner 变更
- 聚合根变更
- 跨领域契约变更
```

## Issue 类型

```
module_relation    data_model    function    workflow
page               interface     unsupported dfx
open_issue         cross_domain_contract
traceability       domain_boundary
```

## 最小切片修复

修复必须定位到五层：

```
domain → module → section → yaml_path → issue_id
```

示例：

```
Issue: 订单创建模块把 CustomerProfile 放入 owned_objects
Slice: domain=order, module=order_create, section=data_model_design.owned_objects
Fix:
  1. 从 owned_objects 删除 CustomerProfile
  2. 在 referenced_objects 增加 customerId
  3. 在 snapshot_objects 增加 BuyerSnapshot
  4. 在 cross_domain_data_usage 增加 CustomerProfile 的 usage_mode
  5. 更新 traceability
```

## 执行方式（按能力降级）

1. **Agent Teams（最优）**：开独立 reviewer agent
2. **subAgent（次优）**：开 subagent 走同样流程
3. **自检（兜底）**：严格逐项核查，不允许目测放行
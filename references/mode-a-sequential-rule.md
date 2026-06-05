# 模式 A 顺序执行铁律

## 规则

当用户选择模式 A（sequential），Orchestrator 必须严格遵守：

```
域1 设计 → 域1 Review passed → 域2 设计 → 域2 Review passed → ... → 域N
```

## 绝对禁止

**绝对禁止**在任何情况下对多个域使用 delegate_task tasks=[] 并行执行，即使"剩余域看起来独立"也不允许。

用户选择模式 A 意味着他们要逐个验收每个域的设计。并行执行直接违反用户意志。

## 违规案例（2026-06-03）

- Orchestrator 在 D01/D02 passed 后对 D03/D04/D05 使用 `delegate_task tasks=[D03, D04, D05]` 同时并行三个域
- 用户质问："我选择的策略A不是要求一个个依次执行吗"
- 根因：Orchestrator 为"效率"自行将顺序模式改为并行
- 代价：D03/D04/D05 全部失败，浪费用户时间，损害信任

## 正确执行方式

```python
# ✅ 正确 - 严格顺序
delegate_task(goal="D03 设计")
# 等待完成 + Review
delegate_task(goal="D04 设计")  
# 等待完成 + Review
delegate_task(goal="D05 设计")

# ❌ 错误 - 并行
delegate_task(tasks=[
    {"goal": "D03 设计"},
    {"goal": "D04 设计"},
    {"goal": "D05 设计"},
])
```

## 唯一例外

仅当用户在选择模式时明确说"并行"或"一起跑"时，才允许并行。用户在 CP 阶段的选择是唯一权威。

# 治理规则

## Skill 定位

本 Skill 是**软件概要设计驾驭系统**，不是一次性文档生成器。

目标：通过可控流水线，把模糊需求转化为可追踪、可 Review、可修复、可汇总的最终概设文档。

## 核心原则

1. **状态驱动，不线性**：每个阶段有准入/准出门禁，失败可路由到上游修复。
2. **真相源唯一**：P2/P3 只能读双基线 + domain-design-index，不得绕过。
3. **领域隔离**：每个主领域独立目录、独立前缀、独立 Review/Repair。
4. **数据模型嵌入**：不设独立全局数据模型阶段，每个模块内完成数据模型设计。
5. **质量闭环**：每个产物必须 Review → Repair → Re-report。
6. **完整性不造假**：缺的标注 open_issues，不编造。

## 角色与职责

| 角色 | 职责 |
|------|------|
| Orchestrator (Agent 00) | 状态推进、调用各 Agent、保存 prompt/output、等待 Checkpoint |
| Agent 01 | 需求提炼 — 只提取需求事实 |
| Agent 02 | 行业洞察 — 补充经验/风险/决策待办 |
| Agent 03 | DDD 架构 — 事件流→领域→Context→聚合 |
| Agent 04 | Checkpoint 卡片生成 |
| Agent 05 | 主领域功能设计 |
| Agent 06 | Review |
| Agent 07 | 最小切片修复 |
| Agent 08 | 文档输出 |

## 硬约束

```text
1. Agent 01 不得做行业增强、DDD、数据模型。
2. Agent 02 不得把建议写成已确认需求。
3. Agent 03 不得做功能详细设计、页面设计。
4. Agent 05 只能基于双基线设计，不得重新提取需求。
5. Agent 06 必须独立于设计 Agent 执行。
6. Agent 07 只修复 Review 指定的 issue，不做全量重写。
7. Agent 08 只汇总 passed 产物，不新增内容。
```
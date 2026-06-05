# Checkpoint：需求与领域蓝图确认

> 以下由 Agent 自动填充，向用户展示前必须删除本行和所有注释。
> 🔴 主卡硬约束：不超过 4 个小节。DD01-DD10 和 Q01-Q12 进 appendix，不放主卡。

我已经完成需求与领域架构分析。以下是决策摘要。

## 1. 当前结论

| 维度 | 数值 | 说明 |
|------|------|------|
| 需求成熟度 | {{maturity_score}}/100 | {{maturity_level}} |
| 建议设计模式 | 模式 {{mode}} | {{mode_reason}} |
| 推荐锚点 | {{anchor_domain}} | {{anchor_reason}} |

## 2. 最需要你确认的 Top 3 问题

| # | 问题 | 推荐选择 | 影响 |
|---|------|---------|------|
| 1 | {{top_q_1}} | {{top_q_1_recommendation}} | {{top_q_1_impact}} |
| 2 | {{top_q_2}} | {{top_q_2_recommendation}} | {{top_q_2_impact}} |
| 3 | {{top_q_3}} | {{top_q_3_recommendation}} | {{top_q_3_impact}} |

> 完整决策清单（DD01-DD{{dd_count}}）和待确认问题（Q01-Q{{q_count}}）详见 appendix/。

## 3. 后续设计模式

| 模式 | 说明 | 推荐 |
|------|------|------|
| A 顺序 | 逐个主领域完整设计→Review→通过后再进下一个 | 稳，首次使用推荐 |
| B 并行 | 所有核心域同时启动，统一 Review | 快，需领域边界清晰 |
| C 锚点先行 | 先完整设计 1 个样板，确认粒度后再展开其余 | 先慢后快，适合对齐标准 |

> 推荐：**模式 {{mode}}**，因为 {{reason}}

## 4. 请回复

```
确认，后续选择 {{mode}}{{#if mode C}}，样板领域：{{anchor_domain}}{{/if}}
```

或指出需要修改的部分：
```
需求问题：...
领域问题：...
```

---

📎 **附录（可选看）**
- `appendix/full-decision-list.md` — 完整决策清单（DD01-DD{{dd_count}}）
- `appendix/full-open-questions.md` — 完整待确认问题（Q01-Q{{q_count}}）
- `01-requirement-card.md` — 需求确认卡（≤1.5 页）
- `02-domain-card.md` — 领域确认卡（≤1.5 页）

# Checkpoint 规则

## 定位

Checkpoint 是 P1→P2 之间的唯一硬停节点。用户在这一个节点确认需求和领域蓝图后，后续 P2/P3 尽量不打断。

## 必须产出的文件

```
workspace/checkpoint/
├── 00-checkpoint-summary.md
├── 01-requirement-card.md
├── 02-domain-card.md
└── appendix/
    ├── business_model.yaml
    ├── industry_insight.yaml
    └── architecture_design.yaml
```

## 用户默认只看三份文件

- `00-checkpoint-summary.md` — 总览 + 模式选择
- `01-requirement-card.md` — 需求确认卡
- `02-domain-card.md` — 领域确认卡

完整产物放在 appendix，不默认展示给用户。

## 确认卡格式约束

### 🔴 主卡硬约束（必须执行）

```text
1. 确认卡不超过 6 个小节，超过必须压缩
2. 任一表格超过 6 行，只保留高风险/高影响项，其余删除
3. 待确认问题超过 5 个，只展示 Top 5，其余进入 appendix
4. 禁止输出"完整清单"，必须输出"详见 appendix"
5. DD01-DD10 完整决策清单 → appendix/full-decision-list.md
6. Q01-Q12 完整待确认问题 → appendix/full-open-questions.md
```

### 两层结构

**用户必看（主卡）**：
- `00-checkpoint-summary.md` — 4 块：当前结论 / Top 3 问题 / 设计模式 / 请回复
- `01-requirement-card.md` — ≤1.5 页
- `02-domain-card.md` — ≤1.5 页

**用户选看（appendix）**：
- `appendix/full-decision-list.md` — 完整决策清单
- `appendix/full-open-questions.md` — 完整待确认问题
- `appendix/business_model.yaml`
- `appendix/industry_insight.yaml`
- `appendix/architecture_design.yaml`

### 00-checkpoint-summary.md（主卡，仅 4 块）
```markdown
# Checkpoint：需求与领域蓝图确认

## 1. 当前结论
| 维度 | 数值 | 说明 |
| 需求成熟度 | X/100 | 水平 |
| 建议设计模式 | A/B/C | 原因 |
| 推荐锚点 | XX域 | 原因 |

## 2. 最需要你确认的 Top 3 问题
| # | 问题 | 推荐选择 | 影响 |
只展示影响最大的 3 个

## 3. 后续设计模式
A 顺序 / B 并行 / C 锚点先行（表格 + 推荐）

## 4. 请回复
确认 / 修改需求 / 修改领域 / 修改设计模式
```

## 用户确认后的动作

1. 生成 `requirement-baseline.yaml`（只含已确认的需求事实）
2. 生成 `domain-architecture-baseline.yaml`（只含已确认的领域架构）
3. 创建 `domain-design-index.yaml`
4. 记录用户选择的 design_mode
5. 更新 `project-state.yaml`
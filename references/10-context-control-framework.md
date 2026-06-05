# 上下文控制框架（Context Control Framework）

## 一、核心原则

> 减少幻觉的关键，不是给模型更多上下文，而是给模型**经过裁剪、标源、冻结、带边界的上下文包**。

每个 Agent 不自己读文件。Orchestrator 为每个 Agent 构造一个明确的 **Context Pack**。

## 二、上下文四层模型

```
L0  原始材料层        → 只给 Agent 01 使用
L1  结构化事实层      → 01/02/03 产出，放 appendix
L2  用户确认基线层    → CP 通过后冻结，P2/P3 只读此层
L3  当前任务上下文包  → 每个 Agent 只吃自己的 Context Pack
```

| 层级 | 内容 | 谁使用 | 谁不能读 |
|------|------|--------|---------|
| L0 | 用户原始需求、上传文档 | Agent 01 | Agent 02~08 |
| L1 | business_model / industry_insight / architecture_design | appendix | P2/P3 Agent |
| L2 | requirement-baseline / domain-architecture-baseline | P2/P3 Agent | — |
| L3 | context-packs/domain_xxx_context.yaml | 对应 Agent | 其他 Agent |

**关键原则：阶段越靠后，越不能读取原始需求全文。否则后面 Agent 会重新解释用户需求，产生漂移。**

## 三、Context Pack 标准格式

```yaml
context_pack:
  meta:
    context_pack_id: ""
    run_id: ""
    agent_name: ""
    stage: ""
    generated_from:
      requirement_baseline: ""
      domain_architecture_baseline: ""
    baseline_version: "v1.0"
    generated_at: ""
    status: "frozen"

  task:
    goal: ""
    current_domain_id: ""
    current_domain_name: ""
    allowed_output: ""

  allowed_sources: []       # 白名单
  forbidden_sources: []     # 黑名单
  forbidden_actions: []     # 禁止行为

  current_domain:
    domain_id: ""
    domain_name: ""
    responsibility: ""
    out_of_scope: []
    modules: []
    owned_objects: []
    referenced_objects: []
    events: []
    functions: []

  related_domain_summaries:   # 只给摘要！
    - domain_name: ""
      owner_objects: []
      exposed_interfaces: []
      exposed_events: []
      allowed_usage: []       # 当前领域允许的使用方式
      forbidden_usage: []     # 当前领域禁止的操作

  context_items:               # 不再叫 confirmed_items，避免误导 Agent
    - id: ""
      content: ""
      type: "confirmed_requirement|industry_recommendation|confirmed_assumption|open_question"
      source: ""
      status: ""

  negative_context:            # 明确不能假设什么
    out_of_scope: []
    forbidden_inference:
      - "不得假设存在审批流程"
      - "不得假设存在多租户"
    unavailable_information:
      - "未确认是否支持 X"

  decision_boundary:
    can_decide: []             # Agent 可以自行决定
    cannot_decide: []          # Agent 不能决定，必须上报

  output_requirements:
    required_schema: ""
    require_source_ids: true
    require_open_issue_when_missing_context: true
```

## 四、每个 Agent 的 Allowlist / Denylist

### Agent 01 — 需求提炼

| Allow（允许读取） | Deny（禁止读取） |
|---|---|
| 原始需求全文 | DDD 产物 |
| 上传文档 | 设计产物 |

### Agent 02 — 行业洞察

| Allow | Deny |
|---|---|
| business_model.yaml | 原始需求全文 |
| project_archetype | DDD 产物 |

### Agent 03 — DDD 架构

| Allow | Deny |
|---|---|
| business_model.yaml | 原始需求全文 |
| industry_insight.yaml | 页面/接口设计 |

### Agent 05 — 主领域功能设计

| Allow | Deny |
|---|---|
| requirement-baseline.yaml | 原始需求全文 |
| domain-architecture-baseline.yaml | 未确认行业建议全文 |
| 当前领域 context-pack.yaml | 其他主领域完整设计文件 |
| 当前主领域已有产物 | 其他主领域内部数据模型 |
| 相关领域只读摘要 | 未通过 Review 的产物 |
| 全局设计约束 | 已废弃旧版 baseline |

**禁止行为：**
1. 不重新提取需求
2. 不重新做行业增强
3. 不重新划分领域
4. 不修改领域边界
5. 不修改共享对象 Owner
6. 不把其他领域对象放进 owned_objects

### Agent 06 — Review

| Allow | Deny |
|---|---|
| 当前领域设计产物 | 设计 Agent 的推理过程 |
| requirement-baseline.yaml | 设计 Agent 的自评结论 |
| domain-architecture-baseline.yaml | 无关领域完整产物 |
| 当前领域 context-pack.yaml | — |
| Review checklist | — |

### Agent 08 — Writer

| Allow | Deny |
|---|---|
| domain-design-index.yaml | 原始需求全文 |
| 所有 status=passed 的产物 | failed/draft 产物 |
| 双基线 | 中间推理材料 |

## 五、上下文预算（按阶段限制）

| 阶段 | 最大函数 | 最大事件 | 最大相关领域 | 是否含原始需求 |
|------|---------|---------|------------|--------------|
| Agent 01 | — | — | — | 是 |
| Agent 02 | 50 | 30 | — | 否 |
| Agent 03 | 50 | 30 | — | 否 |
| Agent 05 | 20 | 20 | 5 | 否 |
| Agent 06 | 全量 | 全量 | 当前+相关 | 否 |
| Agent 08 | 全量（只读 passed） | 全量 | 全部 passed | 否 |

## 六、每条数据必须标注类型

Agent 必须区分：

| 类型 | 含义 | 可以做什么 |
|------|------|-----------|
| `confirmed_requirement` | 用户确认的需求 | 进入正式设计 |
| `confirmed_assumption` | 已确认的假设 | 作为默认设计依据 |
| `industry_recommendation` | 行业建议（未确认）| 只能进入建议或遗留问题 |
| `open_question` | 待确认问题 | 不能写成确定设计 |

## 七、负上下文（Negative Context）

不要只告诉 Agent 有什么，也要告诉它**没有什么、不能假设什么、不能设计什么**：

```yaml
negative_context:
  out_of_scope:
    - "本次不设计支付流水明细"
    - "本次不设计商品主数据维护"
  forbidden_inference:
    - "不得假设存在审批流程"
    - "不得假设存在多租户"
    - "不得假设库存由本系统维护"
  unavailable_information:
    - "未确认是否支持跨组织代下单"
    - "未确认是否支持订单修改商品明细"
```

## 八、input_context_ack（Agent 内部校验，不作为顶层输出）

**input_context_ack 不是 YAML 顶层字段。最终产品顶层只能是 `main_domain_functional_design`。**

input_context_ack 结果必须写入 `main_domain_functional_design.quality_checks.context_ack`。
如果 Orchestrator 需要独立留痕，可另存为 `runs/{run_id}/{domain}/context_ack.yaml`。

如果最终输出同时出现 `input_context_ack` 和 `main_domain_functional_design` 两个顶层字段，Review Agent 必须判定为 schema blocker。

```yaml
input_context_ack:
  agent_name: "05-main-domain-functional-design-agent"
  current_task: "设计订单领域"
  allowed_context_used:
    - "requirement-baseline.yaml"
    - "domain-architecture-baseline.yaml"
    - "context-packs/domain_order_context.yaml"
  forbidden_context_not_used:
    - "用户原始需求全文"
    - "未确认行业建议"
    - "其他领域完整设计"
  design_scope:
    current_domain: "订单领域"
    allowed_modules: ["订单创建", "订单取消", "订单查询"]
  cannot_do:
    - "不重新划分领域"
    - "不维护客户主数据"
    - "不设计支付流水"
```

## 九、Source ID 强制追溯

所有设计项必须有 `source_id`。没有来源 = 不能进入正式设计：

```yaml
function_design:
  functions:
    - function_name: "创建订单"
      source: ["FUNC-001", "EVT-001", "CTX-ORDER"]
```

如果无法追溯来源：
```yaml
open_issues:
  - issue: "需要订单草稿功能，但需求基线未确认"
    impact: "影响订单创建页面"
    blocking: false
    default_strategy: "暂不纳入正式设计"
```

## 十、上下文不足时强制"不设计"

```text
当上下文不足以支撑设计时，不允许 Agent 自行补完设计。
必须输出 open_issue，并说明缺少什么信息。
```

## 十一、上下文版本与冻结

```yaml
context_meta:
  baseline_version: "v1.0"
  source_hash:
    requirement_baseline: "sha256:xxx"
    domain_architecture_baseline: "sha256:yyy"
  status: "frozen"
```

Agent 必须遵守：只使用 `status=frozen` 的基线。发现 hash 不一致 → 停止设计。

## 十二、当前领域 vs 相关领域 vs 无关领域

| 范围 | 给什么 | 不给什么 |
|------|--------|---------|
| **当前领域** | 完整上下文 | — |
| **相关领域** | 只读摘要（Owner对象 + 开放接口 + 允许使用方式 + 禁止操作） | 完整模块设计、页面设计、内部数据模型 |
| **无关领域** | 不给 | 全部 |

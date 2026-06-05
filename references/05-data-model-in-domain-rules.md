# 数据模型归属规则

## 核心原则

> 不单独设置全局数据结构设计阶段，但 P2 中每个模块都必须做数据模型设计。P3 再从各模块 data_model_design 汇总成统一的数据模型章节。

## 五类对象判定

| 类型 | 判定条件 | 当前领域行为 |
|------|---------|------------|
| owned_objects | 当前领域拥有生命周期 | 创建、维护、状态管理 |
| referenced_objects | 外部领域拥有，当前只识别 | 只存 ID 引用 |
| snapshot_objects | 需要保留历史时点事实 | 按策略更新（never/manual/event/periodic） |
| projection_views | 只展示外部数据 | JOIN/API 获取，不建列 |
| derived_data | 只使用计算结果 | 公式/规则计算，不存储 |

## owned_objects 格式

```yaml
owned_objects:
  - object_name: "Order"
    object_type: "aggregate_root"
    description: "订单聚合根"
    lifecycle_owner: "current_domain"
    source: ["EVT-003", "FUNC-005"]
```

## referenced_objects 格式

```yaml
referenced_objects:
  - object_name: "CustomerProfile"
    owner_domain: "customer"
    reference_type: "id_reference"
    reason: "订单需要关联客户"
    source: ["FUNC-005"]
    fields: ["customer_id", "customer_name", "customer_level"]
```

## snapshot_objects 格式

```yaml
snapshot_objects:
  - object_name: "BuyerSnapshot"
    source_owner_domain: "customer"
    snapshot_reason: "订单完成后客户信息可能变更，需保留下单时点快照"
    snapshot_timing: "on_order_create"
    update_strategy: "never_update"
    fields: ["customer_id", "customer_name", "customer_level", "contact_phone"]
```

## projection_views 格式

```yaml
projection_views:
  - view_name: "CustomerOrderSummary"
    source_domain: "customer"
    source_object: "CustomerProfile"
    displayed_fields: ["customer_name", "customer_level"]
    fetch_method: "query_api"
    reason_not_owned: "客户主数据由客户领域维护"
```

## 同名对象跨领域处理规则

```text
1. 同名对象不等于同一领域模型。
2. 每个共享对象必须有 Owner 领域。
3. Owner 领域负责创建、维护、生命周期和状态。
4. 非 Owner 领域只能：ID引用 / 快照 / 投影 / 事件消费 / ACL。
5. 非 Owner 领域不能维护完整主数据。
6. 如果对象归属不清，写入 open_issues。
7. 修改 Owner 必须进入人工审核。
```

示例：
```
客户领域: CustomerProfile, CustomerLevel, CustomerStatus
订单领域: customerId, BuyerSnapshot
售后领域: customerId, AfterSaleContactSnapshot
权限领域: userId / subjectId
```
均指向同一现实对象，但不是同一领域模型。
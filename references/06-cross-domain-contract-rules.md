# 跨领域契约规则

## 允许的跨领域交互方式

| 方式 | 说明 | 示例 |
|------|------|------|
| ID 引用 | 只存外部对象 ID | `customer_id: "CUST-001"` |
| 事件消费 | 订阅外部领域事件 | 订单创建 → 库存扣减 |
| 接口调用 | 通过 API 查询外部数据 | GET /customers/{id} |
| 快照 | 保留历史时点完整副本 | BuyerSnapshot |
| 投影 | 展示外部数据，不存储 | JOIN 查询 |
| ACL | 防腐层转换 | 外部 DTO → 内部 Entity |

## 跨领域关系格式

```yaml
cross_domain_relationships:
  - from_domain: "order"
    to_domain: "customer"
    relationship: "depends_on"
    interaction_mode: "id_reference + snapshot"
    description: "订单引用客户 ID，创单时快照客户信息"

  - from_domain: "order"
    to_domain: "inventory"
    relationship: "triggers"
    interaction_mode: "event"
    description: "订单创建→发布 OrderCreated 事件→库存扣减"
    events: ["OrderCreated"]
```

## 模块级跨领域数据使用

```yaml
cross_domain_data_usage:
  - external_object: "CustomerProfile"
    owner_domain: "customer"
    usage_mode: "id_reference"
    allowed_operations: ["read", "reference"]
    forbidden_operations: ["create", "update", "delete"]
    current_module_fields: ["customer_id", "customer_name"]

  - external_object: "CustomerProfile"
    owner_domain: "customer"
    usage_mode: "snapshot"
    allowed_operations: ["read", "create_snapshot"]
    forbidden_operations: ["update_snapshot", "delete"]
    snapshot_object: "BuyerSnapshot"
```

## 违规检测

```text
1. 外部对象出现在 owned_objects → 违规
2. 外部对象被直接修改 → 违规
3. snapshot 没有 update_strategy → 违规
4. projection 没有 source_domain → 违规
5. 跨领域交互不走契约 → 违规
```
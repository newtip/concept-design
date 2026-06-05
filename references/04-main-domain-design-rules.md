# 主领域功能设计规则

## 定位

P2 不是"全局数据模型阶段"，也不是"普通功能清单阶段"。P2 是：

> 以主领域为独立单元，将已确认需求和领域架构转化为模块级数据模型、功能、流程、页面、接口、不满足、DFX 和遗留问题的设计阶段。

## 文件隔离

```
workspace/domains/{domain_prefix}_{domain_name}/
├── {prefix}-main-domain-functional-design.yaml
├── {prefix}-review-checklist.md
└── {prefix}-repair-log.md
```

硬规则：
```text
1. 当前主领域只能写自己的目录。
2. 当前主领域不能修改其他主领域文件。
3. 当前主领域不能维护其他主领域拥有的数据。
4. 跨领域只允许接口、事件、ID 引用、快照、投影、ACL。
```

## YAML 结构

```yaml
main_domain_functional_design:
  project_name: ""
  domain:
    domain_id: ""
    domain_name: ""
    domain_prefix: ""
    responsibility: ""
    out_of_scope: []

  module_relationship_design:
    modules: []
    intra_domain_relationships: []
    cross_domain_relationships: []

  modules:
    - module_id: ""
      module_name: ""
      source_sub_domain: ""
      module_positioning: {}
      data_model_design:     # ← 每个模块必须包含
        owned_objects: []
        referenced_objects: []
        snapshot_objects: []
        projection_views: []
        derived_data: []
        state_model: []
        data_constraints: []
        cross_domain_data_usage: []
      function_design: {}
      workflow_design: {}
      page_design: {}
      interface_design: {}
      unsupported_design: []
      dfx_design: {}
      open_issues: []

  data_model_summary: {}
  cross_domain_contract_summary: {}
  traceability: []
  quality_checks: {}
```

## 设计规则

1. 只读 requirement-baseline.yaml 和 domain-architecture-baseline.yaml
2. 不得重新提取需求、重做行业增强、重划 DDD 领域
3. 每个子领域作为独立模块
4. 每个模块必须包含完整设计段（数据模型/功能/流程/页面/接口/不满足/DFX/遗留问题）
5. 数据模型必须区分 owned / referenced / snapshot / projection / derived
6. 页面设计必须包含样式、数据、交互、权限
7. 接口设计必须包含调用方向、失败处理和事件
8. 发现基线不足 → 写入 open_issues，不自行修改基线
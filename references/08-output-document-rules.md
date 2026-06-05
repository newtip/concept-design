# 输出文档规则

## Writer 铁律

```text
1. Writer 不新增任何前序未确认的内容。
2. Writer 只能从 domain-design-index.yaml 指向的 passed 产物读取。
3. Writer 不得重新设计、重新分析、重新决策。
4. Writer 的职责是汇总、格式化、补交叉引用、标注来源。
```

## 最终文档结构（11 章）

```
 1. 项目概述
 2. 需求与业务分析           ← 来自 requirement-baseline.yaml
 3. 领域架构设计              ← 来自 domain-architecture-baseline.yaml
 4. 数据模型设计              ← 从各模块 data_model_design 汇总
 5. 主领域功能设计            ← 从各领域 passed 产物汇总
 6. 跨领域接口与协作          ← 从 cross_domain_contract_summary 汇总
 7. 权限设计                  ← 从各模块 permission 汇总
 8. DFX 设计                  ← 从各模块 dfx_design 汇总
 9. 不满足设计                ← 从各模块 unsupported_design 汇总
10. 遗留问题                  ← 从各模块 open_issues 汇总
11. 后续建议
```

## 第 4 章数据模型设计汇总来源

```text
modules[].data_model_design
data_model_summary
modules[].data_model_design.cross_domain_data_usage
```

结构：
```
4.1 数据模型设计原则
4.2 主领域数据模型总览
4.3 按主领域展开
4.4 共享对象归属
4.5 引用/快照/投影/ACL 关系
4.6 状态模型与数据约束
4.7 数据模型遗留问题
```

## 第 5 章主领域功能设计汇总来源

```text
module_relationship_design
modules[].function_design
modules[].workflow_design
modules[].page_design
modules[].interface_design
modules[].unsupported_design
modules[].dfx_design
modules[].open_issues
```
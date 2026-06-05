# P2 输出风格约束

## 🔴 核心原则

**P2 是主领域功能设计，不是 DDD 建模复述。**

## 禁止输出（作为主结构）

以下内容在 DDD 架构设计阶段（P1 Agent 03）已经完成，P2 不得作为主体结构重新输出：

```yaml
# ❌ 禁止在 P2 中作为顶层层级
ubiquitous_language:
aggregate_design:
domain_services:
repository_interface:
architecture_patterns:
application_services:
```

## 允许的使用方式

上述内容如确实需要，只能作为模块设计的**依据引用**，不作为 P2 输出主体：

```yaml
# ✅ 可以这样引用
module_positioning:
  based_on_aggregate: "培训计划聚合根"
  based_on_domain_service: "计划校验服务"  # 作为依据，不作为主结构

# ✅ 数据模型设计
data_model_design:
  owned_objects:
    - object_name: "培训计划"
      based_on_aggregate: "AGG-TP-01"  # 引用，不展开聚合设计
```

## P2 主体结构（必须按此顺序）

```
1. 模块关系设计 (module_relationship_design)
2. 模块数据模型设计 (modules[].data_model_design)
3. 功能设计 (modules[].function_design)
4. 流程设计 (modules[].workflow_design)
5. 页面设计 (modules[].page_design)
6. 接口设计 (modules[].interface_design)
7. 不满足设计 (modules[].unsupported_design)
8. DFX 设计 (modules[].dfx_design)
9. 遗留问题 (modules[].open_issues)
```

## 数据模型粒度控制

### 概设级别（P2 必须输出）
```yaml
fields:
  - field_name: "class_name"
    business_meaning: "班级名称"
    semantic_type: "ownership"
    required: true
    source: "BR21"
```

### 详设级别（不在 P2 输出）
```yaml
# ❌ 不要输出物理字段约束
type: String(200)
constraints: PK, not null, varchar
index: idx_class_name
DDL: CREATE TABLE ...
```

**原则：P2 用业务语义描述字段，不进入物理实现。** 除非需求文档中明确给出了字段类型和长度要求。

## 模块命名规范

```yaml
# ✅ 统一使用 module_id 数组
modules:
  - module_id: "MOD-tp-01"
    module_name: "开班计划管理"

# ❌ 禁止模块名作为 YAML key
modules:
  mod_tp_01_开班计划管理:
    data_model_design: ...
```

## 统一语言处理

DDD 统一语言已在 P1 建立。P2 中：
- 引用领域术语时，使用 domain-architecture-baseline.yaml 中的术语
- 不要在 P2 产物中重复展开 ubiquitous_language 章节
- 如需补充新术语，写入 `open_issues` 而非自行定义

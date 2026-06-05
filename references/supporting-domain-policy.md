# 支撑域与通用域 P2 策略

## 总原则

所有 DDD 领域都必须进入 P2。不同 `domain_type` 的设计重点不同，但不得跳过。

除非用户明确声明某个领域不进入本次 P2，否则所有领域必须：

```yaml
p2_required: true
design_level: full
status: pending
```

禁止使用任何“跳过 P2 / 只做引用 / 仅平台能力 / 不需要设计”的旧式标记。

这些旧标记会造成 Orchestrator 和 Writer 误判：支撑域、通用域被识别出来但没有领域设计产物。

## Core 领域

输出完整业务设计：

- 业务流程
- 页面
- 接口
- 数据模型
- 状态流转
- DFX
- 不满足设计
- 遗留问题

## Supporting 领域

也必须进入 P2，但重点是支撑能力设计：

- 被哪些核心域调用
- 提供哪些接口
- 消费/发布哪些事件
- 失败处理与重试
- 配置项
- 日志与审计
- 数据模型与跨域对象归属

## Generic 领域

也必须进入 P2，但重点是通用能力设计：

- 权限
- 通知
- 审计
- 字典
- 文件
- 组织
- 配置
- 平台能力如何服务各业务域

如果没有独立业务页面，不得留空，应写成嵌入式能力：

```yaml
page_design:
  pages:
    - page_name: "无独立业务页面"
      page_type: "embedded_capability"
      style_summary: "该领域能力通过其他核心领域页面嵌入使用。"
      data_sections: []
      interactions: []
      permissions:
        - role: "系统管理员"
          operations: ["配置", "查看日志"]
          data_scope: "平台配置数据"
          field_restrictions: []
```

## Writer 规则

P3 Writer 必须汇总所有 `status=passed` 且 `review_status=passed` 的领域，不得因为领域是 supporting/generic 就跳过。

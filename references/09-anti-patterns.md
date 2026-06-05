# 反模式

## P1 反模式

```
❌ Agent 01 做行业增强/DDD/数据模型     ✅ 只提取需求事实
❌ Agent 02 把建议写成已确认需求         ✅ 建议进 decision_backlog
❌ Agent 03 做功能设计/页面设计          ✅ 只做领域/Context/聚合
❌ 跳过 Checkpoint 直接进入 P2           ✅ 必须等用户确认
```

## CP 反模式

```
❌ 让用户审完整 YAML                     ✅ 只看 2 张确认卡
❌ 确认卡超过 1.5 页                     ✅ 压缩到关键结论
❌ 不要求用户选设计模式                   ✅ 列出 A/B/C 并推荐
❌ 用户未明确回复就继续                   ✅ 必须等"确认"或"修改"
```

## P2 反模式

```
❌ 重新提取需求                           ✅ 只读双基线
❌ 重做 DDD 领域划分                      ✅ 发现不足写 open_issues
❌ 单独设全局数据模型阶段                  ✅ 嵌入每个模块
❌ 同名对象多领域各自维护                  ✅ Owner/Reference/Snapshot/Projection/ACL
❌ 外部对象放入 owned_objects              ✅ 区分五类对象
❌ snapshot 没有 update_strategy           ✅ 必填
❌ projection 没有 source_domain           ✅ 必填
❌ 设计 Agent 自评通过                     ✅ 独立 Review Agent
❌ Review 后不修复直接汇报                 ✅ Fix → Re-report
❌ 修复时全量重写                          ✅ 最小切片修复
```

## P3 反模式

```
❌ Writer 新增需求/功能/接口               ✅ 只汇总已确认内容
❌ Writer 读取非 passed 产物               ✅ 只读 passed
❌ 最终文档没有标注来源                    ✅ 每段标注来自哪个文件/agent
```
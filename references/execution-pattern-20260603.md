# End-to-End Execution Notes — 2026-06-03

## Context
Full pipeline execution on "承包商培训管理系统" (10 domains, 5 core, 5 supporting/generic).

## Execution Pattern That Worked

### P1: Orchestrator Self-Execution (~5 min)
- Agent 01 (需求提炼): Orchestrator read raw .docx, output business_model.yaml directly. 489 paragraphs → 12 events, 15 functions, 8 entities, 10 open questions.
- Agent 02 (行业洞察): Orchestrator read business_model.yaml, output industry_insight.yaml. Maturity score 55, 7 recommendations, 5 decision backlog items.
- Agent 03 (DDD): Orchestrator read both prior outputs, output architecture_design.yaml. 10 domains (5 core/2 supporting/3 generic), 10 bounded contexts, 7 aggregates.

### CP: User Checkpoint (~2 min)
- Presented compressed cards: Top 3 questions, design mode selection
- User confirmed: capacity=approved_count, notification=email+in-app, mode=A (sequential)

### P2: delegate_task Subagents (~25 min total)
Each domain delegated as a separate subagent:
- DM-001 (tp): 1880 lines, 540s — passed
- DM-002 (tr): 1768 lines, 497s — passed  
- DM-003 (td): 1803 lines, 500s — passed
- DM-004 (em): 2536 lines, timeout at 600s but file already written — retry confirmed complete
- DM-005 (sm): 1589 lines, 430s — passed

### P3: delegate_task Subagent (~5 min)
Writer subagent: read final-document-index.yaml + 5 passed domain files → 588-line overview-design.md

## Key Learnings

### Subagent Timeout Recovery
DM-004 (考试管理域, 3 modules) hit the 600s timeout but had already written the complete YAML file (~19 API calls completed before timeout). Pattern: before re-running, check if file exists and `head -5` to verify it's valid YAML with correct `main_domain_functional_design` header. If so, skip re-generation and proceed to Review.

### Context Size for Subagents（历史经验，不适用于 v1.3+）
旧版 P2 subagent 曾通过 read_file 自行发现 baselines 和 prior domain files，并认为无需预打包 Context Pack。该经验来自无 Context Pack 的旧架构。

v1.3+ 必须以 `context-pack` 为 P2 唯一输入，不再允许 P2 子 Agent 自行读取全量 baselines、原始需求或其他领域完整设计文件。

### Parallel vs Sequential
DM-004 and DM-005 were attempted in parallel (batch delegate_task). DM-005 succeeded, DM-004 timed out. For heavy domains, sequential execution with longer timeouts may be more reliable.

### File Size Reference
- P1 outputs: 3 files, ~55KB total
- P2 outputs: 5 files, ~490KB total  
- P3 output: 1 file, ~44KB
- Total pipeline: ~600KB design artifacts for 10-domain system

## Skill 优化工作流（2026-06-03 验证）

### 迭代模式
1. 用户发送 skill zip → agent 提取分析
2. 用户发送 GPT review（含 20 项具体建议）→ agent 按文件逐项落地
3. agent 执行 `python scripts/lint_skill_package.py` 验证 → 打包发回
4. 用户验证、反馈、再发新版

### 常见修复
- Schema YAML 正则转义：双引号中 `\d` 非法，改用单引号
- 模板缺失字段：对照 Schema required 补齐
- workspace 污染：发布前删除，lint 脚本自动检查
- Agent 提示词顺序：业务推理优先 > 负面约束 > Schema 约束
- 发布包改名：确保 name 字段与目录名一致（concept-design 非 cencept-design）

---
name: "<skill-name>"
description: "<What this skill does in one sentence>. Invoke when <trigger conditions / user phrases>."
version: "0.1.0"
triggers: ["<phrase-1>", "<phrase-2>"]
inputs: ["<glob-pattern>"]
outputs: ["<glob-pattern>"]
tools: ["filesystem", "git"]
author: "AI"
last_updated: "2026-06-13"
---

# <Skill Title>

> **本文件为 Skill 模板,使用前请复制到 `.trae/skills/<skill-name>/SKILL.md` 并填写所有 `<占位符>`。**
> **模板以 `_TEMPLATE/` 命名,加入 `.gitignore` 或标注只读;正式版入仓。**

## 1. 触发条件 (Trigger Conditions)

详细描述什么场景下激活此 Skill。包括:
- 用户的哪些表述会触发(如"为 XXX 写测试")
- 哪些上下文条件必须满足(如"目标文件存在")
- 哪些场景**不会**触发(如"非 JS/Vue 文件")

## 2. 必读上下文 (Required Context)

在执行 Skill 前,Agent **必须**读取以下文件:

- `.trae/rules/SESSION_REMINDER.md` — 全局规则入口
- `.trae/rules/<file>.md` — <用途>
- `.trae/context/<file>.md` — <用途>
- `.trae/skills/SKILL_AUTHORING.md` — Skill 编写规范
- `.trae/skills/_TEMPLATE/PROMPT_TEMPLATE.md` — Prompt 构造规范

## 3. Prompt 模板引用

请阅读并按 [PROMPT_TEMPLATE.md](../_TEMPLATE/PROMPT_TEMPLATE.md) 规范构造 prompt。
具体本 Skill 的 prompt 见同目录 `PROMPT_TEMPLATE.md`。

## 4. 硬约束 (Hard Constraints)

以下约束**不可违反**:

- [ ] 不使用 emoji(用 `[OK]`/`[X]`/`[!]` 替代)
- [ ] data-testid 优先于 CSS 选择器
- [ ] MSW mock 而非模块 mock(`vi.mock` 仅用于 utils)
- [ ] 覆盖 happy path + 至少 3 类 edge case
- [ ] 通过 `.trae/scripts/ai_content_guard.py` 检查
- [ ] 不修改既有 40+ `.trae/rules/` 文件
- [ ] 跨 Agent 并行时通过 git lock 串行化写操作

## 5. 输出规范 (Output Spec)

具体输出文件的路径、格式、Schema 见 `OUTPUT_SPEC.md`(若存在)或在本文档第 5.1 节描述。

### 5.1 输出文件清单

| 路径 | 格式 | 用途 |
|------|------|------|
| `<path>` | `<format>` | <用途> |

## 6. Failure Mode

Agent 调用失败时的处理策略:

| 失败类型 | 处理 |
|---------|------|
| 输入文件不存在 | 返回明确错误,不创建空文件 |
| LLM 生成超长 | 截断并提示用户拆分 |
| 校验失败(ai_content_guard) | 自动修复一次,仍失败则人工介入 |
| 权限拒绝(auth/payment) | deny 立即返回,不重试 |
| MCP server 启动失败 | 降级为无 MCP 模式,记录到 agent-runs.jsonl |

## 7. Observability Hook

调用前后必须更新可观测性数据:

- **调用前**: 写入 `.trae/state/agent-runs.jsonl` (status=`running`)
  ```json
  {"requestId":"<uuid>","agentId":"<id>","skillName":"<name>","startedAt":"<iso>","status":"running","files_changed":[]}
  ```
- **调用后**: 更新该行 (status=`success`|`failed`, `finishedAt`, `tokens_used`, `files_changed`)
- **失败**: 暴露 Prometheus 指标
  ```
  skill_invocation_total{skill_name="<name>", status="failed"} 1
  skill_invocation_duration_seconds{skill_name="<name>"} 12.3
  ```
- **日志保留**: 90 天(由 `.trae/scripts/prune_agent_logs.py` 自动清理)

## 8. 多 Agent 隔离

- 本 Skill 在多 Agent 并行(AGENT_PORT 3010-3019)时,写操作前必须获取 git lock
- 只读操作可并发
- 详见 `.trae/rules/multi-agent-coordination.md`
# Skill 调度规则

> **版本**: v1.0 (2026-06-13)
> **目的**: 定义 Agent 启动与 Skill 调用的优先级与流程,最小化 Token 消耗

## 1. Agent 启动加载顺序

Agent 启动时按以下顺序加载 Skill 与 Context,遵循 **"U 型效应"** 优化原则:

```
Step 1: INDEX 加载 (优先级最高,Token 最小)
  ├── Read .trae/skills/INDEX.md       (注册表, ~2K)
  ├── Read .trae/context/INDEX.md      (Context 注册表, ~1K)
  └── Read .trae/rules/RULES_INDEX.md  (既有 rules 索引, ~3K)

Step 2: 触发匹配 (基于用户输入)
  └── 匹配 INDEX 中的 triggers → 激活目标 Skill

Step 3: 必读上下文 (Skill 声明的 required context)
  ├── Read .trae/rules/<required>.md
  ├── Read .trae/context/<required>.md
  └── Read .trae/skills/<skill>/SKILL.md

Step 4: Prompt 构造
  └── Read .trae/skills/<skill>/PROMPT_TEMPLATE.md

Step 5: 执行
  └── 调用 LLM,生成代码/响应

Step 6: Observability
  └── 写入 .trae/state/agent-runs.jsonl
```

## 2. Token 预算

| 阶段 | 预算 | 说明 |
|------|------|------|
| Step 1 (INDEX) | ≤ 6K | 注册表 |
| Step 2 (匹配) | 0 | 模式匹配,不消耗 Token |
| Step 3 (Skill SKILL.md) | ≤ 3K | 单 Skill 描述 |
| Step 4 (Prompt 模板) | ≤ 1K | 模板 |
| Step 5 (执行) | 视任务 | 由 LLM 决定 |
| **总计(典型任务)** | **≤ 10K** | 不含源码 |

## 3. 优先级规则

当多个 Skill 触发冲突时:

1. **精确匹配 > 模糊匹配**: 用户输入包含 trigger 短语 → 高优先级
2. **最近使用 > 历史使用**: LRU 缓存 5 分钟
3. **Scope 窄 > 广**: `test-gen-js` 优先于 `test-gen`
4. **手工编写 > AI 生成**: 人工 Skill 优先

## 4. 多 Agent 隔离

- 每个 Agent 在自己的 worktree 中操作(`.trae/rules/multi-agent-coordination.md`)
- AGENT_PORT 隔离 3010-3019,确保测试不冲突
- INDEX.md、CHANGELOG.md 写入必须 git lock
- 写操作串行化,读操作可并发

## 5. MCP 加载

若 `.ai/mcp.json` 中 `disabled` 为 false,Agent 启动时:
- 解析配置
- 启动对应 MCP server(`npx @playwright/mcp@latest` 等)
- 失败时降级为无 MCP 模式,记录到 agent-runs.jsonl

## 6. 失败回退

| 阶段 | 失败处理 |
|------|---------|
| INDEX 缺失 | 提示"Skill 不可用,请检查 .trae/skills/INDEX.md" |
| Trigger 无匹配 | 列出可用 Skill,询问用户 |
| Context 缺失 | 回退至源码分析 |
| Prompt 模板缺失 | 使用通用模板 + Skill 描述 |
| LLM 失败 | 重试 1 次,仍失败则人工介入 |
| MCP 失败 | 降级无 MCP,记录 |

## 7. 缓存策略

- INDEX.md: 5 分钟缓存
- SKILL.md: 单次任务内缓存
- Context 文档: 5 分钟缓存
- LLM 调用: 不缓存(每次新生成)

## 8. 与 `.trae/rules/SESSION_REMINDER.md` 的关系

- 本文档聚焦 Skill 调度
- `SESSION_REMINDER.md` 聚焦全局规则(测试入口、PowerShell 等)
- Agent 启动时**两者都加载**,SESSION_REMINDER 在前,本文档在后
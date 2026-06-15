---
name: "test-gen"
description: "Generate Vitest + MSW unit tests for JS utils and Vue components. Invoke when user asks to write tests, add test coverage, or generate test file for an existing module."
version: "0.1.0"
triggers:
  - "为 XXX 写测试"
  - "生成测试"
  - "补充测试覆盖"
  - "write tests for"
  - "generate tests"
  - "add test coverage"
inputs:
  - "src/**/*.js"
  - "src/**/*.vue"
  - "src/utils/**/*.js"
  - "src/services/**/*.js"
  - "src/components/**/*.vue"
outputs:
  - "src/**/*.spec.js"
  - "src/mocks/handlers.js"
  - ".trae/state/agent-runs.jsonl"
tools: ["filesystem", "git"]
author: "AI"
last_updated: "2026-06-13"
---

# test-gen Skill

> 为 JS util 函数与 Vue 组件自动生成符合项目规范的 Vitest + MSW 单元测试。

## 1. 触发条件 (Trigger Conditions)

### 1.1 激活场景

用户表述包含以下任一短语(中文/英文):
- "为 XXX 写测试" / "为 XXX 生成测试"
- "补充 XXX 的测试覆盖"
- "write tests for XXX" / "generate tests for XXX"
- "add test coverage for XXX"

### 1.2 上下文条件

- 目标文件存在(`src/**/*.js` 或 `src/**/*.vue`)
- `.trae/context/<layer>/<topic>.md` 若存在则优先读取
- `.trae/rules/frontend-testing-standards.md` 必须存在

### 1.3 不触发场景

- 后端 Python 文件(`meta/**/*.py`)
- 配置/数据文件(`*.json`, `*.yaml`, `*.yml`)
- 已有同名 `.spec.js` 文件(询问用户覆盖确认)
- Healer/PERMISSIONS.md 中标记为 deny 的模块(auth/payment/crypto/compliance)

## 2. 必读上下文 (Required Context)

执行 Skill 前**必须**读取:

- `.trae/rules/SESSION_REMINDER.md` — 全局规则入口
- `.trae/rules/frontend-testing-standards.md` — 前端测试规范(vitest/MSW/happy-dom)
- `.trae/rules/test-case-standards.md` — 测试用例编写规范
- `.trae/rules/test-data-rules.md` — 测试数据规范(Faker)
- `.trae/skills/SKILL_AUTHORING.md` — Skill 编写规范
- `.trae/skills/test-gen/PROMPT_TEMPLATE.md` — 本 Skill 的 Prompt 模板
- `.trae/skills/test-gen/OUTPUT_SPEC.md` — 本 Skill 的输出规范
- `.trae/context/<layer>/<target>.md`(若存在) — 目标文件 Context

## 3. Prompt 模板引用

请阅读并按 [PROMPT_TEMPLATE.md](./PROMPT_TEMPLATE.md) 规范构造 prompt。

## 4. 硬约束 (Hard Constraints)

以下约束**不可违反**:

### 4.1 通用硬约束(继承自 SKILL_AUTHORING.md)

- [ ] 不使用 emoji(用 `[OK]`/`[X]`/`[!]` 替代)
- [ ] data-testid 优先于 CSS 选择器
- [ ] MSW mock 而非模块 mock(`vi.mock` 仅用于纯 utils)
- [ ] 覆盖 happy path + 至少 3 类 edge case
- [ ] 通过 `.trae/scripts/ai_content_guard.py` 检查
- [ ] 不修改既有 `.trae/rules/` 文件
- [ ] 跨 Agent 并行时通过 git lock 串行化写操作

### 4.2 test-gen 专属硬约束

- [ ] **JS util 测试必须覆盖 12 类场景**(详见 OUTPUT_SPEC.md § 2.1)
- [ ] **Vue 组件测试必须覆盖 props/emit/slot/store 4 维度**(详见 OUTPUT_SPEC.md § 2.2)
- [ ] MSW handlers 必须可独立运行(无需后端)
- [ ] 覆盖率 ≥ 80%(关键函数 100%)
- [ ] 测试文件以 `.spec.js` 结尾,与源文件同目录
- [ ] 必须使用项目现有 helper(如有),不重复造轮子
- [ ] 遵循 `frontend-testing-standards.md` 的 MSW/happy-dom 配置

### 4.3 安全硬约束

- [ ] **auth/ 目录下的文件**: 直接拒绝,不生成测试,提示用户人工编写
- [ ] **payment/ 目录下的文件**: 直接拒绝
- [ ] **crypto/ 目录下的文件**: 直接拒绝
- [ ] **compliance/ 目录下的文件**: 直接拒绝

## 5. 输出规范 (Output Spec)

详细见 [OUTPUT_SPEC.md](./OUTPUT_SPEC.md)。

### 5.1 输出文件清单

| 路径 | 格式 | 用途 | 条件 |
|------|------|------|------|
| `<target>.spec.js` | Vitest | 主测试文件 | 必须 |
| `<target>.msw.js`(可选) | MSW handler | 配套 MSW mock | 若需要 mock HTTP |
| `.trae/state/agent-runs.jsonl` | JSONL | 可观测性 | 必须 |

## 6. Failure Mode

| 失败类型 | 处理 |
|---------|------|
| 目标文件不存在 | 返回错误,不创建空测试 |
| 已有 `.spec.js` | 询问用户是否覆盖 |
| LLM 生成失败 | 重试 1 次(降低 temperature);仍失败 → 标记 TBD |
| `ai_content_guard.py` 失败 | 自动修复 1 次;仍失败 → 人工 review |
| 安全模块命中(auth/payment/crypto/compliance) | 立即返回错误,记录拒绝原因 |
| MCP server 启动失败 | 降级无 MCP 模式 |
| 多 Agent 写冲突 | git lock 失败时退避重试 |

## 7. Observability Hook

调用前后更新:

- **调用前**: 写入 `.trae/state/agent-runs.jsonl`
  ```json
  {"requestId":"<uuid>","agentId":"<id>","skillName":"test-gen","startedAt":"<iso>","status":"running","files_changed":[],"target":"<src path>"}
  ```
- **调用后**: 更新该行 (status=`success`|`failed`, `finishedAt`, `tokens_used`, `files_changed`)
- **指标聚合**: 使用 `.trae/scripts/metrics_aggregator.py` 生成 Prometheus 格式指标
  ```bash
  python .trae/scripts/metrics_aggregator.py --format prometheus
  python .trae/scripts/metrics_aggregator.py --format json --skill test-gen
  ```
  输出指标包括:
  - `skill_invocation_total{skill_name,status}` - 调用次数
  - `skill_invocation_duration_seconds_avg{skill_name}` - 平均耗时
  - `skill_coverage_avg{skill_name}` - 平均覆盖率
  - `skill_tokens_used_total` - 总 token 消耗
  - `skill_files_changed_total` - 总文件变更数
- **日志清理**: 使用 `.trae/scripts/prune_agent_logs.py` 清理超过 90 天的日志
  ```bash
  python .trae/scripts/prune_agent_logs.py --dry-run  # 预览
  python .trae/scripts/prune_agent_logs.py            # 执行清理
  ```
  清理策略:
  - 超过 90 天的记录归档到 `.trae/state/archive/` (gzip 压缩)
  - 聚合指标写入 `.trae/state/agent-runs-aggregated.jsonl` (永久保留)
  - 生成清理报告到 `.trae/state/prune-report-latest.json`
- **失败**: 暴露 Prometheus 指标
  ```
  skill_invocation_total{skill_name="test-gen", status="failed"} 1
  skill_invocation_duration_seconds{skill_name="test-gen"} 12.3
  ```
- **覆盖度统计**: 测试生成后,记录 `coverage_lines`、`coverage_branches`

## 8. 多 Agent 隔离

- 写操作前必须获取 git lock(`.trae/state/.git-lock`)
- 只读操作可并发
- AGENT_PORT 隔离(3010-3019)
- 详见 `.trae/rules/multi-agent-coordination.md`

## 9. 模板同步说明

本 Skill 内容符合 `.trae/skills/_TEMPLATE/SKILL.md` 规范,可由 aiwg 工具同步至:
- Claude Code (`~/.claude/skills/test-gen/`)
- Cursor (`.cursor/rules/test-gen.mdc`)
- GitHub Copilot (`.github/copilot/test-gen.md`)
- Warp / OpenClaw 等

## 10. 版本历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版,含 JS util + Vue 组件双分支 | AI |
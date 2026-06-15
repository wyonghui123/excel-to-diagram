# Skill 注册表 (INDEX)

> **最后更新**: 2026-06-13
> **维护者**: 见各 Skill `author` 字段
> **同步规则**: 新增/修改 Skill 时,本文件**必须**同步更新
> **总数**: 25 个 Skill (23 active, 2 deprecated)

## 注册表

| ID | Name | 用途 | 触发短语 | 路径 | Last Updated | Status |
|----|------|------|---------|------|--------------|--------|
| SK-001 | test-gen | 为 JS util / Vue 组件生成 Vitest + MSW 测试 | "为 XXX 写测试" / "生成测试" / "补充测试覆盖" | `.trae/skills/test-gen/` | 2026-06-13 | active |
| SK-002 | playwright-cli-testing | Playwright CLI 高效测试工作流,Token 消耗比 MCP 低 4-5x | "E2E 测试" / "Playwright 测试" / "长流程测试" | `.trae/skills/playwright-cli-testing/` | 2026-06-13 | active |
| SK-003 | e2e-testing | Playwright E2E 测试工作流,包含终端管理和测试模板 | "E2E 测试" / "终端管理" / "测试流程" | `.trae/skills/e2e-testing/` | 2026-06-13 | active |
| SK-004 | code-gen-testing | 代码生成测试工作流,AI 生成 Playwright 脚本执行 | "AI 生成脚本" / "回归测试" / "CI 自动化" | `.trae/skills/code-gen-testing/` | 2026-06-13 | active |
| SK-005 | problem-fixing | pytest 测试问题修复工作流,管理 fix_tasks.json | "修复测试问题" / "fix_tasks" / "claim" | `.trae/skills/problem-fixing/` | 2026-06-13 | active |
| SK-006 | writing-plans | 编写多步骤任务的实现计划 | "写计划" / "实现计划" / "多步骤任务" | `.trae/skills/writing-plans/` | 2026-06-13 | active |
| SK-007 | verification-before-completion | 完成前验证,运行验证命令再声称成功 | "验证完成" / "检查通过" / "确认修复" | `.trae/skills/verification-before-completion/` | 2026-06-13 | active |
| SK-008 | using-superpowers | 会话开始时建立如何查找和使用 Skill | "开始会话" / "使用 Skill" | `.trae/skills/using-superpowers/` | 2026-06-13 | active |
| SK-009 | test-driven-development | TDD 工作流,先写测试再写实现代码 | "TDD" / "测试驱动" / "先写测试" | `.trae/skills/test-driven-development/` | 2026-06-13 | active |
| SK-010 | systematic-debugging | 系统化调试,根因调查后再修复 | "调试" / "bug 修复" / "测试失败" | `.trae/skills/systematic-debugging/` | 2026-06-13 | active |
| SK-011 | subagent-driven-development | 子代理驱动开发,每个任务独立代理 + 两阶段审查 | "子代理开发" / "独立任务" / "并行实现" | `.trae/skills/subagent-driven-development/` | 2026-06-13 | active |
| SK-012 | finishing-a-development-branch | 完成开发分支,决定如何集成工作 | "完成分支" / "集成工作" / "合并准备" | `.trae/skills/finishing-a-development-branch/` | 2026-06-13 | active |
| SK-013 | requesting-code-review | 请求代码审查,验证工作符合要求 | "请求审查" / "代码审查" / "合并前检查" | `.trae/skills/requesting-code-review/` | 2026-06-13 | active |
| SK-014 | receiving-code-review | 接收代码审查反馈,实现建议 | "接收审查" / "审查反馈" / "实现建议" | `.trae/skills/receiving-code-review/` | 2026-06-13 | active |
| SK-015 | executing-plans | 执行实现计划,带审查检查点 | "执行计划" / "实现计划" / "审查检查点" | `.trae/skills/executing-plans/` | 2026-06-13 | active |
| SK-016 | dispatching-parallel-agents | 并行代理调度,处理 2+ 独立任务 | "并行代理" / "独立任务" / "多代理协作" | `.trae/skills/dispatching-parallel-agents/` | 2026-06-13 | active |
| SK-017 | brainstorming | 创意工作前的头脑风暴,探索用户意图 | "头脑风暴" / "创意工作" / "需求探索" | `.trae/skills/brainstorming/` | 2026-06-13 | active |
| SK-018 | devops-deploy-sop | DevOps 部署 SOP 助手 | "开始部署" / "deploy" / "查看状态" / "回滚" | `.trae/skills/devops-deploy-sop/` | 2026-06-13 | active |
| SK-019 | excel-to-diagram | Excel 数据转应用架构图(Mermaid) | "Excel 转架构图" / "上传 Excel" / "可视化" | `.trae/skills/excel-to-diagram/` | 2026-06-13 | active |
| SK-020 | mcp-frontend-testing | MCP 前端测试工作流 | "MCP 测试" / "前端验证" | `.trae/skills/mcp-frontend-testing/` | 2026-06-13 | **deprecated** |
| SK-021 | browser-use-testing | 浏览器使用测试(已废弃) | "浏览器测试" | `.trae/skills/browser-use-testing/` | 2026-06-13 | **deprecated** |
| SK-022 | test-bootstrap | 测试/服务启动前置 autoload (强制读 multi-agent + SESSION_REMINDER + service-manager) | "跑测试"/"pytest"/"npx playwright"/"启动服务"/"service_manager" | `.trae/skills/test-bootstrap/` | 2026-06-14 | active |

**废弃说明**:
- SK-020 (mcp-frontend-testing): 2026-06-02 起统一使用 playwright-cli-testing
- SK-021 (browser-use-testing): 2026-06-03 起统一使用 PlaywrightCLI

## 业务流三件套 (SK-022/023/024) 工作流

```
chat: "/biz-test business-object-lifecycle"
  ↓ SK-022 Planner → business-flow.yaml 草稿
  ↓ IDE 自动打开,状态栏 Draft Ready
chat: "Approve" 或 PM 在 IDE 点击 [Approve]
  ↓ review_status: draft → approved
  ↓ SK-023 Generator → e2e/business-flow/<feat>.spec.js
  ↓ IDE 跑测试
chat: "测试失败,修复" 或 /heal
  ↓ SK-024 Healer → 人在回路修复
```

详见 [业务流路由规则](./_ROUTER/intent_router.md)

## 模板(Template)

| ID | Name | 用途 | 路径 | 状态 |
|----|------|------|------|------|
| TPL-001 | _TEMPLATE/SKILL.md | Skill 模板 | `.trae/skills/_TEMPLATE/SKILL.md` | template |
| TPL-002 | _TEMPLATE/PROMPT_TEMPLATE.md | Prompt 模板 | `.trae/skills/_TEMPLATE/PROMPT_TEMPLATE.md` | template |

## 治理文件

| 文件 | 用途 | 路径 |
|------|------|------|
| SKILL_AUTHORING.md | Skill 编写规范 | `.trae/skills/SKILL_AUTHORING.md` |
| SCHEDULING.md | Skill 调度规则 | `.trae/skills/SCHEDULING.md` |
| CHANGELOG.md | 变更日志 | `.trae/skills/CHANGELOG.md` |
| healer/PERMISSIONS.md | Healer 边界(仅文档,实现留 Spec B) | `.trae/skills/healer/PERMISSIONS.md` |

## 未来计划(Spec B+)

| 计划 | 用途 | 优先级 |
|------|------|--------|
| visual-test | AI 视觉回归(YonDesign 合规) | P2 |
| e2e-heal | Playwright Healer 自动修复 | P1 (待 Healer 启用) |
| bug-report | 自动生成 Bug 报告 | P3 |
| spec-coverage | Spec ↔ Test 双向追溯 | P3 |

## 注册流程

新增 Skill:

1. 复制 `_TEMPLATE/SKILL.md` 到新目录
2. 在上表追加一行(ID 格式: `SK-NNN`,Name 与目录名一致)
3. 在 `CHANGELOG.md` 追加 entry
4. 更新该 Skill 的 `last_updated`

修改 Skill:

1. 修改文件
2. 更新上表的 `Last Updated`
3. 更新 SKILL.md 的 `version` 与 `last_updated`
4. 在 `CHANGELOG.md` 追加 entry

## 版本历史

| 日期 | 变更 | Author |
|------|------|--------|
| 2026-06-13 | 全量注册: SK-001~SK-021 (20 active + 2 deprecated), 新增 metrics_aggregator.py | AI |
| 2026-06-13 | 初版,注册 SK-001(test-gen)、治理文件、模板 | AI |
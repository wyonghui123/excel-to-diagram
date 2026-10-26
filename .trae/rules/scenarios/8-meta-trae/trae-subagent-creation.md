---
description: Trae IDE Subagent 创建指南 - 在 UI 中创建可被其他智能体调用的 Subagent 时加载。说明真实 Subagent 路径、必填字段、与 .md 文件的关系。
globs: ["**/.trae/agents/**", "**/.trae/agents/*.md"]
version: "0.1.0"
author: "AI"
last_updated: "2026-09-02"
---

# Trae IDE Subagent 真实创建流程 (v5.4)

> **重要修正**：v5.3 文档误判 `.trae/agents/*.md` 是 Subagent 配置文件。
> **真相**（来自 [docs.trae.cn/ide/agent](https://docs.trae.cn/ide/agent)）：真实 Subagent 需在 IDE UI 中创建。

---

## 1. 真实 Subagent 与 .md 文件的区别

| 维度 | UI 创建的 Subagent | `.trae/agents/*.md` |
|------|-------------------|---------------------|
| **是否被识别** | ✅ TRAE 自动识别 | ⚠️ 仅作"提示词文档"参考 |
| **能否被其他 Agent 调用** | ✅ 可以（勾选开关后）| ❌ 不能 |
| **独立上下文** | ✅ | ❌ |
| **必填字段** | `english_identifier` + `when_to_call` | 任意 frontmatter |
| **创建路径** | IDE UI | 手动 Write |

**结论**：`.trae/agents/*.md` 文件**保留作为提示词文档**，但**真正的 Subagent 需在 UI 中创建**。

---

## 2. Subagent 创建流程（UI）

### 2.1 入口

```
AI 对话输入框 → 输入 @ → 浮起面板底部"创建智能体"按钮
```

### 2.2 必填字段（v5.4 修正）

| 字段 | 说明 | 范例 |
|------|------|------|
| **英文标识名**（`english_identifier`）| 被调用时的唯一英文标识 | `project-analyzer` |
| **何时调用**（`when_to_call`）| 描述其他智能体调用该智能体的合适场景和时机 | "当需要分析项目目录结构和模块依赖时调用" |
| **名称** | 智能体显示名 | "项目结构分析器" |
| **提示词**（Prompt）| 智能体的人设、回答口吻、工作流程、工具使用时机 | 详细 Markdown |
| **可被其他智能体调用** | **必须勾选** | ✅ |
| **工具** | MCP Server + 内置工具（阅读/文件系统/终端/联网搜索/预览）| 按需勾选 |

### 2.3 推荐导入的官方 Subagent

来自 [docs.trae.cn/ide/solo-coder](https://docs.trae.cn/ide/solo-coder)：

| 智能体 | 链接 | 适用 |
|-------|------|------|
| UI Designer | [s.trae.com.cn/a/8fdcb7](https://s.trae.com.cn/a/8fdcb7) | UI/UX 设计 |
| Frontend Architect | [s.trae.com.cn/a/3fbe5a](https://s.trae.com.cn/a/3fbe5a) | React/Vue/Angular |
| Backend Architect | [s.trae.com.cn/a/441a24](https://s.trae.com.cn/a/441a24) | RESTful/GraphQL/数据库 |
| API Test Pro | [s.trae.com.cn/a/1ea8bb](https://s.trae.com.cn/a/1ea8bb) | 契约/功能/性能/安全测试 |
| AI Integration Eng | [s.trae.com.cn/a/16c32c](https://s.trae.com.cn/a/16c32c) | AI/ML 集成 |
| DevOps Architect | [s.trae.com.cn/a/bab503](https://s.trae.com.cn/a/bab503) | CI/CD/IaC/监控 |
| Performance Expert | [s.trae.com.cn/a/7bb287](https://s.trae.com.cn/a/7bb287) | 性能测试/优化 |
| Compliance Checker | [s.trae.com.cn/a/7a3bf7](https://s.trae.com.cn/a/7a3bf7) | 法律合规审查 |

**推荐组合**（excel-to-diagram 项目）：
- Backend Architect（已有 Flask 后端）
- DevOps Architect（v5.0 服务治理）
- API Test Pro（E2E 测试）

---

## 3. 本项目 v5.3 创建的 4 个 .md Subagent（提示词文档）

| 文件 | 触发场景 | 工具 |
|------|---------|------|
| `code-reviewer.md` | 用户要求代码审查 | Read, Glob, Grep |
| `unit-test-writer.md` | 用户要求生成/补单测 | Read, Write, Edit, Bash |
| `project-guide.md` | 用户询问项目结构/规范 | Read, Glob, Grep |
| `security-auditor.md` | 用户要求安全审计 | Read, Glob, Grep |

**处理建议**：
- ✅ **保留**：作为提示词参考 + 未来在 UI 创建时复用
- 🔄 **升级**：把每个 .md 的核心内容复制到 IDE UI 创建的 Subagent 中

---

## 4. 触发机制

1. 用户发送消息 → 主 "Agent" 判断任务类型
2. 匹配 Subagent 的 `when_to_call`（何时调用）字段
3. Subagent 在**独立上下文**中执行（不污染主对话历史）
4. 返回结果给主 "Agent" 汇总

**目前仅 SOLO Agent 可调用 Subagent**（v5.4 限制）。

---

## 5. 前置条件

- IDE 模式 → 设置 → **Beta** → 打开 "**启用 Subagents 目录**" 开关
- 仅 SOLO 模式支持调用 Subagent

---

## 6. 参考

- [docs.trae.cn/ide/agent](https://docs.trae.cn/ide/agent) —— 创建并管理智能体
- [docs.trae.cn/ide/solo-coder](https://docs.trae.cn/ide/solo-coder) —— SOLO Agent（含 Subagent 调用）
- v5.4 深度研究：[2026-09-02-trae-ide-v5.4-deep-research.md](../../../excel-to-diagram/docs/governance/2026-09-02-trae-ide-v5.4-deep-research.md)
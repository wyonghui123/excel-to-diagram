---
title: 规范文档场景化重构 v5.0
date: 2026-09-02
status: 完成
author: AI Assistant
related: 2026-09-02-rules-simplification-v4.0.md, 2026-09-02-rules-qc-round2.md, 2026-09-02-service-governance-v5.md
---

# 规范文档场景化重构 v5.0

> **背景**：用户提出"规范文档的组织方式，是否分场景会更合适？"并列出 7 个候选场景：远程服务器运维、部署、本地服务器管理、Git、开发、测试验证问题排查、其他。本文记录从扁平主题分类迁移到 8 个场景子目录的完整过程。

---

## 1. 治理前现状（v4.0 主题分类）

```
.trae/rules/
├── (59 个根目录文件, 按主题分组)
│   ├── Worktree / Git / 开发流 (7)
│   ├── 测试 / 调试 (6)
│   ├── 前端 / 组件 / UI (8)
│   ├── 后端 / 元模型 / 服务 (7)
│   ├── PowerShell / 命令行 (2)
│   ├── 协作 / 多 Agent (3)
│   ├── 编码 / 安全 (8)
│   ├── 测试细节 (5)
│   └── 文档 / 元 (4)
└── core/ (7 个编码文件)
```

**问题**：
1. **跨主题分类**：同一文件可能属多个主题
2. **AI 找不到**：面对任务时无法快速定位
3. **抽象层级错位**：按"代码模块"分类，但 AI 按"任务类型"思考

---

## 2. 用户提出的 7 个场景（+ 1 个补充）

| # | 场景 | 文件数（实施前估算） |
|---|------|---------------------|
| 1 | 远程服务器运维 | 4 |
| 2 | 部署 | 4 |
| 3 | 本地服务器管理 | 4 |
| 4 | Git | 3 |
| 5 | 开发（编码/组件/UI） | 26 |
| 6 | 测试验证问题排查 | 23 |
| 7 | 其他 | 7 |

**实施过程中发现 7 太大，拆为两个场景**：
- 7. **AI 协作 / 多 Agent** — 多 agent 协调
- 8. **Trae 平台 / 元规则** — PowerShell + Trae IDE

---

## 3. v5.0 场景化架构

### 3.1 新结构

```
.trae/rules/
├── START_HERE.md                       # 入口决策树
├── IRON-RULES-CHEATSHEET.md            # 铁律卡片
├── RULES_INDEX.md                      # 场景导航索引
├── SESSION_REMINDER.md                 # 会话提醒
├── scenarios/                          # 🆕 8 个场景子目录
│   ├── 1-remote-server-ops/            # 远程服务器运维 (4 文件)
│   ├── 2-deploy/                       # 部署 (3 文件)
│   ├── 3-local-server-mgmt/            # 本地服务器管理 (4 文件)
│   ├── 4-git/                          # Git (3 文件)
│   ├── 5-development/                  # 开发 (25 文件)
│   ├── 6-test-debug/                   # 测试验证 (23 文件)
│   ├── 7-ai-collaboration/             # AI 协作 (1 文件)
│   └── 8-meta-trae/                    # Trae 平台 (3 文件)
└── .deprecated/                        # 废弃 (8 文件)
```

### 3.2 每个场景子目录的标配

- `README.md` — 场景说明 + 必读文件 + 完整清单 + 关联场景
- 文件移动按"主导场景"分类
- 每个 README 都有 task keywords → AI 可关键词匹配

### 3.3 根目录精简到 4 个入口文件

| 文件 | 作用 |
|------|------|
| `START_HERE.md` | 30 秒决策树 |
| `IRON-RULES-CHEATSHEET.md` | 9 条铁律卡片 |
| `RULES_INDEX.md` | 8 场景导航 |
| `SESSION_REMINDER.md` | 4 大铁律 + 调试工具集 |

---

## 4. 8 场景详细分类

### 4.1 场景 1: 远程服务器运维 (4 文件)
- `remote-server-alert-avoidance.md` — 远程运维告警规避
- `staging-process-guardian.md` — Staging 进程守护
- `postmortem-2026-09-02-staging.md` — 事故复盘
- `server-management.md` — 服务管理基础

### 4.2 场景 2: 部署 (3 文件)
- `release-sync-workflow.md` — Release 同步
- `parallel-dev-sop-v33.md` — 并行发布 SOP
- `efficient-commit-workflow.md` — 高效 commit

### 4.3 场景 3: 本地服务器管理 (4 文件)
- `service-management-v5.md` — 服务管理 v5.0（**单一入口**）
- `service-management-rules.md` — 服务管理 v3（**已废弃，保留兼容**）
- `project_startup.md` — 项目启动
- `core-service-architecture.md` — 核心服务架构

### 4.4 场景 4: Git (3 文件)
- `worktree-governance.md` — Worktree 治理 v4.0
- `git-commit-message.md` — Commit message 格式
- `git-commit-standards.md` — Conventional Commits

### 4.5 场景 5: 开发 (25 文件)
- `development-workflow.md` — 开发工作流 v4.0
- 组件治理（4）：`AI_AGENT_COMPONENT_GUIDE.md` / `ai-component-{reference,templates,checklist}.md` / `component-governance.md` / `component-{lifecycle,rules,config}.md`
- 编码（5）：`coding-standards.md` / `agent-roles.md` / `checklist.md` / `component-layers.md` / `ui-standards.md`
- 元模型（2）：`meta-model-schema-sync.md` / `audit-compliance.md`
- 编码（4）：`encoding-prevention.md` / `file-encoding-rules.md` / `ai-content-protection.md` / `ai-agent-undo-protection.md`
- 上下文（4）：`context-usage.md` / `agent-bootstrap.md` / `doc-sync-rules.md` / `project_rules.md`
- 其他（1）：`engineering-guidelines.md`

### 4.6 场景 6: 测试验证问题排查 (23 文件)
- 测试总览（3）：`test_rules.md` / `e2e-testing.md` / `e2e-simplification.md`
- 前端测试（4）：`frontend-testing-standards.md` / `frontend-test-auth.md` / `browser-test-verification.md` / `page-health-rules.md`
- 调试基础设施（2）：`debug-infrastructure-onboarding.md` / `debug-infrastructure-v20260621.md`
- 测试用例（5）：`test-case-standards.md` / `test-case-{design,runtime,excel,checklist}.md`
- 测试细节（4）：`test-data-rules.md` / `test-observability-rules.md` / `test-runner-template.md` / `test-script-quality-analysis.md`
- Vitest（2）：`vitest-setup.md` / `vitest-debugging.md`
- 调试（3）：`form-debugging.md` / `scope-tree-debugging.md` / `e2e-testing.md`

### 4.7 场景 7: AI 协作 / 多 Agent (1 文件)
- `multi-agent-coordination.md` — 多 Agent 协调 v4.0（13 铁律）

### 4.8 场景 8: Trae 平台 / 元规则 (3 文件)
- `powershell-execution-guide.md` — PowerShell 执行
- `powershell-curl-alias.md` — curl 别名
- `trae-tips-from-forum.md` — Trae 论坛技巧

---

## 5. 关键优势

| 维度 | v4.0 | v5.0 |
|------|------|------|
| **组织方式** | 按主题（前端/后端/测试） | **按场景（任务驱动）** |
| **查找路径** | 4-5 跳（看主题 → 看文件 → 猜相关） | **1-2 跳（任务 → 场景 → 文件）** |
| **AI 友好度** | 中（AI 要"找主题"） | **高（任务 → 关键词匹配 → 场景）** |
| **多 Agent 支持** | 弱（所有 Agent 都看全部 59 文件） | **强（Agent 只读相关场景 1-3 个目录）** |
| **入口清晰度** | START_HERE + IRON + INDEX | **同左（4 文件）+ 8 场景 README** |
| **新场景扩展** | 加主题分组 | **新建 scenarios/X-xxx/ 目录** |

---

## 6. 关键经验教训

1. **场景化必须配套重写 README**：每个场景目录的 README 是 AI 的"二级决策树"，**没有它场景化就白做**
2. **根目录精简到 4 文件**：START_HERE / IRON-RULES-CHEATSHEET / RULES_INDEX / SESSION_REMINDER 之外，**不放任何规范**
3. **场景数量 ≤ 10**：8 个场景足够覆盖所有任务；超过 10 个会让 AI 选择困难
4. **每个场景有主导词**：README 的"何时进入"必须有清晰关键词（如"staging 挂了"、"端口起不来"）
6. **路径变化要兼容**：所有内部链接更新到新路径，**不能留死链**（已用 Grep 验证）

---

## 7. CHANGELOG

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-09-02 | v5.0 | 场景化重构：59 扁平 → 8 场景子目录（66 文件）|
| 2026-09-01 | v4.0 | 精简索引（340 → 130 行）|
| 2026-09-01 | v4.0 | 任务画像决策树（11 任务类型）|
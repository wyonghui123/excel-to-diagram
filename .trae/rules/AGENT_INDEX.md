# AGENT_INDEX - 5 分钟定位任何规范 (按任务分类)

> **唯一入口** - 不按文档类型，按 **"我要做什么"** 分类。
>
> **创建**: 2026-07-04 | **维护**: dev-agent
> **替代**: 旧 `RULES_INDEX.md`（按文档分类的索引，已弃用）
>
> **重要提示**:
> - 本文件位于项目分支内 (`.trae/rules/AGENT_INDEX.md`)
> - 引用文件使用相对路径，**必须在仓库根目录执行才有效**
> - 跨 worktree / 跨全局规则时使用绝对路径

---

## 🚀 我是新 Agent (5 步快速开始)

| 步骤 | 操作 | 文档 (相对路径) |
|------|------|----------------|
| 1 | 读 SESSION_REMINDER 速查 4 铁律 | `.trae/rules/SESSION_REMINDER.md` |
| 2 | 读项目内 AGENT_GUIDELINES (6 件事 + 10 DO NOT) | `AGENT_GUIDELINES.md` (项目根) |
| 3 | 读 PARALLEL_DEV_SOP 完整流程 (8 阶段) | `PARALLEL_DEV_SOP.md` (项目根) |
| 4 | 读最近的 HANDOVER (V043/V044 实际案例) | `DEPLOY_HANDOVER_BUG_V0*.md` (项目根) |
| 5 | 写 spec.md (cp spec_template.md) | `spec_template.md` (项目根或 d:\filework\) |

**禁止事项**: 不要读 `.deprecated/`、`RULES_INDEX.md` (按文档分类已弃用)。

**全局规范** (跨项目生效): `d:\filework\.trae\rules\`

---

## 🔨 我要做开发任务 (dev-agent)

| 任务 | 必读文档 |
|------|----------|
| **理解 dev-agent 完整工作流** | `d:\filework\.trae\rules\development-workflow.md` |
| **跑并行 + 集成 (8 阶段 SOP)** | `PARALLEL_DEV_SOP.md` (项目根) |
| **写 HANDOVER 文档** | `.trae/templates/DEPLOY_HANDOVER.template.md` |
| **了解 spec.md 白名单** | `.trae/rules/multi-agent-coordination.md` § L4 |
| **学习编码规范** | `.trae/rules/core/coding-standards.md` |
| **UI 样式规范** | `.trae/rules/core/ui-standards.md` |
| **了解项目设计原则** | `.trae/rules/core/agent-roles.md` |

---

## 🚢 我要部署 / 集成

| 任务 | 必读文档 |
|------|----------|
| **SOP 阶段 4-6 (integration + 主服务)** | `PARALLEL_DEV_SOP.md` § 4-6 (项目根) |
| **服务管理命令** | `.trae/rules/service-management-rules.md` |
| **核心 server 管理规范** | `.trae/rules/core/server-management.md` |
| **了解 release 工作流** | `d:\filework\.trae\rules\release-sync-workflow.md` |
| **写 HANDOVER (开发智能体)** | `.trae/templates/DEPLOY_HANDOVER.template.md` |
| **看 HANDOVER 历史案例 (PM)** | `DEPLOY_HANDOVER_BUG_V043.md`, `DEPLOY_HANDOVER_BUG_V044.md` (项目根) |

**关键脚本**:
- `scripts/service_manager.ps1` - 统一服务管理
- `scripts/start.ps1` - 启动包装
- `scripts/build-deploy-package.sh` - 部署打包 (唯一)
- `scripts/sync-integration-db.ps1` - integration DB 同步 (8 步 + 备份)
- `scripts/check_rules_consistency.py` - 规范一致性检查 (新增)

---

## 🐛 我要调试

| 任务 | 必读文档 |
|------|----------|
| **调试铁律 (4 必跑 + 5 禁止 + 5 必做)** | `.trae/rules/debug-infrastructure-onboarding.md` |
| **完整调试规范** | `.trae/rules/debug-infrastructure-v20260621.md` |
| **sandbox 安全调试** | `.trae/rules/sandbox-safe-debugging.md` |
| **表单渲染问题排查 (7 铁律)** | `.trae/rules/core/form-debugging.md` |

**关键工具** (`scripts/debug/`):
- `env/diagnose.py` - 综合诊断 (Step 1)
- `restart/restart_safe.py verify` - 后端状态 (Step 2)
- `log/extractor.py --pattern X --tail 50` - 日志提取 (Step 3)
- `inspect/user_context.py` - 用户上下文
- `inspect/table_schema.py --check-code-fields` - 字段映射
- `inspect/code_map.py --type reference` - 代码引用

---

## 🤖 我要做多 Agent 协作

| 任务 | 必读文档 |
|------|----------|
| **L1-L6 沙箱检测** | `.trae/rules/multi-agent-coordination.md` |
| **基础设施 V2.1 (13 铁律)** | `.trae/rules/multi-agent-infrastructure-v20260620-v2.md` |
| **E2E 简化方案** | `.trae/rules/e2e-simplification.md` |
| **Agent Bootstrap 5 步** | `.trae/rules/agent-bootstrap.md` |

**铁律速查**:
- **L1** Worktree: 必须 `agent_bootstrap.ps1`
- **L2** NoMain: 禁主工作树 commit/stash
- **L3** NoStash0: 禁碰 `stash@{0}` (用变量转!)
- **L4** Status: commit 前看 `.agent-status.json`
- **L5** Port: 用 3011-3019 不用 3010
- **L6** Service: 禁动主 3006/3011

---

## 🧪 我要写测试

| 任务 | 必读文档 |
|------|----------|
| **E2E 核心经验 (12 条 CRITICAL)** | `.trae/rules/core/e2e-testing.md` |
| **E2E 完整规范 (v2 简化)** | `.trae/rules/e2e-simplification.md` |
| **测试铁律 (test_rules)** | `.trae/rules/test_rules.md` |
| **测试数据规范 (D01-D08)** | `.trae/rules/test-data-rules.md` |
| **测试可观测性** | `.trae/rules/test-observability-rules.md` |

**铁律**:
- 禁止 `pytest` → 必须 `python d:\filework\test.py`
- 禁止 `npm run dev` / `python dev.py` → 必须 `service_manager.ps1`
- PowerShell `curl` 是 `Invoke-WebRequest` 别名 → 用 `curl.exe`

---

## 🎨 我要做 UI / 样式

| 任务 | 必读文档 |
|------|----------|
| **YonDesign 设计规范** | `.trae/rules/core/ui-standards.md` |
| **设计决策清单** | `src/styles/DESIGN_CHECKLIST.md` |
| **设计常量** | `src/styles/YON_DESIGN_CONSTANTS.md` |
| **EP 组件指南** | `src/styles/YON_EP_GUIDE.md` |
| **三层组件架构** | `.trae/rules/core/component-layers.md` |
| **组件治理** | `.trae/rules/component-governance.md` |

**组件选择决策树**:
```
业务对象页面? → MetaListPage / DetailPage (YAML 驱动)
需要自定义组件? → App* 基础组件
需要业务逻辑? → Meta* 业务组件
```

---

## 🔧 我要做 PowerShell 操作

| 任务 | 必读文档 |
|------|----------|
| **PowerShell 完整规范** | `.trae/rules/powershell-execution-guide.md` |
| **PowerShell 语法速查** | `.trae/rules/powershell-curl-alias.md` |
| **终端交互 prompt** | `.trae/rules/terminal-interactive-prompt.md` |

**3 大铁律**:
1. 禁 `curl` → 用 `curl.exe` / `Invoke-RestMethod`
2. `stash@{0}` 必须用变量: `$r='stash@{0}'; git stash show $r`
3. `head -N` 不存在 → 用 `Select-Object -First N`

---

## 🔍 我要检查规范一致性

| 任务 | 命令 |
|------|------|
| **死链/双版本/过期引用** | `python scripts/check_rules_consistency.py` |
| **仅死链** | `python scripts/check_rules_consistency.py --deadlinks` |
| **CI 严格模式** | `python scripts/check_rules_consistency.py --strict` |

---

## 📚 我要查规范目录 / 历史

| 任务 | 必读文档 |
|------|----------|
| **当前生效规范 (active/)** | `.trae/rules/active/` (备用) |
| **历史归档 (archive/)** | `.trae/rules/archive/` (备用) |
| **废弃规范 (.deprecated/)** | `.trae/rules/.deprecated/` (禁止作为参考) |
| **规则演进历史** | `.trae/rules/active/CHANGELOG.md` (备用) |
| **全局规范** | `d:\filework\.trae\rules\` (跨项目) |

---

## 🚨 出错时

| 错误 | 解决方案 |
|------|----------|
| 找不到 `RULES_INDEX.md` 引用的文件 | RULES_INDEX.md 已弃用, 用本 AGENT_INDEX.md |
| 找不到 `AGENT_GUIDELINES.md` | 在项目根目录 `AGENT_GUIDELINES.md` |
| `agent_bootstrap.ps1` 不存在 | 手动 `git worktree add -b <branch> ../<wt>` |
| pre-commit 缺 spec.md | `cp spec_template.md ./spec.md` |
| pre-commit 缺 L1/L2/L3 | commit message 头部加 `L1-Worktree: yes` 等 |
| 浏览器测试想用 MCP | **[X] 禁止** - 改用 `PlaywrightCLI` |

---

## 📋 5 分钟完整路径

```
新 Agent
  ↓
SESSION_REMINDER (4 铁律)         ← .trae/rules/SESSION_REMINDER.md
  ↓
AGENT_GUIDELINES (6 件事)         ← AGENT_GUIDELINES.md (项目根)
  ↓
PARALLEL_DEV_SOP (8 阶段)          ← PARALLEL_DEV_SOP.md (项目根)
  ↓
最近 HANDOVER (V043/V044)          ← DEPLOY_HANDOVER_BUG_V0*.md (项目根)
  ↓
开始任务
```

---

## 维护规则

- **本文件是唯一索引入口** - RULES_INDEX.md 已弃用
- **新增规范时**: 加到对应任务分类下，不要新开"按文档类型"分类
- **每月检查**: `python scripts/check_rules_consistency.py` 检测死链/双版本
- **跨 worktree 引用**: 用 `d:\filework\...` 绝对路径并加注 "全局" 或 "项目根"

---

**创建**: 2026-07-04
**版本**: v1.1 (修复 v1.0 中 5 个死链引用)
**作者**: dev-agent
**替代**: 旧 RULES_INDEX.md

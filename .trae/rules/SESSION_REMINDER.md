---
alwaysApply: true
description: "项目铁律入口 - pytest禁止、服务管理、curl陷阱、PowerShell兼容、踩坑速查"
---

# 全局规则入口（精简版 v2026.06.20）

> **本文件是 AI Agent 会话必读入口。仅保留铁律标题，示例/细节见引用文件。**
>
> **v3 (2026-06-21)**: 所有规则默认假设**执行者是 AI Agent**（不是人类），措辞已调整。
>
> **v4 (2026-06-21)**: 新增 **调试铁律**（27 → 28），引用 V1 调试基础设施。

---

## [!!!] 铁律 1：禁止直接运行 pytest [!!!]

> **AI Agent 任何时候禁止 `pytest`、`python -m pytest`**
> **唯一合法入口：`python d:\filework\test.py`**
> **硬阻断：conftest.py 检测 TEST_ENTRY=1，未通过则 os._exit(1)**

详情/示例/状态机：`.trae/rules/test_rules.md`

---

## [!!!] 铁律 2：前后端服务必须用 service_manager [!!!]

> **AI Agent 禁止直接用 `npm run dev` / `python dev.py` / `Get-Process` / `taskkill` 管理服务**
> **唯一入口：`powershell -File scripts\service_manager.ps1 [status|start|stop|restart]`**

原因：sandbox 隔离、跨 Agent 不可见、端口冲突、终端占用。
详情：`.trae/rules/service-management-rules.md`

---

## [!!!] 铁律 3：PowerShell 中 `curl` 是别名陷阱 [!!!]

> **`curl` = `Invoke-WebRequest`，会卡死！**
> **必须用 `curl.exe` 或 `Invoke-RestMethod` 或 Python urllib**

详情：`powershell-execution-guide.md` § 5.1

---

## [!!!] 铁律 4：调试基础设施强制使用 [!!!]

> **调试前必跑 6 步**：`scripts/debug/env/diagnose.py` + `scripts/debug/restart/restart_safe.py verify`
> **调试中禁止 5 件事**：手动 taskkill、git diff > file、echo > file、反复 Read backend.out 全文、反复查 user_roles
> **调试后必做 5 件事**：`scripts/debug/verify/run_interceptor_tests.sh` + 清理 DEBUG 代码 + `check_fix_completeness.py` + 写 `.trae/debug/sessions/*.yaml` + 决策日志

7 大工具：
- `scripts/debug/log/extractor.py` - 日志提取（关键字/级别/时间窗口）
- `scripts/debug/inspect/user_context.py` - 用户上下文查询
- `scripts/debug/inspect/table_schema.py` - 表结构 + 字段映射错误检测
- `scripts/debug/inspect/code_map.py` - 代码地图快速定位
- `scripts/debug/restart/restart_safe.py` - 安全重启（杀所有 waitress）
- `scripts/debug/env/diagnose.py` - 综合诊断（一次性回答 10+ 问题）
- `scripts/debug/verify/run_interceptor_tests.sh` - 一键验证

详情：`.trae/rules/debug-infrastructure-v20260621.md`

---

## 快速路由表

| 任务 | 行动 |
|------|------|
| pytest 测试 | `python d:\filework\test.py`（详见 test_rules.md）|
| 问题修复（多会话）| invoke `problem-fixing` Skill |
| E2E 测试 | invoke `e2e-testing` Skill |
| 浏览器验证 | `PlaywrightCLI` (test_helpers/browser_auth_cli.py) |
| **调试前** | `python scripts/debug/env/diagnose.py` |
| **调试日志** | `python scripts/debug/log/extractor.py --pattern X --tail N` |
| **重启后端** | `python scripts/debug/restart/restart_safe.py restart` |
| **代码定位** | `python scripts/debug/inspect/code_map.py --topic X` |
| 服务管理 | `service_manager.ps1 [status\|start\|stop\|restart]` |
| PowerShell + Git 兼容 | 详见 powershell-execution-guide.md |
| trae-sandbox 行为 | 详见 powershell-execution-guide.md Part 1-2 |

---

## v3.18: AI Coding Agent 友好测试要点

- **`--single <test_id>`** < 5s 快速反馈（跳过 DB 快照/锁）
- **`--failed`** 修复后必跑，不要跑 `--all`
- **多 Agent 端口隔离**：3010-3019（AGENT_PORT env）
- **认证**：跨进程必须 cookie（httpOnly + auth_token），**禁 Bearer**
- **`/diagnostics`** admin 端点给 AI Production Diagnostician 用
- **🆕 v3.21 (2026-06-21) 决策日志**：任何规则边界判断前必须输出决策日志
  - 工具：`python scripts/decision_log.py violate --rule-id iron-X --reason "..." --alternatives "..."`
  - 5+ 次 PM 授权 → 触发规则体检

详情：`.trae/rules/test_rules.md`

---

## 18 条常见踩坑速查（精简版）

- **[X] pytest** → 必须用 `python test.py`
- **[X] npm run dev / python dev.py** → 必须用 service_manager.ps1
- **[X] curl** → 必须用 `curl.exe` / `Invoke-RestMethod` / Python
- **[X] Bearer token 跨进程** → 必须 cookie（httpOnly + dev-login）
- **[X] --all 后不 --failed** → 误判并发假失败
- **[X] 修复后 --all** → 浪费时间，跑 --failed
- **[X] DB 直接读写** → test.py 自动快照保护，严禁绕过
- **[X] 多会话修同一任务** → 必须 fix_tasks claim
- **[X] 浏览器测试盲猜"版本问题"** → 页面崩溃了，Fail-Fast
- **[X] console.error 忽略** → check_health() 自动汇总
- **[X] 直接 python tests/e2e/xxx.py** → 必须 `python test.py --file`
- **[X] 路径混用 `tests\e2e\`** → 统一 `tests/e2e/`
- **[X] PS 重定向 `2>&1 1>file`** → 用 `*> file`
- **[X] PS 中 `stash@{0}`** → 被拆！必须 `$r='stash@{0}'`
- **[X] PS 中 `head -100`** → 不存在！用 `Select-Object -First 100`
- **[X] PS 中 `Out-File` / `Set-Content`** → trae-sandbox 假成功，用 Write 工具
- **[X] echo > file** → 假成功，必须用 Write 工具
- **[X] service_manager.ps1 restart -Force** → 参数不存在，用 `force-restart`

完整 37 条速查表：`.trae/rules/RULES_INDEX.md`

---

## 项目特定规则（按工作目录）

**`d:\filework\excel-to-diagram` 项目必读：**

| 规则文件 | 用途 | 重要度 |
|---------|------|--------|
| `test_rules.md` | pytest 详细规则 + test.py 用法 | 必读 |
| `powershell-execution-guide.md` | trae-sandbox + PowerShell 整合规范 | 必读 |
| `multi-agent-coordination.md` | 端口隔离 + worktree + 资源监控 | 必读 |
| `service-management-rules.md` | service_manager 详细用法 | 必读 |
| `test-script-quality-analysis.md` | 测试脚本质量分析 | 推荐 |
| `page-health-rules.md` | 四层错误检测机制 | 推荐 |
| `test-data-rules.md` | fixture 使用方法 | 推荐 |
| `frontend-test-auth.md` | 前端认证规范 | 推荐 |
| `browser-test-verification.md` | 浏览器验证方法 | 推荐 |
| `e2e-testing.md` | E2E 测试规则 | 推荐 |
| `test-case-standards.md` | 测试用例编写规范 | 推荐 |
| `test-observability-rules.md` | 可观测性规范（分批/实时）| 推荐 |
| `frontend-testing-standards.md` | 前端测试标准（Vitest + MSW）| 推荐 |
| `efficient-commit-workflow.md` | 高效 commit 工作流 | 推荐 |

完整索引：`.trae/rules/RULES_INDEX.md`

---

## 状态机：test.py 工作流

```
idle → --all → passed (全部通过)
idle → --all → needs_rerun → --failed → passed / fixing → --failed → ...
```

**修复后必跑 `--failed`，不要跑 `--all`。**

---

_本文件是全局规则入口，所有工作目录的智能体都会读取_
_精简版 (2026-06-20): 230 行 → 130 行 (-43%)，节省 ~1,300 Token/会话_
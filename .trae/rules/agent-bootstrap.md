# [AGENT-BOOTSTRAP] AI Agent 启动强制前置检查 (autoload)

> **本规则由 Trae IDE 在 Agent 启动时自动注入。**
> **每个 AI Coding Agent 启动后必读，并按顺序执行 5 步检查。**
>
> 版本: v3.18.5+ | 创建: 2026-06-14

---

## [CRITICAL] 为什么需要这份规则

2026-06-14 实测两个 Agent 并行运行时发现的问题：

| 问题 | 后果 | 自动防护位置 |
|------|------|-------------|
| 两个 Agent 都用默认 3010 端口 | DB 快照互踩、Lock 互锁 | `test.py` / `agent_test.py` 自动分配 |
| Agent 直跑 `npx playwright test` | 绕开 `test.py --file` 入口 | 后续 `agent_run.ps1` 拦截 |
| Agent 没跑 `service_manager status` | 端口被占 / 服务过期 | `test.py` preflight 检查 |
| Agent 跑 `--all` 后不跑 `--failed` | 并发假失败误判 | 本规则强制要求 |

---

## [REQUIRED] 启动 5 步检查（Agent 接到任务后立即执行）

### Step 1: 分配端口 (AGENT_PORT)

```powershell
# 检查是否已设
if (-not $env:AGENT_PORT) {
    # 让 test.py / agent_test.py 自动分配 (优先 3011-3019)
    # 或手动设: $env:AGENT_PORT = 3011
    $env:AGENT_PORT = 3011
    Write-Host "[AGENT] 使用端口 $env:AGENT_PORT"
}
```

**禁止**: 不设 `AGENT_PORT` 直接跑测试 (会 fallback 3010，跟其他 Agent 冲突)

### Step 2: 服务检查

```powershell
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 status -Port $env:AGENT_PORT
```

**判定**:
- `Summary: ALL SERVICES HEALTHY` → 继续
- `SOME SERVICES NOT RUNNING` → `service_manager.ps1 start -Port $env:AGENT_PORT`
- 服务过期 (started_at > 5min 前) → `service_manager.ps1 restart -Port $env:AGENT_PORT`

### Step 3: 走 test.py 统一入口 (禁止直跑 pytest)

```powershell
# [OK] 正确 (推荐)
python d:\filework\test.py --port $env:AGENT_PORT --single <test_id>
python d:\filework\test.py --port $env:AGENT_PORT --file <path>
python d:\filework\test.py --port $env:AGENT_PORT --all --force
python d:\filework\excel-to-diagram\scripts\agent_test.py --port $env:AGENT_PORT --single <test_id>

# [X] 禁止 (conftest.py 硬阻断 _block_unguarded_entry 会 os._exit(1))
pytest meta/tests/
python -m pytest meta/tests/

# [X] 禁止 (绕开 test.py 入口, 缺进度追踪/DB 快照)
npx playwright test e2e/xxx.spec.js
```

### Step 4: --all 跑完后必须 --failed 验证

```powershell
# 1. 跑全量 (并行, 可能有假失败)
python d:\filework\test.py --port $env:AGENT_PORT --all --force

# 2. 必须跑串行验证 (last-failed, 排除并发假失败)
python d:\filework\test.py --port $env:AGENT_PORT --failed
```

**禁止**: 跑完 `--all` 直接结束，必须 `--failed` 串行复核。

### Step 5: 提交前清理

```powershell
# 检查 stash 残留
git stash list
# 状态确认
git status
```

---

## [REQUIRED] 多 Agent 并行场景

### 端口分配表 (D.7 规范)

| Agent | 前端 | 后端 | AGENT_PORT | 工作目录 |
|-------|------|------|------------|----------|
| Agent 1 (主) | 3004 | 3010 | 3010 | 主仓库 |
| Agent 2 | 3014 | 3020 | 3011 | worktree 或同仓库 |
| Agent 3 | 3024 | 3030 | 3012 | worktree 或同仓库 |
| ... | ... | ... | 3013-3019 | ... |

**规则**:
- 每个 Agent 间隔 10 个端口 (3004/3014/3024, 3010/3020/3030)
- AGENT_PORT 用 3010-3019 (test.py / agent_test.py 的合法范围)
- worktree 由 Agent 自管 (业界共识)

### 并行冲突检测 (test.py 自动)

`test.py` 和 `agent_test.py` 已自动分配端口 (P0 v3.18.5+):
- 优先 3011-3019 (3010 留给主 Agent)
- 全占 → fallback 3010 + WARNING
- 进程内复用同一端口 (会话连续性)

---

## [REFERENCE] 服务管理命令速查

| 场景 | 命令 |
|------|------|
| 查看状态 | `powershell -File scripts/service_manager.ps1 status -Port $env:AGENT_PORT` |
| 启动服务 | `powershell -File scripts/service_manager.ps1 start -Port $env:AGENT_PORT` |
| 停止服务 | `powershell -File scripts/service_manager.ps1 stop -Port $env:AGENT_PORT` |
| 重启服务 | `powershell -File scripts/service_manager.ps1 restart -Port $env:AGENT_PORT` |
| 服务新鲜度检查 | `powershell -File scripts/service_manager.ps1 preflight -Port $env:AGENT_PORT` |
| 列出所有锁 | `powershell -File scripts/service_manager.ps1 list-locks` |
| 清理 stale lock | `powershell -File scripts/service_manager.ps1 clear-stale-lock` |
| 强制重启 | `powershell -File scripts/service_manager.ps1 force-restart -Port $env:AGENT_PORT` |

**禁止**:
- 直跑 `npm run dev` / `python dev.py` (跨 Agent 不可见)
- 用 `Get-Process python` 判断状态 (sandbox 隔离)
- 用 `taskkill /F /IM python.exe` 野蛮杀进程
- `stop; start` 串联重启 (应用 `restart`)

---

## [REFERENCE] 测试入口速查

| 任务 | 命令 |
|------|------|
| 单测快速反馈 (<5s) | `python d:\filework\test.py --single <test_id>` |
| 单文件调试 | `python d:\filework\test.py --file <path>` |
| 全量测试 (并行) | `python d:\filework\test.py --all --force` |
| 串行验证失败 | `python d:\filework\test.py --failed` |
| 仅单元测试 | `python d:\filework\test.py --unit` |
| Agent JSON 输出 | `python scripts\agent_test.py --single <test_id> --json results.json` |
| 查询上次状态 | `python d:\filework\test.py --status` |

---

## [REFERENCE] 常见踩坑速查 (继承自 SESSION_REMINDER.md)

| # | 禁止 | 后果 | 正确做法 |
|---|------|------|---------|
| 1 | 直跑 `pytest` | conftest.py `_block_unguarded_entry` → `os._exit(1)` | 用 `python d:\filework\test.py` |
| 2 | PowerShell 用 `curl` | `Invoke-WebRequest` 别名卡死 | 用 `curl.exe` 或 `Invoke-RestMethod` |
| 3 | 路径混用反斜杠 | mojibake / 解析异常 | 统一正斜杠 `d:/filework/...` |
| 4 | 跑 `--all` 后不跑 `--failed` | 并发假失败误判 | 强制串行验证 |
| 5 | 不设 `AGENT_PORT` | 跟其他 Agent 冲突 | 走 test.py/agent_test.py 自动分配 |
| 6 | 绕开 `service_manager.ps1` | 跨 Agent 不可见 | 唯一服务管理入口 |
| 7 | Bearer token 鉴权 | 项目用 httpOnly cookie | 用 `requests.Session()` + dev-login |
| 8 | 直跑 `npx playwright test` | 绕开 test.py 入口 | 用 `test.py --file e2e/xxx.spec.js` |

---

## [WORKFLOW] Agent 完整工作流示例

```powershell
# ===== Agent 启动 =====
$env:AGENT_PORT = 3011

# Step 1: 服务检查 (本规则 Step 2)
powershell -File scripts/service_manager.ps1 status -Port $env:AGENT_PORT
# → 如果 STOPPED: powershell -File scripts/service_manager.ps1 start -Port $env:AGENT_PORT

# Step 2: 单测快速反馈 (本规则 Step 3)
python d:\filework\test.py --single meta/tests/xxx.py::test_xxx

# Step 3: 改完代码后回归 (本规则 Step 3+4)
python d:\filework\test.py --port $env:AGENT_PORT --file meta/tests/xxx.py
python d:\filework\test.py --port $env:AGENT_PORT --failed

# Step 4: 提交 (本规则 Step 5)
git add <files>
git commit -m "fix: <msg>"
git status  # 无意外修改
```

---

## [SEE-ALSO] 相关规则

- `SESSION_REMINDER.md` — 全局规则入口 (18 铁律 + 23 踩坑)
- `service-management-rules.md` — 服务管理详细规范
- `multi-agent-coordination.md` — 5 层隔离完整设计
- `e2e-testing.md` — E2E 测试规则
- `frontend-test-auth.md` — 前端认证规范 (Cookie / dev-login)
- `test-observability-rules.md` — 测试可观测性 (trace_id / metrics / diagnostics)

---

## CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-06-14 | AI Assistant | 创建本规则 (基于 P0 v3.18.5 自动端口分配落地) |
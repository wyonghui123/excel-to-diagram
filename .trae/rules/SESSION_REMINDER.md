# 全局规则入口

## [!!!] [!!!] [!!!] 铁律：禁止直接运行 pytest [!!!] [!!!] [!!!]

> **任何时候都禁止使用 `pytest`、`python -m pytest` 命令**
> 
> **唯一合法入口：`python d:\filework\test.py`**
> 
> 违规将导致：进度丢失、数据库污染、无法追踪问题
> 
> **已启用硬阻断：conftest.py 会在 `pytest_configure` 阶段检测 TEST_ENTRY=1 环境变量**
> - 未通过 test.py 入口 → `os._exit(1)` 立即终止
> - test.py 所有命令（--all / --failed / --skip / --file / --unit / --integration）自动设置 TEST_ENTRY=1

---

## 快速路由表

| 任务场景 | 行动 |
|---------|------|
| **pytest 测试** | 见下方铁律 + 项目级规则 `.trae/rules/test_rules.md` |
| **问题修复（多会话）** | invoke `problem-fixing` Skill（fix_tasks / claim / complete） |
| **E2E 测试** | invoke `e2e-testing` Skill |
| **MCP 前端验证** | invoke `mcp-frontend-testing` Skill |
| **前后端服务管理** | 见下方「服务管理」节（必须用统一管理器） |

---

## pytest 铁律

```bash
# [X] 绝对禁止
pytest meta/tests/
python -m pytest meta/tests/

# [OK] 唯一合法入口
python d:\filework\test.py --all --force
python d:\filework\test.py --failed
python d:\filework\test.py --skip
python d:\filework\test.py --unit
python d:\filework\test.py --integration
python d:\filework\test.py --status
python d:\filework\test.py --file <path>
# 🆕 v3.18: AI Coding Agent 友好参数
python d:\filework\test.py --single <test_id>      # 单测快速反馈 (< 5s, 跳过 DB 快照)
python d:\filework\test.py --port <port>           # 多 agent 端口隔离 (3010-3019)
python d:\filework\test.py --json <path>            # JSON 输出 (含 trace_id, 给 Agent 解析)
```

**关键规则：**
- `--all` 并行（-n4）有假失败 → 必须再跑 `--failed`（串行 -n0）确认
- 修复后跑 `--failed`，不要跑 `--all`（浪费时间）
- DB 保护：test.py 自动快照+校验，严禁直接读写 `meta/architecture.db`；`--failed` 阶段独立快照保护主 DB（2026-06-02 修复）
- DB 健康监控：Server 启动时初始化 `meta/core/db_health_monitor.py`，WAL > 1MB / pending frames > 100 / 并发访问 → 自动告警
- **DB 快照 WAL 保护（2026-06-02 修复）**：
  - `_create_db_snapshot()` / `_restore_db_snapshot()` 在复制前调用 `_checkpoint_db_wal()` 强制 flush WAL
  - `_preflight_auth_check()` 使用临时快照副本，不再写入生产DB
  - **快照恢复后如需重启服务**：DB 被替换后服务器仍持有旧WAL，必须 restart 清除
  - **快照清理（2026-06-07 修复）**：`_prune_snapshots()` 同时删除 `.db-shm` 和 `.db-wal` 残留文件
- 锁机制：`--all` 排他锁，`--failed` 共享锁，互斥等待最长 120s

## 状态机

```
idle → --all → passed (全部通过)
idle → --all → needs_rerun (有失败，可能并发假失败)
                ↓
           --failed → passed (假失败/已修复)
           --failed → fixing (真实错误)
                        ↓
                     修复 → --failed → passed / fixing
```

---

## 前后端服务管理（多 Agent 协作）

> **多智能体并行环境下，前后端启动/停止/重启必须使用统一管理器，禁止 Agent 直接操作终端或进程。**

### 核心问题

1. **sandbox 权限隔离**：Agent A 启动的进程，Agent B 的 `Get-Process` / `taskkill` 看不到
2. **终端槽位竞争**：最多 5 个终端，服务占用终端后其他 Agent 可用终端减少
3. **端口冲突**：Agent 不知道另一 Agent 已启动服务，重复启动导致端口冲突
4. **无状态可见性**：无法判断服务是否在运行

### 唯一入口

```bash
# 查看状态（任何 Agent 都可以随时调用）
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 status

# 启动前后端（幂等：已运行则跳过）
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 start

# 停止前后端
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 stop

# 重启
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 restart
```

### 设计保证

| 特性 | 机制 |
|------|------|
| 跨 Agent 状态可见 | `.service_status.json` 磁盘文件（端口检测优先于 PID） |
| 并发管理保护 | `.service_manager.lock` 锁文件（120s 超时，残留 5min 清理） |
| 幂等操作 | start 检测到端口已监听 = no-op；stop 检测到端口已关闭 = no-op |
| 端口冲突避免 | netstat + TCP connect 双验证，不依赖 `Get-Process` |
| 终端槽位释放 | `Start-Process -WindowStyle Hidden` 不占用终端 |

### 禁止行为

- [X] 直接使用 `npm run dev:full` 或 `npm run dev` 或 `python dev.py` 管理服务
- [X] 用 `Get-Process python` 判断服务状态（sandbox 隔离不可靠）
- [X] 用 `taskkill /F /IM python.exe` 野蛮杀进程
- [X] 两个 Agent 同时 restart
- [OK] 先用 `status` 查询 → 按需 `start` / `stop` / `restart`

### 启动前检查清单

1. `powershell -File ... service_manager.ps1 status` — 确认当前状态
2. 如果服务已运行 → 不需要 restart（直接使用）
3. 如果服务未运行 → `start`
4. 如果代码有改动需要重启 → `restart`（自动 stop + start）

---

## 🆕 v3.18: AI Coding Agent 友好测试规范

> **AI Coding Agent 是测试基础设施的主要用户，测试需让 Agent 高效写/跑/修测试。**

### 快速反馈 (Fast Feedback)

- `--single <test_id>` 跳过 DB 快照/锁，< 5s 反馈单测结果
- **不** 适用于：需要 DB 完整状态/其他测试副作用的测试
- **适用**：Agent 改 1 行代码后立即验证

### 多 Agent 端口隔离 (D.7)

- 默认 3010；多 agent 并行时通过 `AGENT_PORT` 环境变量分配 3010-3019
- 每个 port 独立：DB snapshot / 锁 / server instance
- **worktree 由 Agent 自管**（业界共识）
- service_manager.ps1 start/stop/status 都支持 `--port` 参数

### 认证统一 (v3.17 cookie 规范)

- **统一用 httpOnly cookie**：`requests.Session()` + dev-login + `auth_token` cookie
- ~~Bearer token~~ 已被 SESSION_REMINDER 标为踩坑（项目用 cookie 鉴权）
- 注：meta/tests/shared/base.py 内部仍可用 Bearer（in-process 测试），但**跨进程必须 cookie**

### trace_id 端到端 (M.1)

- 每个请求 1 trace_id (UUID 32 char)
- 跨 subflow/audit/SSE 关联
- 响应 header `X-Trace-Id` 必返
- Agent 拿到 trace_id 可查询 `/_diagnostics`

### `/diagnostics` 端点 (M.5)

- `GET /api/v2/action/_diagnostics`（admin 权限）
- 给 AI Production Diagnostician 用：health + recent_errors + error_codes + recovery_suggestions
- 详见 `meta/api/diagnostics_api.py`

## [!!!] PowerShell 铁律：禁止使用 `curl` [!!!] [!!!]

> **在 PowerShell 中，`curl` 是 `Invoke-WebRequest` 的别名，不是真正的 curl！**
>
> `curl -s http://...` 会变成 `Invoke-WebRequest -s http://...`，**卡死在交互式等待**，永久占用终端。
>
> **正确做法：**
> ```powershell
> # [X] 绝对禁止 — 会卡死在交互式等待
> curl -s http://localhost:3010/api/v1/...
> curl http://localhost:3010/api/v1/...
>
> # [OK] 三种正确方式任选其一
> curl.exe -s http://localhost:3010/api/v1/...                           # 方式1：用 curl.exe（真实二进制）
> python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:3010/api/v1/...').read().decode())"  # 方式2：Python
> Invoke-RestMethod -Uri http://localhost:3010/api/v1/...                # 方式3：PowerShell 原生
> ```

---

## 常见踩坑

- [X] 直接在 PowerShell 中用 `curl`（是 `Invoke-WebRequest` 别名，会卡死！必须用 `curl.exe` 或 Python）
- [X] 直接 `pytest`（必须用 `python test.py` 入口）
- [X] `--all` 后不跑 `--failed`（误把并发假失败当真）
- [X] 修复后跑 `--all` 而非 `--failed`（浪费时间）
- [X] DB 被污染（未使用 TESTING 安全模式 / 绕过了快照保护）
- [X] 多个会话修同一任务（未认领）
- [X] 直接用 `npm run dev` 或 `python dev.py` 启停服务（未用 `service_manager.ps1`，导致跨 Agent 不可见）
- [X] 浏览器测试中页面白屏后盲猜"版本/数据问题"（页面已崩溃，应 Fail-Fast；`PlaywrightCLI` 已自动监听 pageerror/console/crash）
- [X] 浏览器测试中忽略 console.error（`check_health()` 自动汇总四层错误，详见 `browser-test-verification.md`）
- [X] 直接运行测试脚本 `python tests/e2e/xxx.py`（必须用 `python test.py --file tests/e2e/xxx.py`）
- [X] PowerShell 路径分隔符混用 `tests\e2e\`（统一用正斜杠 `tests/e2e/`）
- [X] PowerShell 重定向语法 `2>&1 1>file`（用 `*> file` 或 `2>&1 | Out-File`）
- [X] 使用 Bearer token 认证（项目用 httpOnly cookie 认证，应该用 `requests.Session()` + dev-login）
- [X] PowerShell 中用 `stash@{0}`（被当 script block 拆分！必须用变量 `$r='stash@{0}'`）
- [X] PowerShell 中用 `head -100`（不存在！用 `Select-Object -First 100`）
- [X] 沙箱隔离时执行 `git commit`（exit 0 但未落盘！先验证写权限，详见 L5 检测）
- [X] `service_manager.ps1 restart -Force`（参数不存在！用 `force-restart`）

---

## 项目特定规则

如果你的工作目录是 `d:\filework\excel-to-diagram`，**必须阅读项目级规则**：
- `.trae/rules/SESSION_REMINDER.md` — **项目规范入口（18 条铁律 + 37 条速查表）**
- `.trae/rules/test-script-quality-analysis.md` — 测试脚本质量分析、效率优化建议
- `.trae/rules/page-health-rules.md` — 页面健康检测规范、四层错误检测机制
- `.trae/rules/powershell-rules.md` — PowerShell 语法规范、Bash→PowerShell 速查表
- `.trae/rules/test-data-rules.md` — 测试数据管理规范、fixture 使用方法
- `.trae/rules/service-management-rules.md` — 服务管理规范、重启安全规则
- `.trae/rules/frontend-test-auth.md` — 前端测试认证规范
- `.trae/rules/browser-test-verification.md` — 浏览器测试验证方法 + 可观测性
- `.trae/rules/e2e-testing.md` — E2E 测试规则
- `.trae/rules/test-case-standards.md` — 测试用例编写规范
- `.trae/rules/test-observability-rules.md` — **测试可观测性规范（分批、实时输出、过程检查）**
- `.trae/rules/frontend-testing-standards.md` — **前端测试标准（Vitest + happy-dom + MSW + Source Map）**
- `.trae/rules/multi-agent-coordination.md` — **多 Agent 协作规范（端口隔离 + worktree + 资源监控）**

---

_本文件是全局规则入口，所有工作目录的智能体都会读取_

# AGENTS.md — excel-to-diagram 项目行为指引

> 本文件是跨 IDE 兼容的轻量级行为指引（Trae / Cursor / Claude Code 均可读取）。
> 详细规则见 `.trae/rules/` 目录。

## 核心铁律

### 1. 测试入口
- **禁止** `pytest` 或 `python -m pytest`
- **唯一合法入口**: `python d:\filework\test.py --failed` / `--all` / `--single` / `--file`
- `--all` 并行有假失败，必须再跑 `--failed` 串行确认

### 2. PowerShell 安全
- **禁止** `curl`（是 Invoke-WebRequest 别名，会卡死）→ 用 `curl.exe` 或 `Invoke-RestMethod`
- **禁止** `head` / `tail` / `grep` / `cat`（不存在）→ 用 `Select-Object` / `Select-String` / `Get-Content`
- Git `stash@{0}` 必须用变量包裹：`$stashRef = 'stash@{0}'`
- 路径统一用正斜杠 `/`

### 3. 服务管理
- **禁止** `npm run dev` / `python dev.py` 启停服务
- **唯一入口**: `powershell -File scripts/service_manager.ps1 start/stop/restart/status`
- **禁止** `Get-Process python` 判断状态（sandbox 隔离不可靠）
- **禁止** `taskkill /F /IM python.exe` 野蛮杀进程

### 4. 认证方式
- 项目用 **httpOnly cookie** 认证，不是 Bearer token
- 跨进程测试用 `requests.Session()` + dev-login

### 5. 数据库保护
- **严禁** 直接读写 `meta/architecture.db`
- DB 操作走 `batch_save` action
- 测试时 test.py 自动快照 + 校验

### 6. 多 Agent 协作
- 必须用 `scripts/agent_bootstrap.ps1` 创建独立 worktree
- **禁止** 在主工作树 commit（会导致其他 Agent 工作被 stash 回滚）
- 端口隔离：`AGENT_PORT` 环境变量（3010-3019）

## 技术栈

- **前端**: Vue 3 + TypeScript + Vite + Element Plus + Pinia
- **后端**: Python 3.11 + Flask + Waitress + SQLite
- **测试**: Vitest + MSW（前端）/ test.py + pytest（后端）/ Playwright（E2E）
- **脚本**: PowerShell 5.1（Windows）

## 目录结构

```
src/          前端源码（Vue 组件、API 层、状态管理）
meta/         后端源码（API 路由、核心逻辑、数据模型）
scripts/      运维脚本（service_manager、agent_bootstrap）
tests/        E2E 测试
meta/tests/   后端单元/集成测试
```

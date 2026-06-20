---
alwaysApply: false
description: "项目启动初始化：依赖安装、环境配置、首次运行"
---

# 项目启动规则

## [FAST] 唯一启动方式（强制）

### 一键启动（Agent / 人类 统一入口）

```powershell
# Windows - 唯一推荐命令
powershell -File scripts/start.ps1

# 强制重启（有代码改动后）
powershell -File scripts/start.ps1 -Force
```

**这是唯一的启动方式。** 无需记忆端口、无需关心服务是否已运行（自动检测）。

### 输出示例
```
  ============================================================
    Excel-to-Diagram  统一服务入口
  ============================================================

  [OK]  前后端均已在运行，无需重复启动
  ------------------------------------------------------------
  Status:
    Frontend (Vite)    : RUNNING  →  http://localhost:3004
    Backend  (Flask)   : RUNNING  →  http://localhost:3010
  ------------------------------------------------------------
  [READY]  打开浏览器: http://localhost:3004
```

### npm 命令（自动走统一入口，Agent 放心用）

```bash
npm run dev:full     # → start.ps1（前后端）
npm run dev          # → 仅前端（Vite）
npm run dev:python   # → service_manager.ps1 start-be（仅后端）
```

---

## [BUILD]️ 纵深防御架构（防 Agent 绕过）

```
任何 Agent 启动方式：
  npm run dev:full  ─┐
  npm run dev:python ─┤
  直接 python dev.py ─┼──→ 全部被拦截，引导到 service_manager
  直接 server.py    ─┘

  Layer 1: npm scripts 重定向 → service_manager
  Layer 2: dev.py / server.py 端口启动守卫 → 拒绝 + 引导
  Layer 3: 文档/提示全部指向统一入口
```

**核心组件：**

| 组件 | 路径 | 作用 |
|------|------|------|
| **start.ps1** | `scripts/start.ps1` | 统一启动包装器，Agent 唯一需要知道的命令 |
| **service_manager.ps1** | `scripts/service_manager.ps1` | 服务生命周期管理（status/start/stop/restart） |
| **watchdog.ps1** | `scripts/watchdog.ps1` | 服务守护进程，每30秒检测服务健康并自动修复 |
| **启动守卫** | `dev.py` + `meta/server.py` | 端口冲突检测 → 拒绝启动 + 引导到 service_manager |
| **端口配置** | `.env` | FLASK_PORT / VITE_DEV_PORT，service_manager 自动读取 |

---

## [TOOL] 服务架构

| 服务 | 端口 | 配置项 | 说明 |
|------|------|--------|------|
| **Vite 前端** | 3004（默认） | VITE_DEV_PORT | 开发服务器，代理 `/api/*` 到后端 |
| **Flask 后端** | 3010（默认） | FLASK_PORT | REST API + WebSocket |

> 端口可通过 `.env` 配置，`service_manager.ps1` 和 `start.ps1` 自动读取。

---

## [FORBID] 为什么不能直接 `python dev.py` / `python -m meta.server`

**多 Agent 并行环境下，trae-sandbox 会隔离进程空间：**
- Agent A 的 `Get-Process` 看不到 Agent B 启动的 Python 进程
- Agent A 的 `taskkill` 杀不掉 Agent B 的进程
- 唯一的跨 sandbox 可见信号是 **端口状态**（`netstat`）

因此：
- [X] 旧方式：`python dev.py` → auto-kill 旧进程 → sandbox 下无效 → 端口冲突
- [OK] 新方式：`start.ps1` → 端口检测（跨 sandbox 可靠）→ 已运行则跳过，未运行则启动

---

## [CLIPBOARD] 故障排查

### 服务状态异常
```powershell
powershell -File scripts/service_manager.ps1 status
```

### 端口冲突 / 僵尸进程
```powershell
powershell -File scripts/service_manager.ps1 restart
```

### 查看服务日志
```powershell
Get-Content .service_manager.log -Tail 20
```

### 查看 Watchdog 状态和事件
```powershell
powershell -File scripts/service_manager.ps1 watchdog
Get-Content .watchdog.log -Tail 20
```

### Watchdog 检测到 HIJACK 的含义
当 watchdog 日志中出现 "HIJACK" 事件时，表示有其他 Agent 绕过了 service_manager 直接启动了服务。Watchdog 会自动修正状态文件以反映实际情况，无需手动干预。

---

## [NOTE] 文件索引

| 文件 | 用途 |
|------|------|
| [scripts/start.ps1](../../scripts/start.ps1) | **统一启动包装器（唯一入口）** |
| [scripts/service_manager.ps1](../../scripts/service_manager.ps1) | 服务生命周期管理器 |
| [scripts/watchdog.ps1](../../scripts/watchdog.ps1) | 服务守护进程（健康监控+自动修复） |
| [package.json](../../package.json) | `dev:full` → start.ps1 |
| [dev.py](../../dev.py) | Flask 后端启动（含启动守卫） |
| [meta/server.py](../../meta/server.py) | Flask 应用入口（含启动守卫） |
| [.env](../../.env) | 端口等环境变量配置 |

---

*最后更新: 2026-06-01 — 纵深防御四层 + start.ps1 统一入口 + watchdog 可观测性*

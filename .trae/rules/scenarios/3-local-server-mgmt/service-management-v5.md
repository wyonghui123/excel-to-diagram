---
alwaysApply: false
title: 服务管理规范 v5.0
last_updated: 2026-09-02
status: 活跃
version: v5.0
based_on: 09-01 worktree 治理 + 09-02 服务治理
supersedes: service-management-rules.md
description: "AI 启动/停止/重启本地服务（5000/3004 等端口）、管理 worktree 服务进程、解决端口冲突、调用 service_manager.ps1 或 _wt_service.py 时查阅此规则。"
---

# 服务管理规范 v5.1（基于 worktree v4.0 + 服务治理新方案 + 多会话并行）

> **v5.1 重要变更（2026-09-06 多会话并行）**
> - 🟢 会话注册表 `.runtime/port_registry.json`：根治多智能体孤儿对账互杀
> - 🟢 slot 沙箱：共享 slot 0 (3006/3011) 只用不改；改后端 → acquire-session 私有槽
> - 🟢 跨会话 stop/restart 保护：其他会话活跃占用时 REFUSED，逃生口 `--force`

> **v5.0 重要变更（2026-09-02 服务治理后）**
> - 🟢 端口单一真相源 = `.ports.yaml`（禁止硬编码端口）
> - 🟢 临时文件统一目录 = `.tmp/`（禁止散落 scripts/ 或 root）
> - 🟢 每周 PM 触发 `reset_workspace.ps1` 自动清理 >7 天的临时文件
> - 🟢 scripts/ 只保留 4 类核心脚本（start / service_manager / watchdog / reset_workspace）
> - 🟢 多 Agent 端口隔离原则沿用（3010-3019）

---

## 1. 唯一入口

```bash
# 查看所有服务状态
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 status

# 启停服务
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 start|stop|restart

# 多 Agent 端口隔离
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 start -Port 3011

# 清理临时文件
powershell -File d:\filework\excel-to-diagram\scripts\reset_workspace.ps1 -Clean
```

**禁止**：
- ❌ 直接 `npm run dev`（绕过 service_manager，其他 Agent 不可见）
- ❌ 直接 `python meta/server.py`（同上）
- ❌ 在终端启动后台进程（无 service_manager 跟踪，进程僵死后无清理）

---

## 2. 端口分配铁律（v5.0 新增）

**端口单一真相源 = `.ports.yaml`**

修改端口流程：
1. 编辑 `excel-to-diagram/.ports.yaml`
2. commit + push
3. 通知所有 AI 智能体

**严禁**：
- ❌ 在代码中硬编码端口号（`if port == 3010`）
- ❌ 在规则文件中写死端口（应引用 `.ports.yaml`）
- ❌ 在文档中散布"端口 = 3004/3010"等信息

**读取端口**：
```powershell
# AI 智能体查询端口
$y = Get-Content d:\filework\excel-to-diagram\.ports.yaml | ConvertFrom-Yaml
$dev_backend = $y.environments.dev.backend.default  # 3010
```

---

## 3. scripts/ 目录治理（v5.0 新增）

**scripts/ 只允许 4 类文件**：

| 类型 | 命名 | 数量上限 |
|------|------|---------|
| 启动入口 | `start*.ps1` / `start*.sh` | 1-2 |
| 服务管理 | `service_manager.ps1` | 1 |
| 健康监控 | `watchdog.ps1` | 1 |
| 清理工具 | `reset_workspace.ps1` | 1 |
| `.sh` 远程部署脚本 | `*-enhanced.sh` / `*-manager.sh` | 4-5（staging 用）|

**禁止**：
- ❌ `scripts/_xxx.py`（临时脚本，挪到 `.tmp/`）
- ❌ `scripts/verify_*.py` / `scripts/probe_*.py` / `scripts/list_*.py`（挪到 `.tmp/`）
- ❌ `scripts/logs/_*.log`（运行时日志归 `.tmp/` 或 `logs/`）

**例外保留**（历史遗留，向后兼容）：
- `scripts/_hooks/pre_commit_sync_infra.py`（pre-commit 钩子）
- `scripts/_wt_*.py` / `scripts/_v33_*.py`（worktree 管理基础设施）
- `scripts/_sync_*.py`（代码同步工具）

---

## 4. 临时文件治理（v5.0 新增）

**所有 AI 临时文件统一到 `.tmp/`**

命名规范：
```
.tmp/
  _fix_<bug-id>_<seq>.py       # Bug fix 探针
  _diag_<module>_<seq>.py      # 诊断
  _probe_<endpoint>_<seq>.py   # API 探针
  _shot_<name>_<seq>.png       # 截图
  _log_<date>_<seq>.txt        # 日志
  _data_<purpose>_<seq>.json   # 数据
```

**清理策略**：
- > 7 天的临时文件：自动删除（PM 每周触发）
- < 7 天的临时文件：保留（可能是活跃会话）
- 强制清理：手动 `reset_workspace.ps1 -Clean -Force`

**禁止**：
- ❌ 在 `scripts/` 创建 `_xxx.py`（挪到 `.tmp/`）
- ❌ 在仓库根创建 `_xxx.py`（挪到 `.tmp/`）
- ❌ 把临时文件 commit 到仓库

---

## 5. 多 Agent 端口隔离（沿用 v3.18）

| Agent | 默认端口 | 备注 |
|-------|---------|------|
| Agent A | 3010 | 默认 |
| Agent B | 3011 | 协调智能体 |
| Agent C | 3012 | 测试智能体 |
| Agent D | 3013+ | 备用 |

**前端端口 = 3004**（固定，共享）。

**CORS 配置**（来自 `.ports.yaml`）：
- `http://localhost:3004`
- `http://localhost:3005`
- `http://localhost:5173`

---

## 6. 服务启动检查清单（强制）

启动任何服务前必须执行：

```powershell
# 1. 查看状态
powershell -File scripts/service_manager.ps1 status

# 2. 检查端口
Get-NetTCPConnection -LocalPort 3010 -ErrorAction SilentlyContinue

# 3. 检查依赖服务
curl http://localhost:3010/health  # backend
curl http://localhost:3004/         # frontend
```

**全部就绪才能启动测试。**

---

## 7. 服务就绪判定（5 步验证）

| 步骤 | 检查 | 通过条件 |
|------|------|---------|
| 1 | service_manager status | 显示 RUNNING |
| 2 | curl backend health | HTTP 200 |
| 3 | curl frontend root | HTTP 200 |
| 4 | 检查 Playwright 进程 | 无残留 |
| 5 | 检查浏览器进程 | 无残留 |

**缺一不可，必须全部通过才能开始测试。**

---

## 8. 重启安全规则

**restart 会导致正在运行的测试卡住。重启前必须确认：**

1. 没有 Playwright 测试进程
2. 没有浏览器（chromium/chrome）进程属于测试
3. 用 `status` 确认服务状态后再决定是否 restart

**重启期间不允许运行测试**。

---

## 9. CHANGELOG

| 日期 | 变更 | 内容 |
|------|------|------|
| 2026-09-06 | v5.1 多会话并行 | 会话注册表 port_registry + slot 沙箱（acquire/release-session）+ 跨会话 stop 保护，端口真源改为 scripts/ports.json |
| 2026-09-02 | v5.0 服务治理 | 新增 .ports.yaml / .tmp/ / reset_workspace.ps1 三件套 |
| 2026-09-01 | v4.0 worktree | 配套开发规范 v4.0 |
| 2026-08-XX | v3.x | service-manager 单一入口（已废弃）|
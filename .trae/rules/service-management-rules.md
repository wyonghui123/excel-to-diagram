---
alwaysApply: false
description: "服务管理规范（指针）：现行版本见 scenarios/3-local-server-mgmt/service-management-v5.md"
globs: "scripts/*.ps1,scripts/*.py"
---

# 服务管理规范（已收敛到 v5.1）

> 本文件正文已并入 **v5.1**：`scenarios/3-local-server-mgmt/service-management-v5.md`
> 原 v3 正文可在 git 历史中查看，不再单独维护。

## 三条硬约束（v5.1 摘要）

| 约束 | 正确做法 |
|---|---|
| 唯一入口 | `powershell -File scripts/service_manager.ps1 status\|start\|stop\|restart`（worktree 用 `_wt_service.py`） |
| 禁止判活/杀进程 | 禁 `npm run dev`、`Get-Process` 判活、`taskkill` 杀进程 |
| 重启用 restart | 禁 `stop; start` 串联（锁等待超时） |
---
name: status
description: 查看系统状态（服务 + Git + Worktree）
tools:
  - RunCommand
---

查看当前系统完整状态，包括前后端服务、Git 工作区、Worktree、Stash。

步骤：
1. 服务状态：`powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 status`
2. Git 状态：`git -C d:\filework\excel-to-diagram status --short --branch`
3. Worktree 列表：`git -C d:\filework\excel-to-diagram worktree list`
4. Stash 列表：`git -C d:\filework\excel-to-diagram stash list`
5. 最近 5 条 commit：`git -C d:\filework\excel-to-diagram log --oneline -5`

如果服务未运行：
- 启动：`powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 start`
- 重启：`powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 restart`

注意：
- 禁止直接用 `npm run dev` 或 `python dev.py` 启停服务
- 禁止用 `Get-Process python` 判断服务状态（sandbox 隔离不可靠）

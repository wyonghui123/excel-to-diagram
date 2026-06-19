# T-service-manager-fix-2026-06-19

> **Task ID**: T-service-manager-fix-2026-06-19
> **Agent**: Smart Agent A
> **基于 commit**: 8961492
> **风险等级**: medium (服务启动行为变更)
> **开始时间**: 2026-06-19 12:10

## 1. 目标 (Goal)

修复 service_manager.ps1 启动后端时弹 CMD 窗口的问题。

## 2. 改动文件

- [x] `scripts/service_manager.ps1` - v3.18 → v3.19
  - backend 用 pythonw.exe 替代 python.exe
  - 4 个 Start-Process 都加 RedirectStandardOutput/Error + NoNewWindow

## 3. 禁止改

- ❌ `.agent-status.json`
- ❌ `.git/hooks/*`
- ❌ `d:\filework\.coord\ports.json`

## 4. 依赖

- 基于 commit: `8961492`
- 不依赖其他 agent

## 5. 完成标准

- [x] service_manager.ps1 修复
- [x] 在 worktree 中 commit
- [ ] Merge 到 main
- [ ] User 重启服务验证无弹窗

## 6. 风险评估

- **风险 1**: pythonw.exe 不输出 stdout/stderr（GUI 模式）
  - 缓解：RedirectStandardOutput 到 logs/ 文件
- **风险 2**: 用户现有服务是 python.exe 启动的，仍有弹窗
  - 缓解：merge 后用户需重启服务（service_manager restart）

## 7. 沟通计划

- merge 后通知用户：service_manager.ps1 v3.19 已就绪
- 建议用户运行 `service_manager.ps1 restart` 让新版本生效
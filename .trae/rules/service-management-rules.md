---
alwaysApply: false
description: "服务管理规范：启停前后端服务、service_manager 使用规则"
globs: "scripts/*.ps1,scripts/*.py"
---

# 服务管理规范（多 Agent 协作）

> 前后端启停必须用 `service_manager.ps1`，禁止直接操作终端/进程。

## 核心问题

- **sandbox 隔离**：Agent A 的进程对 Agent B 不可见
- **终端槽位竞争**：服务占用终端后其他 Agent 可用终端减少
- **端口冲突**：Agent 不知道另一 Agent 已启动服务

## 唯一入口

```bash
# 查看状态
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 status

# 启停
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 start|stop|restart
```

## 禁止行为

| 禁止 | 后果 |
|------|------|
| 直接 `npm run dev` | 跨 Agent 不可见，导致端口冲突 |
| 用 `Get-Process` 判断状态 | sandbox 隔离不可见 |
| 用 `taskkill` 杀进程 | 可能误杀其他 Agent |
| 从终端推断服务状态 | 用 `service_manager.ps1 status` |
| 用 `stop; start` 串联重启 | 锁等待超时，应用 `restart` |
| 强制删除锁文件 | 锁是保护机制，应等待 120s 超时 |
| 服务操作期间运行测试 | 应确认就绪后再测试 |

## 重启安全规则

> **restart 会导致正在运行的 Playwright 测试卡住/超时。重启前必须检查。**

**重启前必须确认：**
1. 没有 Playwright 测试进程正在运行
2. 没有浏览器（chromium/chrome）进程属于测试
3. 使用 `status` 确认服务状态后再决定是否 restart

**重启期间的测试协调：**
```
服务被操作（restart/stop/start）期间，不应运行测试：
  [X] Agent A 在 restart → Agent B 在运行测试
  [OK] Agent A 完成 restart + 确认就绪 → Agent B 才运行测试

判断服务就绪：
  1. service_manager.ps1 status 显示 RUNNING
  2. curl http://localhost:3004 返回 200
  3. curl http://localhost:3010 返回 200
  → 才能开始测试
```

**判断测试是否在运行：**
```bash
# 检查是否有 Playwright 测试进程
powershell -Command "Get-Process | Where-Object { $_.CommandLine -match 'playwright|chromium' }"

# 如果有测试在运行，不要 restart
# 正确做法：等测试完成，或使用独立的测试环境
```

## 渐进式重启（零停机）

```
service_manager.ps1 的 restart 命令是"先停后启"，会导致短暂不可用。

零停机方案（手动分步）：
  1. 先 start 新进程 → 确认端口监听
  2. 再 stop 旧进程

注意：这需要手动分步操作，不是简单的 restart 命令。
```

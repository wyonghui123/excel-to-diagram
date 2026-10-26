---
title: 场景 1. 远程服务器运维
scenario: 1-remote-server-ops
icon: "1."
---

# 场景 1. 远程服务器运维 (Remote Server Operations)

> **场景定位**：远程服务器 (staging/prod) 上的服务运维、进程管理、故障恢复
> **场景关键词**：`staging 挂了` / `进程死亡` / `端口占用` / `远程重启` / `watchdog` / `yexec` / `SSH`

---

## 何时进入此场景

当 AI 任务画像符合以下任一情况时，进入此场景：

- staging 挂了
- 进程死亡
- 端口占用
- 远程重启
- watchdog

---

## 必读文件（按重要性排序）

1. **[remote-server-alert-avoidance.md](./remote-server-alert-avoidance.md)** — 远程运维告警规避 (ssh/yexec 安全)
1. **[staging-process-guardian.md](./staging-process-guardian.md)** — Staging 进程守护 (18081/19200/19101/13011)
1. **[postmortem-2026-09-02-staging.md](./postmortem-2026-09-02-staging.md)** — 2026-09-02 Staging 事故复盘 (知识沉淀)
1. **[server-management.md](./server-management.md)** — 服务管理基础 (旧版核心规范)

---

## 完整文件清单（4 个）

| 文件 | 用途 |
|------|------|
| [remote-server-alert-avoidance.md](./remote-server-alert-avoidance.md) | 远程运维告警规避 (ssh/yexec 安全) |
| [staging-process-guardian.md](./staging-process-guardian.md) | Staging 进程守护 (18081/19200/19101/13011) |
| [postmortem-2026-09-02-staging.md](./postmortem-2026-09-02-staging.md) | 2026-09-02 Staging 事故复盘 (知识沉淀) |
| [server-management.md](./server-management.md) | 服务管理基础 (旧版核心规范) |

---

## 关联场景

**前序场景**：
- 视任务而定

**后续场景**：
- 视任务而定

---

## CHANGELOG

| 日期 | 变更 |
|------|------|
| 2026-09-02 | v5.0 场景化重构 (从扁平主题分类迁移到场景目录) |

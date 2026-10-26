---
alwaysApply: false
description: "staging 进程守护规范：watchdog + systemd + 自动重启铁律"
globs: "tools/staging_*.sh,tools/staging_*.py,tools/*.service"
---

# Staging 进程守护规范

> **版本**: v1.0 | **更新**: 2026-09-02 | **状态**: 活跃
> **触发事件**: 2026-09-01 staging 18081/19200 进程死亡，无守护导致必须 SSH 手动 nohup 拉起
> **适用范围**: 所有 staging 服务（172.20.59.7）

---

## 〇、问题陈述

staging 有 **4 个核心服务**：

| 服务 | 端口 | 进程 owner | 守护机制（v1.0 前） |
|---|---|---|---|
| core_service | 19200 | nobody | ❌ 无 |
| log_service | 19101 | root | ⚠️ 有 systemd（V007.55）但**兄弟进程无** |
| meta_backend | 13011 | root | ❌ 无 |
| unified_18081 | 18081 | nobody | ❌ 无 |

**事故链**：任何一次误 kill / OOM / 进程崩溃 → 服务永久死掉 → 必须 SSH 手动拉起。

**根因**：没有跨 4 服务的统一守护机制。systemd unit 只覆盖 log_service。

---

## 一、解决方案（v1.0 起强制）

### 1.1 `staging_watchdog.sh` — 应用层 watchdog（必装）

```bash
# 已部署到 /opt/app/staging/bin/staging_watchdog.sh
# 由 staging 上 nobody 或 root 启动 nohup 守护

# 单次检查 + 自动修复（适合 cron）
bash /opt/app/staging/bin/staging_watchdog.sh --once

# 持续守护（前台 30s 周期）
bash /opt/app/staging/bin/staging_watchdog.sh --watch --interval 30

# 后台运行（部署后必跑）
nohup bash /opt/app/staging/bin/staging_watchdog.sh --watch --interval 30 \
    >> /opt/app/staging/logs/staging_watchdog.log 2>&1 &
disown

# 看状态
bash /opt/app/staging/bin/staging_watchdog.sh status

# 停守护
bash /opt/app/staging/bin/staging_watchdog.sh stop
```

**能力**：

| 检查 | 频率 | 行为 |
|---|---|---|
| core_service (19200) HTTP probe | 30s | DOWN → 调 `staging_services.sh restart core_service`（自动拉上游） |
| log_service (19101) HTTP probe | 30s | 同上 |
| meta_backend (13011) HTTP probe | 30s | 同上 |
| unified_18081 (18081) HTTP probe | 30s | 同上 |

**防雪崩**：1 小时内同一服务重启 ≥5 次 → 停止自动重启，写 ABORT 日志要求人工介入。

### 1.2 systemd unit（可选升级）

如果 staging 服务器开放 systemd 权限，把下面 4 个 unit 部署到 `/etc/systemd/system/`：

| unit | 文件 |
|---|---|
| staging-core.service | core_service (19200) |
| staging-backend.service | meta_backend (13011) |
| staging-spa.service | unified_18081 (18081) |
| staging-watchdog.service | watchdog 守护（30s 周期） |

启用：
```bash
cp staging-*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now staging-core staging-backend staging-spa staging-watchdog
```

**优势**：服务器重启 → 自动拉起；不需要 nohup。

### 1.3 现有 systemd（不要破坏）

`log_service_staging.service`（V007.55）是已有的 systemd unit，**保留不动**，watchdog 检测到 log_service DOWN 仍会调 `staging_services.sh restart log_service`（内部用 setsid+nohup，与 systemd 不冲突——systemd 会启动新的）。

---

## 二、强制约束（铁律）

### L1: 服务死了必须 5 分钟内自动重启

任何 staging 服务 DOWN 后 **不允许** 状态保持超过 5 分钟不修复。

- watchdog 30s 检测 → 最迟 30s 发现
- restart 脚本 5s 启动 → 最多 35s 恢复
- 超出 → 必须排查（可能是 restart 失败卡死，需要 SSH）

### L2: restart 失败 N 次必须放弃

1 小时内同服务重启 ≥5 次 → watchdog 写 ABORT 日志，**不再自动重启**，要求人工排查：

```bash
# 看 ABORT 日志
tail -50 /opt/app/staging/logs/staging_watchdog.log | grep ABORT

# 手工排查
bash /opt/app/staging/bin/staging_services.sh status log_service
tail -50 /opt/app/staging/logs/log_service.log
```

### L3: watchdog 必须常驻

**禁止**用 `--once` 作为长期守护（只会跑一次）。生产/常驻 staging 必须 `--watch` + nohup。

### L4: 部署 staging_watchdog.sh 必须重启 daemon

每次更新 staging_watchdog.sh 后：
```bash
bash /opt/app/staging/bin/staging_watchdog.sh stop
nohup bash /opt/app/staging/bin/staging_watchdog.sh --watch --interval 30 \
    >> /opt/app/staging/logs/staging_watchdog.log 2>&1 &
disown
```

### L5: 远程运维必须先看 watchdog 状态

SSH 上 staging 后第一件事：
```bash
bash /opt/app/staging/bin/staging_watchdog.sh status
# 看 restarts_1h 是否异常，看 4 服务是否 UP
```

---

## 三、与 staging_services.sh 的关系

```
staging_watchdog.sh (守护)
    │
    ├─ HTTP 探测 4 个端口
    │
    └─ DOWN 时调 → staging_services.sh restart <name>
                       │
                       └─ 内部用 setsid+nohup 启动 (P1-3 依赖图)
                          + 自动拉上游 (restart-deps 内置逻辑)
```

**关键点**：watchdog **不直接启动进程**，统一委托给 `staging_services.sh`（依赖图正确性有保证）。

---

## 四、监控与告警（可选 P1.5）

```bash
# 看 watchdog 最近 1 小时重启次数
grep -c 'RESTART-OK' /opt/app/staging/logs/staging_watchdog.log

# 看 ABORT 事件
grep ABORT /opt/app/staging/logs/staging_watchdog.log

# 看服务健康总览
bash /opt/app/staging/bin/staging_watchdog.sh status
```

**未来**：可对接 yonaa 的 alert monitor（已有 alert_monitor.py），把 ABORT 推送到 IM/钉钉。

---

## 五、CHANGELOG

| 日期 | 变更人 | 变更内容 |
|---|---|---|
| 2026-09-02 | AI Assistant | v1.0 创建。触发：2026-09-01 staging 18081/19200 死亡无人拉起事故。落地 staging_watchdog.sh + 4 个 systemd unit + 5 条铁律 |

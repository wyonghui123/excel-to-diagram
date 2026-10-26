---
alwaysApply: false
title: 元能力服务架构铁律
last_updated: 2026-07-14
status: 活跃
enforcement: 强制执行
---

# 元能力服务架构铁律

> 最后更新: 2026-07-14 | 状态: 活跃 | 强制执行
> V007.50 更新: 补充 staging 端口 19200

## ⚠️ 架构冻结警告

**core_service 是核心元能力服务，架构已冻结。任何违规添加新能力的 AI 必须立即重构。**

---

## 一、各服务的职责边界

### 1.1 core_service — **架构冻结**

**端口**:
- prod: **9200**
- staging: **19200**

**职责**（只允许这 4 项）：
- `/api/upload` — 文件上传
- `/api/exec` — 命令执行
- `/api/audit` + `/api/audit/rotate` — 审计日志
- `/api/services/status` — 集中服务状态查询（只读元能力）

**禁止**：
- ❌ 任何业务能力（DB、配置、告警、回滚、部署）
- ❌ 任何系统管理能力（crontab、服务管理）
- ❌ 总行数 **必须 < 500 行**（超出立即拆分）

### 1.2 observability_service (9201) — ⚠️ 2026-07-14 未检测到监听

**职责**：批量上传、Prometheus 指标、健康检查、请求追踪

> **状态**: 2026-07-14 性能测试时 `netstat -tlnp` 未检测到 9201 端口监听。可能未部署或已停止。使用前需先确认。

### 1.3 log_service — 已有 ✅

**端口**:
- prod: **9101**
- staging: **19101**

**职责**：日志查询、诊断、**告警网关** (`/api/alert/*`)、**一键回滚** (`/api/deploy/*`)、看门狗

### 1.4 ops_scheduler (9202) — ⚠️ 2026-07-14 未检测到监听

**职责**：定时任务调度、JSONL 执行日志

> **状态**: 2026-07-14 性能测试时 `netstat -tlnp` 未检测到 9202 端口监听。但 `ps aux` 显示 `/opt/app/shared/ops_scheduler.py` 进程在运行（可能未监听端口，仅作为后台进程）。

### 1.5 config_service (9203) — **待创建**

**职责**：
- `/api/config` — 配置中心（list/get/set/delete/export）
- `/api/crontab` — crontab 管理（show/install/backup）

**触发原因**：之前错误地放在 core_service，必须拆分

### 1.6 dbops_service (9204) — **待创建**

**职责**：
- `/api/db/ops` — DB 运维（health/stats/backups/backup/restore/cleanup/verify）

**触发原因**：DB 专属能力不属于 core_service

---

## 二、违规历史（避免再犯）

| # | 日期 | 违规内容 | 后果 | 纠正 |
|---|------|---------|------|------|
| 1 | 2026-07-12 | 在 core_service 添加 `/api/config` + `/api/crontab` + `/api/services/status` + `/api/db/ops` | core_service 从 400 行膨胀到 1140 行 | **拆分到 config_service + dbops_service** |

---

## 三、添加新能力前的强制检查清单

**每次想给 core_service 加新端点前，必须回答这 4 个问题**：

### Q1: 这是元能力吗？

**元能力定义**：能让 AI **远程操作系统**的能力（upload/exec/audit）

**反例**（不是元能力）：
- ❌ DB 备份、配置管理、crontab 管理、告警推送、回滚
- ❌ 任何特定业务领域的能力

### Q2: 是否能被现有服务替代？

现有 6 个服务端口已覆盖大部分运维场景。**先看能不能用现有端点组合完成**。

### Q3: 添加后总行数是否 < 500？

如果接近 500，**必须新建独立服务**而不是堆到 core_service。

### Q4: 新服务是否能独立部署？

新能力是否能在独立端口运行、有自己的 token、独立的 watchdog？

**只有 4 个问题都通过（YES），才允许添加到 core_service。否则必须新建服务。**

---

## 四、强制执行机制

### 4.1 代码层防护

`core_service.py` 头部 docstring 已加入：

```python
[!!!] ABSOLUTELY FORBIDDEN [!!!]
以下能力必须拆分到独立服务, 不得添加到 core_service:
  [X] /api/config         → config_service (端口 9203)
  [X] /api/crontab        → config_service (端口 9203)
  [X] /api/db/ops         → dbops_service (端口 9204)
```

### 4.2 文档层防护

- 本规则文件
- `OPS_MANUAL.md` 中服务清单标注 **「架构冻结」**
- 每个新服务的 `tools/<service>.py` 头部明确职责

### 4.3 流程层防护

**每次代码评审必须验证**：
1. core_service 行数 < 500
2. 新端点不在 ABSOLUTELY FORBIDDEN 清单
3. 4 问检查清单全部通过

---

## 五、CHANGELOG

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-07-12 | AI Assistant | 创建规则文件，记录首次违规（1140 行膨胀），定义 config_service/dbops_service 拆分计划 |
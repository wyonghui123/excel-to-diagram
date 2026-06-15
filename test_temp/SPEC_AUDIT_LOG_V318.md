# Spec + RFC: 审计日志 (audit_log) 体系优化 (v3.18) — **最终版**

> **作者**: Trae AI
> **日期**: 2026-06-12
> **版本**: v3.18-final
> **状态**: 待用户授权开发
> **前置调研**: [INDUSTRY_BENCHMARK_AUDIT_v318.md](file:///d:/filework/excel-to-diagram/test_temp/INDUSTRY_BENCHMARK_AUDIT_v318.md) / [AUDIT_LOG_DEEP_ANALYSIS_v318.md](file:///d:/filework/excel-to-diagram/test_temp/AUDIT_LOG_DEEP_ANALYSIS_v318.md) / [TBD_DECISIONS_V318.md](file:///d:/filework/excel-to-diagram/test_temp/TBD_DECISIONS_V318.md)

---

## 1. Background & Objectives

### 1.1 Background (现状, 基于实际 schema + 数据)

**Schema 实际状态 (28 字段)**: 必填 `object_type/action/log_category(默认business)/log_level(默认INFO)`; 默认 `status='written', retry_count=0`; 11 索引齐; v3.18 已支持 `agent_id/agent_session_id/tool_call_id/agent_reasoning`; **没有** v2 字段 `outcome/action_kind/parent_action_id/retention_until`。

**实际数据 (2216 条样本)**:
- `log_category` 全 `'business'` (100%)、`log_level` 全 `'INFO'` (100%)
- `user_name='V3.17 Test'` 1601 条 = **73% 测试脏数据**
- `status='failed'` 7 条 (异步写失败无重试)
- 单 trace 最多 17 条, 平均 3.1 条 → 关联能力 OK

**代码现状 (实际定位)**:
- [AuditLogger.log()](file:///d:/filework/excel-to-diagram/meta/core/action_executor.py#L108-L153) 缺 `log_category/log_level/outcome` 显式参数
- [BatchAuditContext](file:///d:/filework/excel-to-diagram/meta/services/audit_service.py#L114-L163) 引用不存在的字段 → schema drift, 批量审计**完全失败**
- 错误响应非 RFC 7807 (散落各 API)
- `AUDIT_WRITE_FAILED` 无 retry worker
- `target_display` cascade 已修, ASSOCIATE 路径还有 100% 缺失

### 1.2 Business Objectives

| 目标 | 量化 |
|------|------|
| 合规可审计 | 1 类 → 7 类, 满足 SOX/GDPR/PCI 报告 |
| 用户可恢复 | 错误恢复 N 分钟 → 30 秒 |
| 审计可读性 | 测试脏数据 73% → 0%, user_name 完整格式 30% → 100% |
| 防篡改 | hash chain 100% (本期) |
| 数据可持续 | 3 层保留: 2y/1y/90d |

### 1.3 User / Stakeholder (涉众) Objectives

| 角色 | 目标 | 痛点 → 解决 |
|------|------|------------|
| 终端用户 | 操作被拒时知道怎么解决 | 看不到阻止原因 → FR-002 recovery hint |
| 审计员 | 快速筛 security/auth 类日志 | 100% 业务 → FR-003 7 类 |
| SRE | 监控失败/阻塞率 | 无法区分 → FR-004/005 level+outcome |
| 合规官 | 防篡改 + 长保留 | 无 hash chain / 永久存 → FR-014/013 |
| AI Agent (v3.18) | 操作可追溯 | agent_* 字段已有, 联动增强 |

---

## 2. Requirement Type Overview

| Type | 适用 | 证据 |
|------|------|------|
| Business | ✅ | 4 轮对话分析 + TBD 决策 |
| User/Stakeholder (涉众) | ✅ | 错误恢复/可读性/合规 |
| Solution | ✅ | RFC 7807 / Hash chain / 3 层保留 |
| Functional | ✅ | FR-001 ~ FR-016 |
| Nonfunctional | ✅ | NFR-001 ~ NFR-008 |
| External Interface | ✅ | IF-001 ~ IF-003 |
| Transition | ✅ | TR-001 ~ TR-003 |

---

## 3. Functional Requirements

### FR-001: RFC 7807 错误响应标准化 — **Must**

- **Description**: 所有 4xx/5xx 错误响应 MUST 符合 RFC 7807, 至少含 `type / title / status / detail / instance / code / trace_id / timestamp`, 可选 `recovery`
- **Acceptance Criteria**:
  - 新建 `meta/api/_problem_details.py`, 提供 `ProblemDetails.build()` 工厂方法
  - 现有 `{success, message}` 自由 JSON 全量迁移
  - `trace_id` 必返 (用户支持查询用)
  - 单元测试覆盖 8 种错误 (404/422/401/403/409/500/502/503)
- **Source**: RFC 7807 + Stripe 错误实践

### FR-002: DELETE_BLOCKED recovery hint — **Must**

- **Description**: DELETE 被 `RESTRICT_ON_DELETE` 等外键约束阻止时, 错误响应 MUST 含 `recovery` 字段
- **Acceptance Criteria**:
  - 7 类常见阻止原因 (HAS_CHILDREN / HAS_MEMBERS / IS_REFERENCED / IS_SYSTEM / HAS_TRANSACTIONS / HAS_AUDIT_TRAIL / VERSION_LOCKED) 都有对应 recovery
  - `recovery` 至少含 `type / title / ui_path / endpoint / count / estimated_seconds / auto_resolvable`
  - 前端根据 `auto_resolvable: true` 渲染"一键处理"按钮
- **Source**: Stripe recovery + 用户体验

### FR-003: log_category 7 类自动派生 — **Must**

- **Description**: 根据 `action` 自动派生 `log_category`, 7 类: `business/security/authz/access/admin/system/cascade`
- **Acceptance Criteria**:
  - 新建 `meta/core/audit_constants.py`, 定义 `AuditCategory` 枚举
  - 派生规则: `LOGIN→security`, `role.*→authz`, `READ→access`, `DELETE_BLOCKED→admin`, `AUDIT_WRITE_FAILED→system`, 级联衍生→`cascade`, 其他→`business`
  - `AuditLogger.log()` 增加 `log_category` 显式参数 (默认 derive)
  - 历史 2216 条 backfill
- **Source**: GCP Cloud Audit Logs 4 类 + 业界共识

### FR-004: log_level 3 级自动派生 — **Must**

- **Description**: 根据 action 结果派生 `log_level`: `INFO` (成功) / `WARN` (拒绝/阻塞) / `ERROR` (系统故障)
- **Acceptance Criteria**:
  - 派生规则: 成功→INFO, `DELETE_BLOCKED`/`ACCESS_DENIED`→WARN, `AUDIT_WRITE_FAILED`→ERROR
  - `AuditLogger.log()` 增加 `log_level` 显式参数
- **Source**: OpenTelemetry SeverityNumber 简化

### FR-005: outcome 字段新增 — **Must**

- **Description**: 新增 `outcome VARCHAR(20)`, 区分 4 种结果
- **Acceptance Criteria**:
  - 枚举: `success / failure / blocked / retry`
  - `AuditLogger.log()` 增加 `outcome` 参数
  - Migration: `ALTER TABLE audit_logs ADD COLUMN outcome VARCHAR(20) DEFAULT 'success'`
  - 索引: `idx_audit_outcome (outcome, created_at)`
  - 历史 backfill
- **Source**: NIST SP 800-92 + 当前缺 outcome

### FR-006: user_name 强制 `display_name (username)` 格式 — **Must**

- **Description**: 统一 `user_name = "{display_name} ({username})"`, 无 display_name 或等于 username 时用纯 username
- **Acceptance Criteria**:
  - `meta/core/audit_constants.py` 新增 `normalize_user_name()` 工具
  - `set_user_context()` 接入
  - 单元测试: 3 种情况
  - 历史 2216 条 backfill
- **Source**: CloudTrail `userIdentity`

### FR-007: 测试脏数据清理 — **Must**

- **Description**: 删 `user_name LIKE 'V3.17 Test%'` 的所有 audit log + 对应 users
- **Acceptance Criteria**:
  - 备份到 `audit_logs_backup_20260612`
  - **含 admin 角色测试数据也全删** (TBD-4 决策)
  - 保留唯一真 admin (`id=1, role='admin'`)
  - 提供 `meta/scripts/cleanup_test_audit.py`, 默认 `--dry-run`
  - 删后 `VACUUM`
- **Source**: 当前 1601/2216 = 73% 脏数据

### FR-008: 操作链 API `/_audit/operation/<trace_id>` — **Must**

- **Description**: `GET /api/v2/audit/operation/<trace_id>` 返完整操作链 (含 cascade)
- **Acceptance Criteria**:
  - 权限: **admin only** (TBD-3 决策, `@admin_required` 装饰器)
  - 返 `{trace_id, chain: [...], summary: {root_action, total_events, cascade_depth, affected_objects}}`
  - `chain` 按 `created_at ASC, id ASC` 排序
  - 单元测试: 1 DELETE → 5 DISSOCIATE
- **Source**: OpenTelemetry trace 查询

### FR-009: cascade 字段化 — **Should**

- **Description**: `extra_data.cascade_reason` 提升为顶级 `cascade_root_id (INT)` / `cascade_root_action (VARCHAR)`
- **Acceptance Criteria**:
  - `cascade_interceptor.py` 写入时同时填顶级 + extra
  - Migration 加字段 + 索引 `idx_audit_cascade (cascade_root_action, object_type)`
  - 向后兼容: extra_data 仍保留
- **Source**: Stripe event lineage

### FR-010: 异步写失败自动重试 worker — **Should**

- **Description**: `AuditRetryWorker` **独立 daemon thread** + service_manager 集成
- **Acceptance Criteria**:
  - 1 分钟间隔扫 `status='failed'`
  - 10 次上限指数退避
  - 重试成功 → `status='written'`
  - 启动通过 service_manager 拉起
  - 优雅退出: `stop_event.wait()` 在 stop 信号立即返回
- **Source**: dev.to 警告 setInterval 风险, Stripe 独立 process, Rails SolidQueue 0.1s polling

### FR-011: BatchAuditContext schema drift 修复 — **Should**

- **Description**: 修 BatchAuditContext 引用不存在字段, 实际批量审计**完全失败**问题
- **Acceptance Criteria**:
  - 选 A: 表新增 `action_kind/outcome/parent_action_id/retention_until` 4 字段 (含 FR-005 的 outcome)
  - `batch_create` 写 1 header + N details, header `action_kind='static' outcome='success'`, details `action_kind='instance' parent_action_id=header.id`
  - 验证 31/31 测试后批量操作有审计
- **Source**: 当前 [audit_service.py:114-163](file:///d:/filework/excel-to-diagram/meta/services/audit_service.py#L114-L163) schema drift

### FR-012: target_display 修 ASSOCIATE 100% 缺失 — **Should**

- **Description**: 确保 ASSOCIATE 审计都含 `target_display`
- **Acceptance Criteria**:
  - `association_service.py` 调 `audit_interceptor.log_associate()` 时传 `target_display`
  - 不依赖 `g.request` 上下文
  - 验证修复后 100% 有
- **Source**: 上轮未修完

### FR-013: retention_until 字段 + 3 层保留 — **Should**

- **Description**: 新增 `retention_until` 字段, 写入时按 category 自动设置 3 层保留期
- **Acceptance Criteria**:
  - **3 层保留策略** (TBD-2 决策, 基于 Linear 90d / Notion 180d / GitHub 90-120d / 中型共识):

  | log_category | 保留期 | 理由 |
  |-------------|-------|------|
  | `security` (登录/密码/2FA) | **2 年** | SOX/GDPR 中位线 |
  | `authz` (role/permission) | **2 年** | 合规需要 |
  | `business` (CRUD) | **1 年** | 业务回溯 |
  | `admin` (DELETE_BLOCKED) | **1 年** | 投诉/争议 |
  | `access` (READ/EXPORT) | **90 天** | 容量大 |
  | `system` (AUDIT_WRITE_FAILED) | **90 天** | 故障排查 |
  | `cascade` (级联衍生) | **90 天** | 配合主操作 |

  - Migration: 加 `retention_until DATETIME` 字段 + 索引 `idx_audit_retention`
  - 历史 backfill: 按 `created_at + interval(category)`
  - 配套 cron: 每日扫 `retention_until < today`, 移到 `audit_logs_archive` 表

- **Source**: 头部保留期对比

### FR-014: Hash chain 防篡改 — **Must** (本期, TBD-1 决策)

- **Description**: 新增 `prev_hash CHAR(64)` / `row_hash CHAR(64)` 字段, 每条 hash 链验证
- **Acceptance Criteria**:
  - `prev_hash` = 上一条 row_hash, 首条为 `"0"*64`
  - `row_hash` = `sha256(prev_hash + canonical_json(payload))`
  - `meta/services/audit_hash_chain.py` 提供 `compute_row_hash()` + `verify_chain(start_id)`
  - 日终 cron 跑 verify, 不匹配 → 触发 `AUDIT_HASH_MISMATCH` 告警
  - 单元测试: 改 1 条 → verify_chain() 必报
  - **S3 Object Lock 推迟 Phase 3** (TBD-8 决策)
- **Source**: AWS CloudTrail + PostgreSQL 实践 (中型 SaaS 共识, GitHub Enterprise 有)

### FR-015: 测试数据自动清理 cron — **Should**

- **Description**: 每周日 03:00 本地时区自动清理测试数据
- **Acceptance Criteria**:
  - 扫 `user_name LIKE 'V3.17%' OR 'test_%' OR 'audit_%'` 且 `created_at < today - 7 days` 数据
  - 默认 `--dry-run`, 显式 `--apply` 才删
  - 删除前备份到 `audit_logs_deleted_<YYYYMMDD>`
  - 30 天后 backup 自动清
- **Source**: AWS 02:00 daily / 中型多按周 (TBD-7 决策)

### FR-016: WORM 归档到 S3 Object Lock — **Could (Phase 3)**

- **Description**: > 365 天的审计自动 export 到 S3 Object Lock (Compliance mode)
- **Acceptance Criteria** (Phase 3):
  - 仅 Enterprise tier + 开启合规 mode 时启用
  - 可插拔 backend (S3 / GCS / Azure Blob / 本地 NAS)
  - 跨账户归档 (log archive account)
- **Source**: AWS CloudTrail (TBD-8 决策: **本期不做**)

---

## 4. Nonfunctional Requirements

| ID | 描述 | 测量 |
|----|------|------|
| **NFR-001** | 审计写入 P99 < 5ms (异步) | 1000 次操作取 P99 |
| **NFR-002** | DB 临时不可用 30s, 审计不丢, 恢复后 100% 补写 | 模拟 DB down 测 |
| **NFR-003** | 100 万数据下, `(trace_id)` / `(object_type, object_id, time)` 查询 P95 < 200ms | sqlite-explain |
| **NFR-004** | 90% 审计行让非技术用户读懂 | 抽样 100 条给 3 用户读 |
| **NFR-005** | 篡改检测 100% (FR-014 hash chain) | 人工 modify → verify_chain() 必报 |
| **NFR-006** | LIKE 模糊搜索 P95 < 500ms (1M 数据) | benchmark |
| **NFR-007** | 归档自动化: 每日扫 `retention_until < today` | cron 验证 |
| **NFR-008** | 多 Agent (3010-3019) 审计独立 | `test.py --port 3011` 验证 |

---

## 5. External Interface Requirements

### IF-001: 审计查询 API (强化)

- **Endpoint**: `GET /api/v2/audit/query?object_type=&object_id=&action=&user_name=&from=&to=&trace_id=&log_category=&outcome=&page=&size=`
- **Response**:
  ```json
  {
    "success": true,
    "data": {
      "items": [
        {
          "id": 12345,
          "created_at": "2026-06-12T13:30:00Z",
          "object_type": "product",
          "object_id": 70,
          "object_display": "产品A (PROD_001)",
          "action": "UPDATE",
          "field_name": "name",
          "old_value": "旧名",
          "new_value": "新名",
          "user_name": "张三 (zhangsan)",
          "user_id": 123,
          "ip_address": "10.0.0.1",
          "user_agent": "Chrome 138 / Windows 10",
          "log_category": "business",
          "log_level": "INFO",
          "outcome": "success",
          "trace_id": "abc123...",
          "transaction_id": "def456...",
          "parent_object_type": "user_group",
          "parent_object_id": 5
        }
      ],
      "total": 1234,
      "page": 1,
      "size": 20
    }
  }
  ```
- **Error**: RFC 7807 格式 (FR-001)

### IF-002: 操作链 API (新增, admin only)

- **Endpoint**: `GET /api/v2/audit/operation/<trace_id>` (TBD-3 决策: **admin only**)
- **Response**:
  ```json
  {
    "success": true,
    "data": {
      "trace_id": "abc123...",
      "root_action": "DELETE",
      "root_object": "user_group#567",
      "root_user": "张三 (zhangsan)",
      "chain": [
        {"id": 1, "action": "DELETE", "object": "user_group#567", "level": 0, "cascade": false},
        {"id": 2, "action": "DISSOCIATE", "object": "user#1234 -/-> user_group#567", "level": 1, "cascade": true, "cascade_root_id": 1}
      ],
      "summary": {
        "total_events": 8,
        "cascade_depth": 2,
        "affected_objects": ["user_group#567", "user#1234", "user#1235"],
        "duration_ms": 45
      }
    }
  }
  ```
- **Error**: 403 (非 admin) 用 RFC 7807 + recovery (申请 admin 权限)

### IF-003: 前端审计展示

- 7 类 `log_category` 过滤标签, 3 级 `log_level` 颜色 (INFO=蓝, WARN=橙, ERROR=红)
- 详情显示 RFC 7807 错误时, "一键处理" 按钮根据 `recovery.auto_resolvable` 渲染
- 操作链: 树状图 cascade, 红框=主动, 蓝框=衍生

---

## 6. Transition Requirements

### TR-001: 字段迁移 (8 字段)

- **Description**: ALTER TABLE 加 8 字段 + 写 backfill
- **Strategy**:
  ```sql
  -- Phase 1
  ALTER TABLE audit_logs ADD COLUMN outcome VARCHAR(20) DEFAULT 'success';
  ALTER TABLE audit_logs ADD COLUMN cascade_root_id INTEGER;
  ALTER TABLE audit_logs ADD COLUMN cascade_root_action VARCHAR(50);
  ALTER TABLE audit_logs ADD COLUMN retention_until DATETIME;
  ALTER TABLE audit_logs ADD COLUMN prev_hash CHAR(64);
  ALTER TABLE audit_logs ADD COLUMN row_hash CHAR(64);

  CREATE INDEX idx_audit_outcome ON audit_logs(outcome, created_at);
  CREATE INDEX idx_audit_cascade ON audit_logs(cascade_root_action, object_type);
  CREATE INDEX idx_audit_retention ON audit_logs(retention_until);
  CREATE INDEX idx_audit_hash ON audit_logs(row_hash);

  -- Backfill
  UPDATE audit_logs SET outcome='blocked' WHERE action='DELETE_BLOCKED';
  UPDATE audit_logs SET outcome='failure' WHERE action='AUDIT_WRITE_FAILED';
  UPDATE audit_logs SET log_level='WARN' WHERE action IN ('DELETE_BLOCKED', 'ACCESS_DENIED');
  UPDATE audit_logs SET log_level='ERROR' WHERE action='AUDIT_WRITE_FAILED';
  -- 3 层保留
  UPDATE audit_logs SET retention_until = datetime(created_at, '+2 years') WHERE log_category IN ('security', 'authz');
  UPDATE audit_logs SET retention_until = datetime(created_at, '+1 year')  WHERE log_category IN ('business', 'admin');
  UPDATE audit_logs SET retention_until = datetime(created_at, '+90 days') WHERE log_category IN ('access', 'system', 'cascade');
  -- Hash chain: 从最早一条开始算
  -- (Python 脚本, 不在 SQL)
  ```
- **Rollback**:
  ```sql
  ALTER TABLE audit_logs DROP COLUMN outcome;
  ALTER TABLE audit_logs DROP COLUMN cascade_root_id;
  ALTER TABLE audit_logs DROP COLUMN cascade_root_action;
  ALTER TABLE audit_logs DROP COLUMN retention_until;
  ALTER TABLE audit_logs DROP COLUMN prev_hash;
  ALTER TABLE audit_logs DROP COLUMN row_hash;
  DROP INDEX IF EXISTS idx_audit_outcome;
  DROP INDEX IF EXISTS idx_audit_cascade;
  DROP INDEX IF EXISTS idx_audit_retention;
  DROP INDEX IF EXISTS idx_audit_hash;
  ```

### TR-002: 测试脏数据清理

- **Description**: 1601 条 `'V3.17 Test%'` 数据 + 对应 users
- **Strategy**:
  ```sql
  CREATE TABLE audit_logs_backup_20260612 AS SELECT * FROM audit_logs WHERE user_name LIKE 'V3.17 Test%';
  DELETE FROM audit_logs WHERE user_name LIKE 'V3.17 Test%';
  DELETE FROM users WHERE display_name LIKE 'V3.17 Test%' AND id != 1;
  VACUUM;
  ```
- **Rollback**: `INSERT INTO audit_logs SELECT * FROM audit_logs_backup_20260612;`

### TR-003: API 响应格式双写迁移

- **Description**: `{success, message}` → RFC 7807
- **Strategy** (TBD-5 决策: **双写 2 周 + 切换 1 周 + 4 周废弃**):
  1. **Week 1-2 (双写)**: 旧字段保留, 加 `problem` 字段含 RFC 7807
  2. **Week 3 (切换)**: Feature flag `RFC7807_ENABLED=true`, 前端读 `problem`
  3. **Week 4-7 (废弃)**: 旧字段 deprecated
  4. **Week 8+**: 移除旧字段
- **Rollback**: Feature flag 关闭

---

## 7. Constraints & Assumptions

### 7.1 Technical Constraints
- SQLite 主 DB (100 万行后性能下降, FTS 不支持)
- 已有 AsyncAuditWriter, 不可完全同步写
- Python 3.10+, Flask 蓝图

### 7.2 Business Constraints
- 业务要求: 删除能恢复
- 错误透明, 不能静默失败
- 审计访问本身要审计 (meta-audit)

### 7.3 Assumptions
- 5 年内 < 5000 万条审计 (Verified)
- 4 类核心对象稳定 (Verified)
- 多 Agent 并行 (3010-3019) 长期需要 (Verified)
- 同步 ACK + 异步写可接受 (Verified)

---

## 8. Priorities & Milestone Suggestions

| ID | 需求 | 优先级 | 原因 |
|----|------|-------|------|
| FR-001 | RFC 7807 | **Must** | 用户体验质变 |
| FR-002 | DELETE_BLOCKED recovery | **Must** | 同上 |
| FR-003 | log_category 7 类 | **Must** | 合规报告 |
| FR-004 | log_level 3 级 | **Must** | 监控分级 |
| FR-005 | outcome 字段 | **Must** | 失败/阻塞/重试区分 |
| FR-006 | user_name 标准化 | **Must** | 可读性 +300% |
| FR-007 | 测试脏数据清理 | **Must** | 73% 噪音消除 |
| FR-008 | 操作链 API | **Must** | cascade 调试 |
| FR-014 | hash chain | **Must** | 防篡改 (TBD-1 升) |
| FR-011 | BatchAuditContext 修复 | Should | schema drift |
| FR-012 | ASSOCIATE 100% | Should | 上轮未完 |
| FR-009 | cascade 字段化 | Should | FR-008 依赖 |
| FR-010 | retry worker | Should | 7 条 fail 永久 |
| FR-013 | retention_until 3 层 | Should | 长期健康 |
| FR-015 | 周日 03:00 cron | Should | 长期健康 |
| FR-016 | WORM 归档 | Could | Phase 3 占位 |

**建议里程碑**:
- **Milestone 1 (本周, 9 个 Must)**: FR-001/002/003/004/005/006/007/008/014 → 用户体验质变 + 合规能力 + 审计可读性 + 防篡改
- **Milestone 2 (1 月, 4 个 Should)**: FR-009/010/011/012/013/015 → cascade 可视化 + 异步可靠 + 长期健康
- **Milestone 3 (3 月, Phase 3)**: FR-016 + 独立 audit.db + S3 Object Lock

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

**当前架构**:
```
[BO Action / HTTP Request]
  ↓
[AuditLogger.log()]  (action_executor.py:108)  ← 缺 log_category/log_level/outcome 显式参数
  ↓ 同步入队
[AsyncAuditWriter]    (async_audit_writer.py)
  ↓ 批量异步写
[SQLite audit_logs 表] (28 字段, 11 索引)
  ↓
[Query API: audit_api.py] → CSV/JSON 输出
```

**当前 7 大问题 (代码定位)**:

| 问题 | 代码位置 |
|------|---------|
| log_category/log_level 全默认 | [action_executor.py:108-153](file:///d:/filework/excel-to-diagram/meta/core/action_executor.py#L108-L153) |
| BatchAuditContext schema drift | [audit_service.py:114-163](file:///d:/filework/excel-to-diagram/meta/services/audit_service.py#L114-L163) |
| 错误响应非 RFC 7807 | 散落各 API |
| DELETE_BLOCKED 无 recovery | deletion_service.py |
| AUDIT_WRITE_FAILED 永久 fail | [async_audit_writer.py](file:///d:/filework/excel-to-diagram/meta/services/async_audit_writer.py) |
| 1601 条测试脏数据 | DB 直查 |
| cascade_reason 在 extra_data 难查 | [cascade_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/cascade_interceptor.py) |

### 9.2 Target State

```
[BO Action / HTTP / AI Agent Tool Call]
  ↓ set_user_context (FR-006 标准化)
[AuditLogger.log(action, ..., log_category, log_level, outcome, ...)]
  ├─→ auto-derive (FR-003/004/005)
  ↓ 同步入队
[AsyncAuditWriter] → [audit_logs (新增 6 字段)]
       ↓ on failure           ↓ on success
[AuditRetryWorker] ← 独立 thread (FR-010)
  10 次指数退避
       ↓ exhausted
[archive_audit_logs]    [Hash Chain Worker] (FR-014)
       ↓                    日终 verify
[S3 WORM 归档] (FR-016, Phase 3)
       ↓
[Query API] → 操作链 API (admin only) / RFC 7807 错误 / FTS
       ↓
[Frontend Audit Page] → 7 类过滤 / 3 级颜色 / 一键处理
```

### 9.3 Detailed Design

#### 新增模块

| 路径 | 职责 |
|------|------|
| `meta/core/audit_constants.py` | AuditCategory/AuditLevel/Outcome 枚举 + normalize_user_name() |
| `meta/api/_problem_details.py` | RFC 7807 工厂方法 + 7 类 recovery 模板 |
| `meta/api/audit_operation_api.py` | 操作链 API (admin only) |
| `meta/services/audit_retry_worker.py` | 独立 daemon thread retry |
| `meta/services/audit_hash_chain.py` | row_hash + verify_chain() |
| `meta/scripts/cleanup_test_audit.py` | 脏数据清理 + cron |
| `meta/scripts/migrate_v318_audit.py` | ALTER TABLE + backfill |

#### 修改模块

| 文件 | 改动 |
|------|------|
| [meta/core/action_executor.py:108](file:///d:/filework/excel-to-diagram/meta/core/action_executor.py#L108) | log() 加 log_category/log_level/outcome 显式参数 |
| [meta/services/audit_service.py:114-163](file:///d:/filework/excel-to-diagram/meta/services/audit_service.py#L114-L163) | BatchAuditContext 修 schema drift |
| [meta/services/async_audit_writer.py](file:///d:/filework/excel-to-diagram/meta/services/async_audit_writer.py) | 集成 retry worker |
| [meta/api/audit_api.py](file:///d:/filework/excel-to-diagram/meta/api/audit_api.py) | 加 outcome/log_category 过滤, 返 object_display |
| [meta/api/_audit_helper.py](file:///d:/filework/excel-to-diagram/meta/api/_audit_helper.py) | 用 RFC 7807 |
| [meta/core/bo_framework.py](file:///d:/filework/excel-to-diagram/meta/core/bo_framework.py) | set_user_context 接 normalize |
| `scripts/service_manager.ps1` | 加 audit-worker 启动 |

#### 数据模型

```sql
-- TR-001: 8 字段
ALTER TABLE audit_logs ADD COLUMN outcome VARCHAR(20) DEFAULT 'success';
ALTER TABLE audit_logs ADD COLUMN cascade_root_id INTEGER;
ALTER TABLE audit_logs ADD COLUMN cascade_root_action VARCHAR(50);
ALTER TABLE audit_logs ADD COLUMN retention_until DATETIME;
ALTER TABLE audit_logs ADD COLUMN prev_hash CHAR(64);
ALTER TABLE audit_logs ADD COLUMN row_hash CHAR(64);

CREATE INDEX idx_audit_outcome ON audit_logs(outcome, created_at);
CREATE INDEX idx_audit_cascade ON audit_logs(cascade_root_action, object_type);
CREATE INDEX idx_audit_retention ON audit_logs(retention_until);
CREATE INDEX idx_audit_hash ON audit_logs(row_hash);
```

#### API 设计

```
[NEW] GET  /api/v2/audit/operation/<trace_id>      → 操作链 (admin only)
[NEW] GET  /api/v2/audit/diagnostics               → 健康度
[NEW] GET  /api/v2/audit/verify-chain              → 日终 hash 验证
[MOD] GET  /api/v2/audit/query                      → 加 outcome/log_category 过滤
[MOD] ALL  error responses                          → RFC 7807
[MOD] DELETE_BLOCKED                                → recovery hint
```

#### 主流程 (DELETE 触发 cascade)

```
1. POST /api/v2/bo/user_group/567 (删除)
2. bo_api.py: 验证权限, set_user_context (FR-006 标准化)
3. action_executor.py: DELETE action
4. deletion_service.py: 检查外键, 找阻止原因 (HAS_MEMBERS)
5. 抛 BusinessError(recovery={...}) (FR-002)
6. bo_api.py: ProblemDetails.user_group_not_empty() (FR-001)
7. 返 422 + RFC 7807 + recovery
8. 前端: "用户组下还有 12 个成员, 一键处理" 按钮

成功:
5'. deletion_service.py: DELETE
6'. cascade_interceptor.py: 5 个 DISSOCIATE
     透传 trace_id/user_agent + target_display + cascade_root_id
7'. 返 200
8'. 点"查看操作链" → FR-008 admin-only API 返完整链
```

### 9.4 Alternatives Considered

| 选项 | 决定 |
|------|------|
| outcome 字段 vs status 复用 | **outcome 字段** (NIST/GCP 都有, 语义清晰) |
| BatchAuditContext 修 vs 加字段 | **加字段** (本就是 schema drift, 修正) |
| Hash chain vs S3 Object Lock | **chain + S3 都要** (Phase 3 推迟 S3) |
| SQLite vs ClickHouse | **本期 SQLite, 大数据量后迁** |
| RFC 7807 一步 vs 双写 | **双写 2 周 + 切换 1 周 + 4 周废弃** (Stripe 12 月太长) |
| setInterval vs thread | **独立 daemon thread** (dev.to 警告) |
| cron vs thread (retry) | **thread** (立即响应, 不与 HTTP 共享生命周期) |

### 9.5 Implementation & Migration Plan

#### 实施顺序 (Step 1-9)

1. **Step 1: Schema 迁移** (TR-001) — 加 6 字段 + 4 索引, 低峰期
2. **Step 2: 常量与自动派生** (FR-003/004/005) — `audit_constants.py` + AuditLogger 加参数
3. **Step 3: 修 schema drift** (FR-011) — BatchAuditContext
4. **Step 4: 清理脏数据** (FR-007) — 1 SQL + backup
5. **Step 5: RFC 7807 + recovery** (FR-001/002) — _problem_details.py + 改各 API
6. **Step 6: 操作链 API + cascade 字段化** (FR-008/FR-009) — admin only
7. **Step 7: user_name 标准化** (FR-006) — backfill 2216 条
8. **Step 8: hash chain** (FR-014) — prev_hash/row_hash + verify
9. **Step 9: retry worker + cron** (FR-010/FR-013/FR-015) — 独立 thread + 周日 03:00

#### 风险与缓解

| 风险 | 缓解 |
|------|------|
| ALTER TABLE 锁表 | 低峰期, 选时机 |
| Backfill 慢 (2216 → 1M) | 分批 1000/批, 进度条 |
| RFC 7807 前端需协调 | Feature flag 双写 2 周 (TBD-5) |
| BatchAuditContext 修影响批量 | 优先 5/31 测试 → 批量 |
| 测试脏数据误删 | backup 表 + dry_run 默认 + 留 1 admin |
| hash chain sha256 开销 | 异步批量, 不阻塞业务 |

#### 测试策略

- **Unit**:
  - `test_audit_constants.py` — normalize 3 情况 + 7 类 category 映射
  - `test_problem_details.py` — 8 种错误
  - `test_hash_chain.py` — compute + verify 100 条
- **Integration** (扩展 `test_all_19_actions.py`):
  - 31/31 全跑 (不退化)
  - 操作链: 1 DELETE → 5 DISSOCIATE, 返 cascade_depth=1
  - DELETE_BLOCKED: 响应含 recovery
- **E2E** (`test_temp/audit_run_all_actions.py`):
  - log_category/log_level 填充率 100%
  - user_name 100% 标准化
  - 脏数据清理后 真实审计 100% 可读

#### 回滚计划

| Step | 回滚 |
|------|------|
| Step 1 ALTER | `ALTER TABLE DROP COLUMN` 可逆 |
| Step 2-3 代码 | `git revert` |
| Step 4 删脏数据 | backup INSERT |
| Step 5 RFC 7807 | Feature flag 关闭 |
| Step 6 操作链 API | disable 即可 |
| Step 7 user_name | revert + 历史保留 |
| Step 8 hash chain | 字段可删, 不影响业务 |
| Step 9 worker/cron | service_manager stop / 删 cron |

---

## 10. Resolved Decisions (TBD 全部解决)

| TBD | 决策 | 头部依据 |
|-----|------|---------|
| TBD-1 Hash chain | **本期 Must** (FR-014), S3 推迟 Phase 3 | GitHub Enterprise 有, Stripe/Linear 不做但有替代 |
| TBD-2 保留期 | **3 层**: security/authz=2y / business/admin=1y / access/system/cascade=90d | Linear 90d / Notion 180d / GitHub 90-120d / 中型共识 |
| TBD-3 API 权限 | **admin only** (IF-002 `@admin_required`) | Linear owner only / GitHub owner+security |
| TBD-4 admin 测试数据 | **全删** (含 admin 角色) | 安全优先 + user_factory 自动造 |
| TBD-5 RFC 7807 迁移 | **双写 2 周 + 切换 1 周 + 4 周废弃** (TR-003) | Stripe 12 月太长, 我们阶段 4-7 周合适 |
| TBD-6 retry worker | **独立 daemon thread** + service_manager (FR-010) | dev.to 警告 setInterval, Stripe 独立 process |
| TBD-7 清理 cron | **每周日 03:00 本地时区** (FR-015) | AWS 02:00 daily / 中型多按周 |
| TBD-8 S3 Object Lock | **本期不做**, Phase 3 (FR-016) | Linear/Notion 不强调, 中型 SaaS 非必须 |

---

## Spec + RFC 完整性自检

- ✅ **10 章节齐全** (Background, Types, FR, NFR, IF, TR, Constraints, Priorities, RFC, Resolved Decisions)
- ✅ **TBD 全部解决** (8 项明确, 在第 10 章节)
- ✅ **16 个 FR** (9 Must + 6 Should + 1 Could)
- ✅ **8 个 NFR** (性能/可靠性/可读性/防篡改)
- ✅ **3 个 IF** (查询/操作链/前端)
- ✅ **3 个 TR** (字段迁移/脏数据/API 双写)
- ✅ **基于实际实现** (28 字段真实 schema + 2216 条样本 + 代码定位)
- ✅ **头部产品对齐** (6 大中型 SaaS 调研)

---

**请确认 Spec + RFC, 授权后按 Step 1-9 顺序开始实施。**

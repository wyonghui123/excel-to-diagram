# Spec: 审计日志 v2 — Action 感知 + 通用记录 + 详情增强 (v1.0)

> **版本**: v1.0.0
> **日期**: 2026-06-05
> **状态**: 📋 草案 (Draft) — 等待用户确认
> **范围**: 后端 audit_service + action 模型 + 前端 AuditLog/AuditLogDetail 组件
> **架构依据**: [ARCHITECTURE_V2.md](file:///d:/filework/excel-to-diagram/docs/ARCHITECTURE_V2.md) §6
> **头部研究**: [Trailbase Audit Log Schema](https://trailbase.frozo.ai/blog/audit-log-schema-design-guide)、[Stripe Activity Logs](https://docs.stripe.com/activity-logs)、[AppMaster Unified Timeline](https://appmaster.io/blog/unified-audit-timeline-schema-ui)、[Azure Activity Log Schema](https://learn.microsoft.com/azure/azure-monitor/platform/activity-log-schema)
>
> **用户决策（2026-06-05）**：
> 1. Action 分类：**2 种** (InstanceAction / StaticAction)
> 2. 详情 UI：**基于现有 UI 组件和框架**（AuditLogDetail / Drawer / AppCollapse）
> 3. 记录范围：**全 object 通用 + opt-out**
> 4. 批量处理：**1 条聚合 + N 条明细**
> 5. 保留期：**Stripe 模式 6 个月**
>
> **版本对比**：
> - 现有 [audit_service.py:36-58](file:///d:/filework/excel-to-diagram/meta/services/audit_service.py#L36-L58) 的 `AuditRecord`（v1，20+ 字段）
> - v2 增强：新增 5 个字段（action_kind / outcome / parent_action_id / previous_hash / retention_until）
> - 详情 UI 增强：action_kind badge + outcome badge + RelatedEvents 条带

---

## 1. 背景与目标

### 1.1 背景

经过 2026-06-05 的 E2E 测试深入排查，发现审计日志体系存在 4 大问题：

1. **Action 与日志脱节**：[meta/core/action_dispatcher.py](file:///d:/filework/excel-to-diagram/meta/core/action_dispatcher.py) 是空壳（`raise NotImplementedError`），无法在 action 执行时自动记录日志
2. **日志内容结构松散**：[meta/services/audit_service.py:36-58](file:///d:/filework/excel-to-diagram/meta/services/audit_service.py#L36-L58) 的 `AuditRecord` 字段已较丰富（20+ 字段），但**action 类型无分类**、**无 outcome 字段**、**批量操作无关联**
3. **详情展示方案不统一**：[AuditLogDetail.vue](file:///d:/filework/excel-to-diagram/src/components/common/AuditLogDetail/AuditLogDetail.vue) 有 4 种渲染分支（Create/Delete/Associate/Update），但**无 StaticAction 支持**、**无失败/拒绝状态**
4. **action 模型"加强"未落地**：用户原话"加强 action 模型（instance 或者 static）"——目前 [action_handlers.py](file:///d:/filework/excel-to-diagram/meta/core/action_handlers.py) 已有 trigger handler（`clear_other_current_versions`），但**无 instance/static 分类**

### 1.2 业务目标

| 目标 | 衡量指标 |
|------|---------|
| **action 执行自动记录** | 所有 `/api/v2/bo/<type>/*` 接口 + 所有 action 声明，100% 自动产生 audit_log |
| **action 分类** | `action_kind` 字段必填：InstanceAction (绑实例) / StaticAction (不绑实例) |
| **outcome 标准化** | outcome ∈ {SUCCESS, FAILURE, DENIED, RETRY}，UI 显示状态 badge |
| **批量聚合** | 100 条记录创建 → 1 条 header (action='batch_create') + 100 条 detail (parent_action_id 关联) |
| **详情 UI 增强** | 基于现有 AuditLogDetail.vue 增加 3 个 panel：action_kind、outcome、RelatedEvents |
| **保留期 6 个月** | 6 个月前的日志自动归档到 `audit_logs_archive` 表（与 Stripe 一致） |

### 1.3 涉众目标

| 涉众 | 目标 | 影响 |
|------|------|------|
| 管理员/审计员 | 调查"谁动了我的数据" | 详情 UI 更清晰（action_kind + outcome + 字段 diff） |
| QA/支持 | 复现 bug 时需要操作历史 | 失败/重试可追溯 |
| 合规/法务 | 6 个月保留 + 不可篡改 | 6 个月归档 + hash 链（可选） |
| 后端开发 | action 执行自动记录 | 不需要每个 handler 手动调用 audit |
| 前端开发 | 详情 UI 与列表 UI 一致 | 基于现有 Drawer + AppCollapse |

### 1.4 范围与边界

**本次 Spec 覆盖**：

1. **后端 action 模型强化**（P0）：
   - `ActionKind` 枚举：InstanceAction / StaticAction
   - `ActionOutcome` 枚举：SUCCESS / FAILURE / DENIED / RETRY
   - `Action` 元数据：声明 `kind` + 默认 `audit: true`
2. **AuditRecord v2 增强**（P0）：
   - 新增 5 个字段（兼容 v1）
3. **通用记录机制**（P0）：
   - 拦截器自动记录
   - opt-out 通过 `audit: false` 声明
4. **批量聚合**（P1）：
   - `BatchAuditContext` helper
5. **前端详情 UI 增强**（P1）：
   - action_kind badge + outcome badge
   - RelatedEvents panel（基于 AppCollapse）
6. **保留期 6 个月**（P2）：
   - 后台 cron 归档脚本

**不在本次范围**：
- hash 链防篡改（标记为 v3 特性）
- 实时事件流（WebSocket / SSE）— 标记为 v3
- 第三方 SIEM 集成 — 标记为 v3

---

## 2. 现状与差距分析

### 2.1 现有组件盘点

| 组件 | 路径 | 状态 | v2 改造点 |
|------|------|:---:|----------|
| **后端 AuditRecord** | [meta/services/audit_service.py:36-58](file:///d:/filework/excel-to-diagram/meta/services/audit_service.py#L36-L58) | v1 | +5 字段 |
| **后端 AuditService** | [meta/services/audit_service.py](file:///d:/filework/excel-to-diagram/meta/services/audit_service.py) | ✅ 完整 | +batch helper + archive script |
| **后端 ActionDispatcher** | [meta/core/action_dispatcher.py](file:///d:/filework/excel-to-diagram/meta/core/action_dispatcher.py) | ❌ 空壳 | 补 execute_sync/async 实现 |
| **后端 ActionHandlers** | [meta/core/action_handlers.py](file:///d:/filework/excel-to-diagram/meta/core/action_handlers.py) | ✅ 有 trigger | 增强 metadata |
| **前端 AuditLog 列表** | [src/components/common/AuditLog/AuditLog.vue](file:///d:/filework/excel-to-diagram/src/components/common/AuditLog/AuditLog.vue) | ✅ 完整 | +action_kind/outcome 列 |
| **前端 AuditLogDetail** | [src/components/common/AuditLogDetail/AuditLogDetail.vue](file:///d:/filework/excel-to-diagram/src/components/common/AuditLogDetail/AuditLogDetail.vue) | ✅ 4 分支 | +action_kind/outcome/RelatedEvents |
| **前端 auditLogMeta** | [src/views/SystemManagement/meta/auditLogMeta.js](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/meta/auditLogMeta.js) | ✅ 完整 | +2 列 + filters |
| **前端 useAuditLogs** | [src/composables/useAuditLogs.js](file:///d:/filework/excel-to-diagram/src/composables/useAuditLogs.js) | ✅ 基础 | +loadRelatedEvents + filters |

### 2.2 头部产品研究

| 产品 | 关键做法 | 我们要采纳 |
|------|---------|-----------|
| **Trailbase Audit Log Schema** | 5W 模型 + 必需字段（event_id/timestamp/actor/action/resource/outcome）| 沿用 5W；outcome 必填 |
| **Stripe Activity Logs** | `resource.verb` 命名（如 `api_key_created`）+ 6 月保留 | 6 月保留（已确认） |
| **AppMaster Unified Timeline** | 事件分类（access/data/workflow/integration/admin-security）+ RelatedEvents 条带 | RelatedEvents 折 |
| **C# Corner 字段级审计** | AuditHeader + AuditDetail 1:n + 并排 old/new 对比 | 已有但需增强 |
| **Azure Activity Log Schema** | severity 等级 | 我们已用 log_level，保留 |

### 2.3 横向问题

- **action 命名不一致**：现有 [auditLogMeta.js:79-84](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/meta/auditLogMeta.js#L79-L84) 用 `CREATE/UPDATE/DELETE/ASSOCIATE/DISSOCIATE` 全大写，**应统一为 `resource.verb` 格式**（如 `user.created`）
- **action_kind 未定义**：当前 [AuditRecord.action](file:///d:/filework/excel-to-diagram/meta/services/audit_service.py#L40) 是字符串，无 kind 分类
- **批量无聚合**：100 条导入 → 100 条独立日志，无法看总量
- **失败无 outcome**：当前 action 失败时通常不写日志（只写 error log），无审计追溯

---

## 3. 目标架构

### 3.1 强化后的 Action 模型

```
┌──────────────────────────────────────────────────────────┐
│  Action Metadata (YAML)                                  │
│  - id: "set_current_version"                              │
│  - kind: "instance"  ← 🆕 NEW: InstanceAction            │
│  - audit: true  ← 🆕 NEW: 默认自动记录                   │
│  - handler: "clear_other_current_versions"                 │
│  - category: "business"                                   │
└──────────────────────────────────────────────────────────┘
                ↓ 加载到
┌──────────────────────────────────────────────────────────┐
│  ActionRegistry (内存)                                    │
│  - id → {kind, audit, handler, category, ...}            │
└──────────────────────────────────────────────────────────┘
                ↓ 调用
┌──────────────────────────────────────────────────────────┐
│  ActionDispatcher.execute_sync()  ← 🆕 实现 (非空壳)    │
│  1. 参数校验                                              │
│  2. before-triggers                                       │
│  3. handler 执行 (带 outcome 捕获)                        │
│  4. after-triggers                                        │
│  5. audit 记录 ← 🆕 自动 (除非 audit=false)               │
└──────────────────────────────────────────────────────────┘
```

### 3.2 通用记录机制

```
[UI/Client] → POST /api/v2/bo/<type>
       ↓
[bo_api.py] → _execute_core()
       ↓
[Interceptors]
  ├─ persistence_interceptor (业务表写入)
  ├─ audit_interceptor ← 🆕 增强：默认拦截所有 /api/v2/bo/*
  │    ├─ 自动从 url 提取 object_type / object_id
  │    ├─ 自动从 method 提取 action verb
  │    ├─ 异常捕获 → outcome=FAILURE
  │    ├─ 403 → outcome=DENIED
  │    └─ 写入 audit_logs 表 (除非 action_meta.audit=false)
  └─ ...
```

### 3.3 详情 UI 增强

基于现有 [AuditLogDetail.vue](file:///d:/filework/excel-to-diagram/src/components/common/AuditLogDetail/AuditLogDetail.vue)（Drawer）增加 3 个 panel：

```
┌─ Drawer 480px ─────────────────────────────────┐
│ [Header]                                        │
│   🔵 UPDATE | ✅ SUCCESS | 📌 InstanceAction   │
│   2026-06-05 14:30:25 by alice@co.com          │
├─────────────────────────────────────────────────┤
│ [Info Panel]                                    │
│   对象类型: user                                │
│   对象ID: 42                                    │
│   IP: 192.168.1.1                              │
│   Trace: abc-123                                │
├─────────────────────────────────────────────────┤
│ [Action Kind]  ← 🆕 NEW                         │
│   ┌──────────┬──────────┬──────────┐           │
│   │Instance  │ Static   │ Parent   │           │
│   │✓         │          │ -        │           │
│   └──────────┴──────────┴──────────┘           │
├─────────────────────────────────────────────────┤
│ [Outcome]  ← 🆕 NEW                              │
│   Status: ✅ SUCCESS                            │
│   Error: -                                      │
│   Duration: 142ms                               │
├─────────────────────────────────────────────────┤
│ [Field-level Diff]  (已有)                      │
│   field | old | new                            │
│   name  | Ali  | Alice                         │
│   role  | user | admin                         │
├─────────────────────────────────────────────────┤
│ [RelatedEvents]  ← 🆕 NEW (AppCollapse 折叠)   │
│   ▼ 父操作: batch_update_users (5 records)     │
│     └── audit_log #100: header                 │
│   ▶ 子操作 (3)                                 │
└─────────────────────────────────────────────────┘
```

---

## 4. 功能需求

### 4.1 后端 — Action 模型强化

#### FR-LOG-001：ActionKind 枚举

- **描述**：在 `meta/core/action_models.py` 定义 `ActionKind` 枚举（2 种）
- **验收标准**：
  ```python
  class ActionKind(Enum):
      INSTANCE = "instance"  # 绑定到具体实例 (e.g., set_current_version on product #42)
      STATIC = "static"      # 不绑实例 (e.g., export_all_users, batch_reset_passwords)
  ```
- **优先级**：Must
- **类型映射**：Solution
- **来源**：用户决策

#### FR-LOG-002：ActionOutcome 枚举

- **描述**：在 `meta/core/action_models.py` 定义 `ActionOutcome` 枚举（4 种）
- **验收标准**：
  ```python
  class ActionOutcome(Enum):
      SUCCESS = "success"   # 成功
      FAILURE = "failure"   # 失败（异常）
      DENIED = "denied"     # 拒绝（无权限/校验失败）
      RETRY = "retry"       # 重试中
  ```
- **优先级**：Must
- **类型映射**：Solution

#### FR-LOG-003：Action 声明 schema 增强

- **描述**：YAML 中 action 声明支持 `kind` + `audit` 字段
- **验收标准**：
  ```yaml
  actions:
    - id: "set_current_version"
      kind: "instance"          # 🆕
      audit: true               # 🆕 默认 true
      handler: "clear_other_current_versions"

    - id: "export_all_users"
      kind: "static"            # 🆕
      audit: false              # 🆕 opt-out：不记录
      handler: "export_handler"
  ```
- **优先级**：Must
- **类型映射**：Solution

#### FR-LOG-004：ActionDispatcher 实现

- **描述**：[meta/core/action_dispatcher.py](file:///d:/filework/excel-to-diagram/meta/core/action_dispatcher.py) 实现 `execute_sync`
- **验收标准**：
  - 完整实现（非 NotImplementedError）
  - 异常捕获 → outcome=FAILURE
  - 401/403 → outcome=DENIED
  - 调用前/后 trigger
  - 自动写 audit（除非 `audit: false`）
- **优先级**：Must
- **依赖**：FR-LOG-001/002/003

### 4.2 后端 — AuditRecord v2 增强

#### FR-LOG-005：AuditRecord 新增 5 字段

- **描述**：[meta/services/audit_service.py](file:///d:/filework/excel-to-diagram/meta/services/audit_service.py) 的 `AuditRecord` dataclass 新增：
  ```python
  @dataclass
  class AuditRecord:
      # ... v1 20 字段 ...
      action_kind: Optional[str] = None       # 🆕 'instance' | 'static'
      outcome: Optional[str] = None          # 🆕 'success' | 'failure' | 'denied' | 'retry'
      parent_action_id: Optional[Any] = None # 🆕 批量聚合
      error_message: Optional[str] = None     # 🆕 失败/拒绝时记录
      retention_until: Optional[str] = None  # 🆕 6 月保留截止时间
  ```
- **优先级**：Must
- **兼容性**：v1 字段全部保留（向后兼容）
- **DB 迁移**：`ALTER TABLE audit_logs ADD COLUMN action_kind TEXT;` 等 5 条

#### FR-LOG-006：通用记录机制（自动拦截）

- **描述**：[meta/core/interceptors/audit_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/audit_interceptor.py) 默认拦截所有 `/api/v2/bo/<type>/*` 接口
- **验收标准**：
  - 自动从 URL 提取 `object_type` / `object_id`
  - 自动从 HTTP method 推断 action verb：
    - `POST` → `created`
    - `PUT/PATCH` → `updated`
    - `DELETE` → `deleted`
  - 自动从 `action_meta.audit` 决定是否记录
  - 异常 → outcome=FAILURE
  - 401/403 → outcome=DENIED
  - 100% 覆盖：所有 `/api/v2/bo/*` 接口调用都自动产生 audit
- **优先级**：Must

#### FR-LOG-007：批量聚合 helper

- **描述**：新增 `BatchAuditContext` context manager
- **验收标准**：
  ```python
  with BatchAuditContext(action='batch_create_users', object_type='user') as batch:
      for user_data in user_list:
          result = await user_service.create(user_data)
          # 自动产生 1 条 header + N 条 detail
          batch.add_detail(object_id=result.id, outcome='success')
  ```
- **优先级**：Should
- **依赖**：FR-LOG-006

#### FR-LOG-008：6 月保留归档

- **描述**：新增 `meta/scripts/archive_audit_logs.py` cron 脚本
- **验收标准**：
  - 每天 0:00 跑
  - `retention_until < NOW()` 的日志移到 `audit_logs_archive` 表
  - 保留原表 `audit_logs` 中 6 月内的记录
  - 归档操作写 meta-log（自己产生的归档操作也审计）
- **优先级**：Could
- **依赖**：FR-LOG-005（retention_until 字段）

### 4.3 前端 — 详情 UI 增强

#### FR-LOG-009：action_kind badge

- **描述**：[AuditLogDetail.vue](file:///d:/filework/excel-to-diagram/src/components/common/AuditLogDetail/AuditLogDetail.vue) 增加 action_kind badge
- **验收标准**：
  - 在 Header 区域显示：`📌 InstanceAction` 或 `🌐 StaticAction`
  - 用现有 `el-tag` 组件
  - 颜色：instance=primary, static=info
- **优先级**：Should
- **依赖**：现有 [AuditLogDetail.vue](file:///d:/filework/excel-to-diagram/src/components/common/AuditLogDetail/AuditLogDetail.vue) 已有 badge 模式

#### FR-LOG-010：outcome badge + error_message

- **描述**：AuditLogDetail 新增 outcome panel
- **验收标准**：
  - 在 Action Kind panel 下方显示 Outcome panel
  - badge：`✅ SUCCESS` / `❌ FAILURE` / `🚫 DENIED` / `🔄 RETRY`
  - 失败时显示 error_message
  - 显示 duration_ms（从 audit_log.duration 字段）
- **优先级**：Should

#### FR-LOG-011：RelatedEvents panel

- **描述**：AuditLogDetail 新增 RelatedEvents 折叠面板
- **验收标准**：
  - 用现有 `AppCollapse` 组件
  - 父操作：显示 `batch_*` 头部摘要 + 子操作数量
  - 子操作：显示同 `parent_action_id` 的所有 detail
  - 每条 related event 可点击跳到自己的详情（递归嵌套）
  - 无 parent_action_id 时整 panel 隐藏
- **优先级**：Should
- **依赖**：现有 [AppCollapse.vue](file:///d:/filework/excel-to-diagram/src/components/common/AppCollapse/AppCollapse.vue)

#### FR-LOG-012：列表列扩展

- **描述**：[auditLogMeta.js](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/meta/auditLogMeta.js) 增加 2 列
- **验收标准**：
  - 新增 `action_kind` 列（type=tag，options=[instance, static]）
  - 新增 `outcome` 列（type=tag，options=[success, failure, denied, retry]）
  - 列表 filters 支持 action_kind 和 outcome
- **优先级**：Should

#### FR-LOG-013：useAuditLogs 增强

- **描述**：[useAuditLogs.js](file:///d:/filework/excel-to-diagram/src/composables/useAuditLogs.js) 增加 `loadRelatedEvents`
- **验收标准**：
  ```javascript
  const { logs, total, loadRelatedEvents } = useAuditLogs(type, id)
  // 获取同 transaction_id / parent_action_id 的所有相关事件
  const related = await loadRelatedEvents(transactionId)
  ```
- **优先级**：Should

---

## 5. 非功能需求

### NFR-LOG-001：性能

- audit_log 写入延迟：< 50ms（P95）
- audit_log 列表查询（20 条）：< 200ms（P95）
- 详情页加载：< 300ms（P95）

### NFR-LOG-002：兼容性

- v1 的 20 字段全部保留（已部署）
- v2 新增 5 字段 nullable（旧记录无值不报错）
- 前端 AuditLogDetail 兼容 v1/v2 数据（v1 缺字段时 UI 隐藏对应 panel）

### NFR-LOG-003：可观测性

- 每次 audit 写入带 trace_id（与已有 transaction_id 关联）
- outcome=FAILURE 自动告警（飞书/Slack 通知）
- 后台 cron 归档失败告警

### NFR-LOG-004：可测试性

- action_dispatcher 单元测试覆盖率 ≥ 95%
- audit_service 单测覆盖 FR-LOG-005/006/007
- 前端 AuditLogDetail.spec.js 覆盖 4 个 panel

### NFR-LOG-005：可逆性

- 新增字段均可回滚（`ALTER TABLE ... DROP COLUMN`）
- 新增 panel 可禁用（feature flag: `AUDIT_V2_ENABLED`）

---

## 6. 外部接口

### IF-LOG-001：audit_logs 表 schema 变更

```sql
-- 5 个新字段（v2）
ALTER TABLE audit_logs ADD COLUMN action_kind TEXT;          -- 'instance' | 'static'
ALTER TABLE audit_logs ADD COLUMN outcome TEXT;              -- 'success' | 'failure' | 'denied' | 'retry'
ALTER TABLE audit_logs ADD COLUMN parent_action_id INTEGER;  -- FK to audit_logs.id
ALTER TABLE audit_logs ADD COLUMN error_message TEXT;        -- 失败原因
ALTER TABLE audit_logs ADD COLUMN retention_until TEXT;      -- ISO 8601 截止时间

-- 归档表（v2）
CREATE TABLE audit_logs_archive (
  id INTEGER PRIMARY KEY,
  archived_at TEXT NOT NULL,
  -- ... 全部原字段 ...
  -- 索引：同 audit_logs
);

-- 索引（v2）
CREATE INDEX idx_audit_parent ON audit_logs(parent_action_id);
CREATE INDEX idx_audit_outcome ON audit_logs(outcome);
CREATE INDEX idx_audit_action_kind ON audit_logs(action_kind);
CREATE INDEX idx_audit_retention ON audit_logs(retention_until);
```

### IF-LOG-002：API 响应 v2 字段

```json
{
  "id": 123,
  "object_type": "user",
  "object_id": 42,
  "action": "user.updated",
  "action_kind": "instance",          // 🆕
  "outcome": "success",                // 🆕
  "parent_action_id": null,            // 🆕
  "error_message": null,               // 🆕
  "retention_until": "2026-12-05T...", // 🆕
  "field_name": "name",
  "old_value": "Ali",
  "new_value": "Alice",
  "user_id": 1,
  "user_name": "alice@co.com",
  "ip_address": "192.168.1.1",
  "user_agent": "Mozilla/5.0...",
  "created_at": "2026-06-05T14:30:25Z",
  "trace_id": "abc-123",
  "transaction_id": "tx-456",
  "log_category": "business",
  "log_level": "INFO"
}
```

---

## 7. 过渡要求

### TR-LOG-001：DB schema 迁移

- 5 个 `ALTER TABLE` 操作
- 兼容 SQLite/PostgreSQL（项目两种 DB 都支持）
- 迁移脚本：`meta/migrations/v2_001_audit_log_v2.sql`
- 回滚：`ALTER TABLE ... DROP COLUMN` 5 次

### TR-LOG-002：渐进式启用

- 后端：v2 字段先 nullable，旧数据无值
- 前端：v1 数据缺字段时 UI 隐藏对应 panel
- feature flag：`AUDIT_V2_ENABLED`（默认 true）
- 完整切换 1 季度后，清理 v1 兼容代码

---

## 8. 约束与假设

### 8.1 技术约束

- DB：SQLite（主）+ PostgreSQL（备），schema 必须双兼容
- 后端：Python 3.14 + Flask + SQLAlchemy
- 前端：Vue 3 + Element Plus + 现有 UI 组件（Drawer/AppCollapse/AppModal）
- 测试框架：pytest + vitest

### 8.2 业务约束

- 6 个月保留期（已与用户确认）
- action 模型 2 分类（已与用户确认）
- 全 object 通用记录 + opt-out（已与用户确认）
- 批量聚合 1+N（已与用户确认）
- 详情 UI 基于现有框架（已与用户确认）

### 8.3 假设

- 现有 [AuditLogDetail.vue](file:///d:/filework/excel-to-diagram/src/components/common/AuditLogDetail/AuditLogDetail.vue) 的 4 分支渲染结构稳定
- 现有 [auditLogMeta.js](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/meta/auditLogMeta.js) 的列表元数据驱动模式可扩展
- action 声明从 YAML 加载的路径已稳定

---

## 9. 优先级与里程碑

| ID | 需求 | 优先级 | 工作量 | 依赖 |
|----|------|:---:|:---:|------|
| FR-LOG-001 | ActionKind 枚举 | Must | 0.1 d | — |
| FR-LOG-002 | ActionOutcome 枚举 | Must | 0.1 d | — |
| FR-LOG-003 | Action schema 增强 | Must | 0.2 d | FR-LOG-001/002 |
| FR-LOG-004 | ActionDispatcher 实现 | Must | 1.5 d | FR-LOG-003 |
| FR-LOG-005 | AuditRecord v2 字段 | Must | 0.5 d | — |
| FR-LOG-006 | 通用记录机制 | Must | 1.5 d | FR-LOG-004/005 |
| FR-LOG-007 | 批量聚合 helper | Should | 1 d | FR-LOG-006 |
| FR-LOG-008 | 6 月保留归档 | Could | 1 d | FR-LOG-005 |
| FR-LOG-009 | action_kind badge | Should | 0.3 d | FR-LOG-005 |
| FR-LOG-010 | outcome badge | Should | 0.3 d | FR-LOG-005 |
| FR-LOG-011 | RelatedEvents panel | Should | 1 d | FR-LOG-007 |
| FR-LOG-012 | 列表列扩展 | Should | 0.3 d | FR-LOG-005 |
| FR-LOG-013 | useAuditLogs 增强 | Should | 0.5 d | FR-LOG-011 |

**总工作量**：~8 d

**里程碑**：
- **M1（3 d）**：后端 P0（FR-LOG-001~006）— 通用记录机制可工作
- **M2（2 d）**：后端批量聚合（FR-LOG-007）+ 前端详情 UI（FR-LOG-009/010）
- **M3（2 d）**：前端列表 + RelatedEvents（FR-LOG-011/012/013）
- **M4（1 d）**：归档脚本（FR-LOG-008，可推迟到 P2）

---

## 10. 变更 / 设计提案 (RFC)

### 10.1 As-Is 分析

- **当前架构**：
  - 后端：AuditRecord 20+ 字段 + audit_service CRUD + audit_interceptor（手动调用）
  - 前端：AuditLog（列表）+ AuditLogDetail（详情 Drawer，4 分支渲染）
- **当前问题**：
  - action_dispatcher 空壳，action 执行不自动写日志
  - 无 action_kind / outcome / 批量聚合
  - 详情 UI 不支持 StaticAction / 失败状态
- **关键代码路径**：
  - [meta/core/action_dispatcher.py:12-18](file:///d:/filework/excel-to-diagram/meta/core/action_dispatcher.py#L12-L18) — 空壳
  - [meta/services/audit_service.py:36-58](file:///d:/filework/excel-to-diagram/meta/services/audit_service.py#L36-L58) — AuditRecord v1
  - [src/components/common/AuditLogDetail/AuditLogDetail.vue:1-80](file:///d:/filework/excel-to-diagram/src/components/common/AuditLogDetail/AuditLogDetail.vue#L1-L80) — 现有 4 分支

### 10.2 Target State

- **目标架构**：
  - 后端：ActionDispatcher 完整实现 + AuditRecord v2（+5 字段）+ 通用拦截器
  - 前端：AuditLogDetail 增强（action_kind/outcome/RelatedEvents 3 个 panel）
- **关键变更**：
  1. 新建 `meta/core/action_models.py`（ActionKind + ActionOutcome 枚举）
  2. 改造 [action_dispatcher.py](file:///d:/filework/excel-to-diagram/meta/core/action_dispatcher.py) — 完整实现
  3. 改造 [audit_service.py](file:///d:/filework/excel-to-diagram/meta/services/audit_service.py) — AuditRecord v2
  4. 改造 [audit_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/audit_interceptor.py) — 通用拦截
  5. 改造 [AuditLogDetail.vue](file:///d:/filework/excel-to-diagram/src/components/common/AuditLogDetail/AuditLogDetail.vue) — 3 个新 panel
  6. 改造 [auditLogMeta.js](file:///d:/filework/excel-to-diagram/src/views/SystemManagement/meta/auditLogMeta.js) — +2 列
  7. 改造 [useAuditLogs.js](file:///d:/filework/excel-to-diagram/src/composables/useAuditLogs.js) — loadRelatedEvents
  8. 新建 `meta/scripts/archive_audit_logs.py` — 6 月归档

### 10.3 Detailed Design

#### 10.3.1 数据模型（v2 AuditRecord）

```python
# meta/services/audit_service.py:36-58 (v1 → v2)
@dataclass
class AuditRecord:
    # ... v1 20 字段全部保留 ...
    id: Any
    object_type: str
    object_id: Any
    action: str                      # 改为 'resource.verb' 格式 (e.g., 'user.updated')
    field_name: str
    old_value: Any
    new_value: Any
    user_id: Any
    user_name: str
    ip_address: str
    user_agent: str
    created_at: str
    trace_id: Optional[str] = None
    transaction_id: Optional[str] = None
    status: Optional[str] = None
    agent_id: Optional[str] = None
    agent_session_id: Optional[str] = None
    tool_call_id: Optional[str] = None
    agent_reasoning: Optional[str] = None
    log_category: Optional[str] = None
    log_level: Optional[str] = None

    # 🆕 v2 新增 5 字段（全部 nullable，兼容 v1）
    action_kind: Optional[str] = None       # 'instance' | 'static'
    outcome: Optional[str] = None          # 'success' | 'failure' | 'denied' | 'retry'
    parent_action_id: Optional[Any] = None # 批量聚合 FK
    error_message: Optional[str] = None    # 失败/拒绝原因
    retention_until: Optional[str] = None  # 6 月截止（ISO 8601）
```

#### 10.3.2 ActionDispatcher 实现

```python
# meta/core/action_dispatcher.py:12 (v1 空壳 → v2 实现)
class ActionDispatcher:
    def __init__(self, action_registry, audit_service):
        self.registry = action_registry
        self.audit = audit_service

    def execute_sync(self, action_id: str, params: dict, context: dict) -> dict:
        action_meta = self.registry.get(action_id)
        if not action_meta:
            raise ValueError(f"Unknown action: {action_id}")

        outcome = ActionOutcome.SUCCESS
        error_msg = None
        result = None
        start_time = time.time()

        try:
            # 1. before-triggers
            self._run_triggers(action_meta.before_triggers, params, context)

            # 2. handler 执行
            handler = self.registry.get_handler(action_meta.handler)
            result = handler(params, context)

        except PermissionError as e:
            outcome = ActionOutcome.DENIED
            error_msg = str(e)
            raise
        except Exception as e:
            outcome = ActionOutcome.FAILURE
            error_msg = str(e)
            raise
        finally:
            # 3. after-triggers
            self._run_triggers(action_meta.after_triggers, params, context, result)

            # 4. 自动写 audit (除非 audit=false)
            if action_meta.audit:
                self._auto_audit(action_meta, params, context, result, outcome, error_msg, start_time)

        return result

    def _auto_audit(self, action_meta, params, context, result, outcome, error_msg, start_time):
        duration_ms = int((time.time() - start_time) * 1000)
        retention_until = (datetime.utcnow() + timedelta(days=180)).isoformat()

        self.audit.create(AuditRecord(
            object_type=action_meta.object_type,
            object_id=params.get('object_id') or params.get('id'),
            action=action_meta.resource_verb,  # e.g., 'user.updated'
            action_kind=action_meta.kind.value,  # 'instance' or 'static'
            outcome=outcome.value,
            error_message=error_msg,
            retention_until=retention_until,
            user_id=context.get('user_id'),
            user_name=context.get('user_name'),
            ip_address=context.get('ip_address'),
            user_agent=context.get('user_agent'),
            trace_id=context.get('trace_id'),
            transaction_id=context.get('transaction_id'),
            log_category=action_meta.category,  # 'business' | 'security' | ...
            log_level='INFO' if outcome == ActionOutcome.SUCCESS else 'ERROR',
        ))
```

#### 10.3.3 通用记录机制（audit_interceptor）

```python
# meta/core/interceptors/audit_interceptor.py
class AuditInterceptor:
    """默认拦截所有 /api/v2/bo/<type>/*"""

    def __init__(self, audit_service, action_registry):
        self.audit = audit_service
        self.registry = action_registry

    def after_action(self, request, response, context):
        # 1. 自动从 URL 提取 object_type / object_id
        object_type = self._extract_object_type(request.url)
        object_id = self._extract_object_id(request.url, response)

        # 2. 自动从 method + action 声明推断 verb
        action_meta = self._resolve_action_meta(request, object_type)
        if not action_meta or not action_meta.audit:
            return  # opt-out

        # 3. 异常 → outcome=FAILURE
        outcome = self._determine_outcome(response)

        # 4. 写 audit
        self.audit.create(AuditRecord(
            object_type=object_type,
            object_id=object_id,
            action=f"{object_type}.{action_meta.verb}",
            action_kind=action_meta.kind.value,
            outcome=outcome,
            # ... 其他上下文 ...
        ))
```

#### 10.3.4 详情 UI 3 个 Panel（基于现有组件）

```vue
<!-- src/components/common/AuditLogDetail/AuditLogDetail.vue (v2) -->

<template>
  <el-drawer :model-value="visible" title="变更详情" size="480px">
    <!-- 现有 Header / Info / Summary 保留 -->

    <!-- 🆕 Panel 1: Action Kind -->
    <div v-if="log.action_kind" class="ald-panel">
      <h4>Action 类型</h4>
      <el-tag :type="log.action_kind === 'instance' ? 'primary' : 'info'">
        {{ log.action_kind === 'instance' ? '📌 InstanceAction' : '🌐 StaticAction' }}
      </el-tag>
    </div>

    <!-- 🆕 Panel 2: Outcome -->
    <div v-if="log.outcome" class="ald-panel">
      <h4>执行结果</h4>
      <el-tag :type="outcomeTagType">
        {{ outcomeIcon }} {{ outcomeLabel }}
      </el-tag>
      <div v-if="log.error_message" class="ald-error">错误: {{ log.error_message }}</div>
      <div v-if="log.duration_ms" class="ald-duration">耗时: {{ log.duration_ms }}ms</div>
    </div>

    <!-- 现有 Field-level Diff 保留 -->

    <!-- 🆕 Panel 3: RelatedEvents (AppCollapse 折叠) -->
    <AppCollapse v-if="hasRelatedEvents" class="ald-panel" title="相关操作">
      <div v-if="log.parent_action_id">
        <strong>父操作</strong>: {{ relatedHeader?.action }} ({{ relatedHeader?.object_type }}#{{ relatedHeader?.object_id }})
      </div>
      <div v-if="relatedChildren.length > 0">
        <strong>子操作</strong> ({{ relatedChildren.length }}):
        <ul>
          <li v-for="child in relatedChildren" :key="child.id"
              @click="$emit('selectLog', child)" class="ald-related-item">
            {{ child.action }} - {{ child.object_type }}#{{ child.object_id }}
            <el-tag size="small" :type="outcomeTagType(child.outcome)">{{ child.outcome }}</el-tag>
          </li>
        </ul>
      </div>
    </AppCollapse>
  </el-drawer>
</template>
```

#### 10.3.5 批量聚合 helper

```python
# meta/services/audit_service.py (新增)
class BatchAuditContext:
    def __init__(self, action: str, object_type: str, audit_service, user_context):
        self.action = action
        self.object_type = object_type
        self.audit = audit_service
        self.user_ctx = user_context
        self.header_id = None
        self.details = []

    def __enter__(self):
        # 1. 创建 header
        self.header_id = self.audit.create(AuditRecord(
            object_type=self.object_type,
            object_id='batch',  # 标记为批量
            action=self.action,
            action_kind='static',  # 批量操作通常是 static
            outcome='success',
            user_id=self.user_ctx.get('user_id'),
            # ...
        ))
        return self

    def add_detail(self, object_id, outcome='success', error_msg=None):
        self.audit.create(AuditRecord(
            object_type=self.object_type,
            object_id=object_id,
            action=self.action.replace('batch_', ''),  # e.g., 'batch_create' → 'create'
            action_kind='instance',
            outcome=outcome,
            error_message=error_msg,
            parent_action_id=self.header_id,
            # ...
        ))

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            # batch 整体失败
            self.audit.update(self.header_id, outcome='failure', error_message=str(exc_val))
        return False  # 不吞异常
```

### 10.4 备选方案

| 方案 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| 2 种 action_kind (instance/static) | 简单 | 不能表达 workflow/auth | ✅ 用户决策 |
| 4 种 action_kind | 更精细 | 过度设计 | ❌ |
| 6 种 action_kind (CRUD/WORKFLOW/AUTH/ADMIN/INTEGRATION/SYSTEM) | 对齐 Stripe+Azure | 复杂 | ❌ |
| 详情 UI 全自定义 | 灵活 | 破坏现有 UI 体系 | ❌ |
| 详情 UI 基于现有 (Drawer+AppCollapse) | 一致性 + 复用 | 受限于现有组件 | ✅ 用户决策 |
| 全量记录 (无 opt-out) | 完整 | 高频静态 action 噪声大 | ❌ |
| 全 object + opt-out | 灵活 + 简洁 | 默认值需谨慎 | ✅ 用户决策 |
| 100 条独立日志 | 简单 | 表增长快 | ❌ |
| 1 条聚合 (无明细) | 极简 | 丢失细节 | ❌ |
| 1+N 聚合 | 头尾兼顾 | 复杂度 | ✅ 用户决策 |
| 永久保留 | 开发友好 | 存储成本 | ❌ |
| 7 年保留 | 合规最强 | 成本 | ❌ |
| 6 月保留 | Stripe 行业标准 | 需归档 | ✅ 用户决策 |

### 10.5 实施与迁移计划

- **实施顺序**：
  1. FR-LOG-001/002：建枚举（0.2 d）
  2. FR-LOG-003：YAML schema 增强（0.2 d）
  3. FR-LOG-005：DB schema 迁移（0.5 d）
  4. FR-LOG-004：ActionDispatcher 实现（1.5 d）
  5. FR-LOG-006：通用拦截器（1.5 d）
  6. FR-LOG-009/010/011：详情 UI 3 panel（1.6 d）
  7. FR-LOG-012/013：列表 + composable（0.8 d）
  8. FR-LOG-007：批量 helper（1 d）
  9. FR-LOG-008：6 月归档（1 d，可推迟）
- **风险缓解**：
  - 后端：先在测试环境跑 DB 迁移，验证 v1 数据兼容
  - 前端：v1 数据缺字段时 UI 隐藏对应 panel
  - 渐进式：feature flag `AUDIT_V2_ENABLED`
- **测试策略**：
  - 单元：action_dispatcher 95%，audit_service 90%
  - 集成：现有 8 个 E2E spec 继续通过
  - E2E：新增 spec 覆盖 action_kind/outcome/RelatedEvents
- **回滚计划**：
  - DB：`ALTER TABLE ... DROP COLUMN` 5 次
  - 后端：git revert
  - 前端：feature flag 关闭

---

## 11. TBD List

| ID | 项 | 状态 |
|----|----|------|
| TBD-1 | hash 链防篡改（previous_hash 字段） | 推迟到 v3 |
| TBD-2 | 实时事件流（WebSocket/SSE） | 推迟到 v3 |
| TBD-3 | SIEM 集成（Splunk/ELK） | 推迟到 v3 |
| TBD-4 | 归档操作自身的审计（archive_audit_logs 跑完后写 audit） | FR-LOG-008 已包含 |
| TBD-5 | 敏感字段脱敏（password/token 在日志中不存明文） | 需细化 |
| TBD-6 | 导出 CSV/Excel 的 API | 推迟到 M3 后 |

**TBD-5 紧急性**：中等。需在 FR-LOG-005 实施时一并处理：在 audit 写入时检测 `field_name in ['password', 'token', 'secret']` 自动 redact。

---

## 12. 完整性声明

- Spec + RFC 包含 **11 节**（§1 背景 / §2 现状 / §3 目标架构 / §4 FR / §5 NFR / §6 IF / §7 TR / §8 约束 / §9 优先级 / §10 RFC / §11 TBD）
- 13 个 FR + 5 个 NFR + 2 个 IF + 2 个 TR
- 4 个里程碑（M1-M4），总计 8 d
- 头部研究材料 4 个产品（Trailbase/Stripe/AppMaster/C# Corner + Azure）
- 末节 §11 TBD 列出 6 项，3 项标记推迟，1 项已包含，1 项需细化，1 项延后

**下一步**：
1. 用户 review Spec + RFC
2. 确认 TBD-5（敏感字段脱敏）处理方案
3. 决定 M1 后是否立即开始实施
4. 实施完成后 E2E 回归（11 个 spec 全部通过）

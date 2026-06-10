# BO Action 体系扩展 — 现状调研报告

> **日期**: 2026-06-05
> **目的**: 系统性识别可下沉为 BO Action 的业务行为
> **方法**: 3 维度调研 — 后端 288 endpoint + 前端 33 composable + 70+ service

---

## 📊 数据规模

| 维度 | 数量 | 业务复杂度 |
|------|:---:|:---:|
| **后端 API 文件** | 44 | — |
| **后端 endpoint** | **288** | 中等（4 个最大蓝图: bo/user/permission/manage） |
| **后端 service** | 70+ | 高（auth/audit/permission/notification/workflow） |
| **前端 composable** | 33 | 高（最大 useMetaList 2499 行） |

---

## 🎯 v3 Spec 双层模型回顾

```
业务行为 = "触发一次完整的领域操作" (走 18 拦截器链)
         适合 BO Action

静态服务 = "纯计算/查询/单步" (无副作用, 同步)
         保留静态 service / API
```

### 判断标准
- ✅ **适合 BO Action**: 写操作 + 涉及拦截器链（审计/权限/通知/级联）+ 多个领域对象
- ❌ **保留静态**: 纯读 / 单步计算 / 不需要审计

---

## 🔍 后端 288 endpoint 分类（按是否"业务行为"）

### 1️⃣ 已是 BO Action 体系（6 个，本次已实施）

| Action | 业务复杂度 | 价值 |
|--------|:---:|------|
| user.authenticate / logout / get_current | 中 | 高 |
| user.change_password | 中 | 中 |
| user.update_profile | 中 | 中 |
| batch_save | 高（多写+审计） | 极高 |

### 2️⃣ P0 强烈推荐下沉为 BO Action

| 候选 Action | 现有 endpoint | 服务 | 业务价值 |
|-------------|----------------|------|:---:|
| `notification.publish` | `notification_api.publish_event` | change_notification_service | 🔴 极高 |
| `audit.retry` | `audit_management_api.retry_failed` | audit_service.retry_failed_record | 🟠 高 |
| `audit.export` | `audit_api.export` | audit_service.export_audit_log | 🟠 高 |
| `user.reset_password` | `user_api.reset_password` | (无 service) | 🟠 高 |
| `task.trigger` | `task_api.trigger` | (无 service) | 🟠 高 |
| `task.enable`/`task.disable` | `task_api.enable`/`disable` | (无 service) | 🟡 中 |
| `subscription.create` | `notification_api.subscriptions POST` | (无 service) | 🟠 高 |
| `enum_type.create`/`update`/`delete` | `enum_api.enum-types POST/PUT/DELETE` | (无 service) | 🟡 中 |
| `user_group.add_member` | `user_group_api.members POST` | user_group_service | 🟠 高 |
| `role.assign_users` | `role_api.role/users POST` | permission_service | 🟠 高 |
| `batch_delete` (通用) | `manage_api.batch-delete` | bo_framework | 🟠 高 |
| `state.transition` | `manage_api.actions POST` | (无 service) | 🔴 极高（核心 BO 行为） |

### 3️⃣ P1 可选下沉（中等价值）

| 候选 Action | 现有 endpoint | 业务价值 |
|-------------|----------------|:---:|
| `value_help.resolve` | `value_help_api.resolve` | 🟡 中 |
| `aggregate.refresh` | `stats_api.aggregates/refresh` | 🟡 中 |
| `olap.drill_down`/`roll_up` | `stats_api.olap/drill-down/roll-up` | 🟡 中 |
| `schema.sync` | `schema_api.sync` | 🟡 中 |
| `database.vacuum`/`analyze`/`reindex` | `database_api.vacuum/analyze/reindex` | 🟢 低（运维） |

### 4️⃣ P2 不下沉（纯查询/元数据）

| 类型 | endpoint | 原因 |
|------|----------|------|
| 元数据查询 | `meta_api.objects`, `schema_api.tables` | 只读 |
| 静态读取 | `user_api.users GET` | 只读 |
| 列表查询 | `manage_api GET list` | 只读 |
| 监控/健康 | `database_api.health` | 运维 |
| WebSocket | `task_api.queues stats` | 推送 |

---

## 🎨 前端 33 composable 业务逻辑分析

### 1️⃣ P0 强烈推荐改造

| Composable | 行数 | fetch | 写入 | 业务函数 | 下沉价值 |
|------------|:---:|:---:|:---:|:---:|:---:|
| **useDetail.js** | 650 | 0 | 0 | 22 | 🔴 极高（CRUD+关联+审计） |
| **useBOApi.js** | 666 | 0 | 0 | 33 | 🔴 极高（CRUD+关联+表单保存） |
| **useMetaList.js** | 2499 | 0 | 0 | 36 | 🔴 极高（**已部分下沉**） |
| **useImportExportApi.js** | 165 | 4 | 3 | 3 | 🟠 高（**已存在 endpoint**） |

### 2️⃣ P1 可选改造

| Composable | 行数 | 业务价值 | 改造点 |
|------------|:---:|:---:|------|
| useObjectIdentity.js | 276 | 🟠 高 | 4 个 endpoint → 1 个 Action |
| useMenuPermissions.js | 216 | 🟡 中 | 菜单权限查询 |
| useAssociation.js | 325 | 🟡 中 | 关联操作 |

### 3️⃣ P2 不下沉（纯前端逻辑）

| Composable | 原因 |
|------------|------|
| useDebounce, useVirtualScroll | 纯前端工具 |
| useMessage | UI 提示 |
| useRefreshCoordinator | 协调器 |
| useNavigation, useLayoutControl | UI 状态 |

---

## ⚙️ service 层 70+ 服务分析

### 1️⃣ 适合包装为 Action（业务行为）

| Service | 关键方法 | Action 候选 |
|---------|----------|------------|
| **change_notification_service** | `publish_event` | `notification.publish` |
| **audit_service** | `retry_failed_record` | `audit.retry` |
| **audit_service** | `export_audit_log` | `audit.export` |
| **condition_evaluator** | `evaluate` | `condition.evaluate` |
| **hierarchy_service** | `build_tree` | `hierarchy.build` |
| **owner_transfer_service** | (transfers) | `owner.transfer` |
| **permission_sync_service** | `sync_all` | `permission.sync` |
| **permission_audit_service** | (audit) | `permission.audit` |
| **cascade_service** | `cascade_*` | `cascade.delete/update` |
| **bulk_import / bulk_export** | `import`/`export` | `import.execute`/`export.execute` |

### 2️⃣ 保留静态 service（纯计算/查询）

| Service | 原因 |
|---------|------|
| auth_provider, token_service | 已是基础 service |
| permission_service, data_permission_service | 查询密集 |
| query_service, list_service | 静态查询 |
| cache_monitor, structured_logger | 监控 |
| display_name_service, date_format_service | 纯计算 |

---

## 🔄 与 v2 BO API 关系

**关键发现**：项目已有 **V2 BO API**（[bo_api.py:319](file:///d:/filework/excel-to-diagram/meta/api/bo_api.py#L319) `/api/v2/bo/{object_type}/{id}/actions/{action_id}`）—— 走 bo_framework 的 18 拦截器链。

**V2 vs V3 关系**：
- **V2 BO API** = 路径化 endpoint（`/api/v2/bo/{object_type}/{id}/actions/{action_id}`）
- **V3 BO Action** = 统一端点（`/api/v2/action/{action_id}`）

**两者共存**：
- V2 适合：单 BO 行为（针对某个具体对象）
- V3 适合：跨 BO 业务（用户认证、全局批量操作、跨域工作流）

---

## 📋 推荐实施清单（按优先级）

### P0 必做（1 周内，5-8 个 Action）

| # | Action | 类型 | 端点 | 工作量 |
|---|--------|------|------|:---:|
| 1 | `notification.publish` | 业务 | notification_api | 1h |
| 2 | `audit.retry` | 运维 | audit_management_api | 30min |
| 3 | `audit.export` | 运维 | audit_api.export | 30min |
| 4 | `user.reset_password` | 业务 | user_api | 30min |
| 5 | `task.trigger` | 运维 | task_api | 30min |
| 6 | `batch_delete` (通用) | 业务 | manage_api.batch_delete | 1h |
| 7 | `state.transition` | 业务 | manage_api.actions | 1.5h |

**预计总工作量**: 5-6 小时

### P1 推荐（1-2 周）

| # | Action | 工作量 |
|---|--------|:---:|
| 8 | `user_group.add_member` | 1h |
| 9 | `role.assign_users` | 1h |
| 10 | `value_help.resolve` | 1h |
| 11 | `aggregate.refresh` | 30min |
| 12 | `subscription.create` | 30min |
| 13 | `enum_type.crud` (3 个) | 1.5h |

### P2 长期（按需）

- `olap.drill_down`/`roll_up`
- `schema.sync`
- `database.vacuum`/`analyze`/`reindex`
- `condition.evaluate`
- `hierarchy.build`
- `owner.transfer`
- `permission.sync`

---

## 🛡️ 实施前置条件

- [ ] 当前 `feature/bo-action-v3` 分支（已存在）继续
- [ ] DB 备份（实施前 1 次）
- [ ] 服务重启机制验证（已验证）
- [ ] E2E 测试脚本模板（已验证）
- [ ] V2 BO API 端点保留（不删除，向后兼容）

---

## 📊 风险评估

| 风险 | 等级 | 缓解 |
|------|:---:|------|
| 旧端点突然失效 | 🟡 中 | 保留老 endpoint 至少 1 个版本 |
| 老前端调用未切 | 🟢 低 | 暂不切, 走 BO Action 是 "also 提供" |
| Action 注册遗漏 | 🟢 低 | server.py 启动时打印注册数 |
| 鉴权不严 | 🟡 中 | 复用 auth_middleware 模式 |
| 性能回归 | 🟢 低 | 单 HTTP 替代 N+1 |

---

## 📂 决策矩阵

| Action | 现有端点可删除? | 推荐做法 |
|--------|:---:|------|
| notification.publish | 🟡 部分 | 保留 POST, 内部走 Action |
| audit.retry/export | 🟢 可删 | 一次性迁移 |
| user.reset_password | 🟡 部分 | 保留 admin 接口, 走 Action |
| batch_delete | 🟡 部分 | 保留, 内部用 |
| state.transition | ❌ 不删 | V2 已有, 走 V3 不实用 |

**最佳实践**: 保留所有现有 endpoint, **BO Action 作为新的可选调用方式**。前端可逐步切。

---

## 变更记录

| 版本 | 日期 | 变更 |
|:---:|------|------|
| 1.0.0 | 2026-06-05 | 创建调研报告 + 优先级 P0/P1/P2 排序 |

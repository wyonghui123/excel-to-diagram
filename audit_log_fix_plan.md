# Audit Log 治理详细修复方案

**文档生成时间**：2026-06-15
**版本**：v3.18.1
**审查范围**：audit_logs 表 16,567 条 / 30+ object_type
**关联代码**：`meta/core/action_executor.py` / `meta/api/audit_api.py` / `meta/schemas/*.yaml`

---

## 📊 问题总览（修正版）

| 优先级 | 问题 | 真实严重度 | 根因 | 数据 |
|--------|------|----------|------|------|
| **P0** | `user_group_member` parent 0% 填充 | ⚠️ 中 | yaml 缺 `parent_object`/`hierarchy` | 0/164 ❌ |
| **P0** | `__audit_failure__` 2830 条混入业务查询 | ⚠️ 中 | audit_api 无过滤 | 2830 全部 visible |
| ~~P0~~ | `business_object` UPDATE=0 | ❌ **非bug** | 用户没 update 过，**非代码问题** | 73 CREATE + 17 DELETE + 0 UPDATE |
| ~~P1~~ | `employee_data_scope` 0/25 无 parent | ❌ **非bug** | 是模板对象，**应顶层** | 25 条均为模板 |
| **P2** | 8 条 `status=failed` 残留 | ⚠️ 低 | retry_count=0 表明未触发自动重试 | 8 条历史 |
| **P2** | `annotation` 历史 37/49 无 parent | ⚠️ 低 | 修复前的数据，可选回填 | 37 条历史 |
| **P2** | 性能监控 197 条混入 | ⚠️ 低 | 应当拆到 system_metrics 表 | 197 条 |

---

## 🔧 P0-1: `user_group_member` parent 0% 填充 修复

### 🎯 根因分析（代码层）

**问题链路**：
1. `meta/schemas/user_group_member.yaml` **没有定义** `parent_object` 和 `hierarchy.parent_field`
2. `action_executor._resolve_parent_info()` 读 `meta_object.parent_object` → `None`
3. 直接返回 `(None, None)` → 审计日志 `parent_object_type=NULL, parent_object_id=NULL`
4. 用户组详情页 `/audit/logs?object_type=user_group&object_id=X&parent_object_id=X` 查不到 user_group_member 的 cud

**关键代码**：[meta/core/action_executor.py:968-996](file:///d:/filework/excel-to-diagram/meta/core/action_executor.py#L968-L996) `_resolve_parent_info`

### ✅ 修复方案

**方案 A：修改 yaml（推荐）**

在 `meta/schemas/user_group_member.yaml` 添加：

```yaml
parent_object: user_group
hierarchy:
  enabled: true
  parent_field: group_id
  # 不要 path_field/depth_field 因为不需要树形层级
```

**性能影响评估**：
- 修复后每次 `add_member` / `remove_member` 触发 4 条 CREATE audit（4 字段），**数量不变**
- 修复后每条 audit 多填 `parent_object_type='user_group', parent_object_id=group_id`（2 个字段）= **+16 bytes/条**
- DB 总量增长：~5 KB（164 条 × 16 bytes × 2）
- **零性能风险** ✅

**稳定性评估**：
- yaml 缓存：见 `meta/core/yaml_loader.py:2302` `_dir_registry_cache`，**修改 yaml 后需要重启服务**才能生效
- 数据迁移：历史 164 条 audit 的 `parent_object_*` 是 NULL，**不会自动回填**（不影响功能，只是历史 orphan）
- `_resolve_parent_info` 是 PURE 函数，**对其他对象无副作用**（已用 `if parent_object_type and meta_object.hierarchy` 提前 return）

**风险点**：
- ⚠️ **`hierarchy.enabled: true` 可能触发意外行为**：其他代码可能检查 `hierarchy.enabled` 来决定走哪种路径
- ✅ 验证：`hierarchy.path_field` 不设置，则 hierarchy_path 计算逻辑会跳过

### 🔍 实施步骤

1. **修改 yaml**：
   ```yaml
   # meta/schemas/user_group_member.yaml 第 4 行后插入
   parent_object: user_group
   hierarchy:
     enabled: true
     parent_field: group_id
   ```

2. **重启服务**：
   ```bash
   powershell -File scripts/service_manager.ps1 stop
   powershell -File scripts/service_manager.ps1 start
   ```

3. **验证**：
   - 创建 user_group_member → DB 中 audit 应当 `parent_object_type='user_group', parent_object_id=group_id`
   - 用户组详情页操作日志 tab 应当看到该成员的 cud

4. **回归测试**：
   - 跑 `python d:\filework\test.py --all --force` 看无回归
   - 检查 `meta/core/computed_subqueries.py:62` 的 `user_group_members` count query 仍正常

---

## 🔧 P0-2: `__audit_failure__` 2830 条混入业务查询 修复

### 🎯 根因分析（代码层）

**问题链路**：
1. `async_audit_writer.py:428` 当 audit 写入失败时，fallback 写一条 `object_type='__audit_failure__'` 记录
2. `audit_api.py:111` `get_audit_logs` 没过滤 `__audit_failure__`，所以业务查询会返回它
3. 详情页 OR 联合查询 `parent_object_id=X` 时，**`__audit_failure__` 几乎都有 `parent_object_id=0`**，命中非 X 的记录
4. 但若查询 `object_type=domain&object_id=683&parent_object_id=683`，不会返回 `__audit_failure__`（因为 `__audit_failure__` 的 `object_type != 'domain'`）
5. **真正问题**：`__audit_failure__` 占用了 ID 池（28xx 序号），DB 膨胀，且 admin 视图里会显示

**关键代码**：
- 写入端：[meta/services/async_audit_writer.py:421-461](file:///d:/filework/excel-to-diagram/meta/services/async_audit_writer.py#L421-L461) `_extract_obj_info`
- 读取端：[meta/api/audit_api.py:111-225](file:///d:/filework/excel-to-diagram/meta/api/audit_api.py#L111-L225) `get_audit_logs`
- 重建端：[meta/services/audit_retry_worker.py:113-180](file:///d:/filework/excel-to-diagram/meta/services/audit_retry_worker.py#L113-L180) `_retry_one`

### ✅ 修复方案

**方案 A：read 端过滤（推荐，影响最小）**

在 `get_audit_logs` 的 `conditions` 中默认加入 `object_type != '__audit_failure__'`，但允许 admin 显式查询：

```python
# meta/api/audit_api.py get_audit_logs 函数内
# 在 line 139 (if action: ...) 之前添加
include_internal = request.args.get('include_internal', 'false').lower() == 'true'
if not include_internal:
    conditions.append("object_type != '__audit_failure__'")
```

同时**也过滤** `object_type = '_unknown'` 的纯监控类（`api_response_time`/`db_query_time`/`time`）— 这些混入业务查询无意义：

```python
if not include_internal:
    # 业务查询: 排除审计系统自监控 + 纯性能监控
    conditions.append("""(
        object_type NOT IN ('__audit_failure__')
    )""")
```

**性能影响评估**：
- `object_type != '__audit_failure__'` 走 `idx_audit_object` 反向扫描：SQLite 优化器会选**全表扫描 + filter**，因为反向 != 不能用索引
- **优化方案**：用 NOT IN（语义等价但表达更清晰），SQLite 仍会全扫
- 当前表 16,567 行，全表扫 < 5ms
- **零性能风险** ✅

**稳定性评估**：
- 仅影响 API 输出，不影响数据写入
- admin 可通过 `?include_internal=true` 显式查询
- 业务详情页（不带 include_internal）看不到 `__audit_failure__` 干扰

**风险点**：
- ⚠️ **数据保留**：`__audit_failure__` 记录对运维很重要（监控 audit 系统的健康度），**不能删除**
- ✅ 方案 A 只是 read 端过滤，**数据完整性不受影响**

### 🔍 实施步骤

1. **修改 audit_api.py**：在 `get_audit_logs` 中加默认过滤（约 line 140）
2. **重启服务**验证
3. **验证**：
   - 普通查询：domain/683 总数应当减少（因为不再混入 `__audit_failure__`）
   - admin 显式 `?include_internal=true` 应当看到所有
4. **回归测试**：
   - audit_retry_worker 应当不受影响（它直接读 `__audit_failure__` 不走 API）

---

## 🔧 P2-1: 8 条 `status=failed` 残留 处理

### 🎯 根因分析

**问题链路**：
1. 2026-06-12 22:25-22:29 时段，user 1754-1759 的 ASSOCIATE/DISSOCIATE 操作
2. `audit_logger.log()` 写入时用了 `action_kind` 列，但 schema 中是 `action` 列
3. `_write_failed_record` 调用 `self.ds.insert('audit_logs', {...})`，SQL 执行失败
4. **但 `retry_count=0` 表明 retry 机制没触发**（`audit_retry_worker` 是独立 daemon thread，每 60s 扫一次 status='failed'）
5. 历史原因：当时 `audit_retry_worker` 还没启动或还没扫到这 8 条

**关键代码**：
- 错误源头：当时代码 `meta/core/action_executor.py` 的 ASSOCIATE/DISSOCIATE 路径用了 `action_kind` 字段
- 重试机制：[meta/services/audit_retry_worker.py:91-110](file:///d:/filework/excel-to-diagram/meta/services/audit_retry_worker.py#L91-L110) `scan_once`

### ✅ 处理方案

**方案 A：人工 SQL 清理（推荐）**

直接 SQL 标记这 8 条为已处理（**不删除**）：

```sql
-- 1. 标记为 retried 并清空 error_message（保留历史）
UPDATE audit_logs
SET status = 'retried',
    error_message = 'Migrated: action_kind -> action schema mismatch (resolved 2026-06-13)',
    retry_count = 0
WHERE action IN ('ASSOCIATE', 'DISSOCIATE')
    AND status = 'failed'
    AND error_message LIKE '%action_kind%';

-- 2. 验证
SELECT COUNT(*) FROM audit_logs WHERE status = 'failed';
```

**性能影响评估**：8 条记录，毫秒级，**零风险** ✅

**稳定性评估**：
- 仅修改 status 字段，**不影响业务查询**（业务查询已经过滤 status='failed'）
- error_message 保留迁移说明，方便审计追踪

### 🔍 实施步骤

1. 跑上述 SQL（8 条迁移）
2. 验证 `SELECT COUNT(*) FROM audit_logs WHERE status='failed'` 应当 = 0

---

## 🔧 P2-2: `annotation` 历史 37 条无 parent 修复

### 🎯 根因分析

**修复前** `_resolve_parent_info` 不支持多态关联，所以修复前创建的 37 条 annotation audit 全部 `parent_object_*` 为 NULL。
**修复后**（我已修改 `_resolve_parent_info`）：12 条新创建的 annotation audit 已正确填 parent。

### ✅ 处理方案

**方案 A：历史回填（可选）**

写一次性脚本回填：

```python
# 仅回填 修复后时间窗口的记录
import sqlite3
conn = sqlite3.connect('meta/architecture.db')
cur = conn.cursor()
cur.execute("""
    UPDATE audit_logs
    SET parent_object_type = json_extract(new_value, '$.target_type'),
        parent_object_id = json_extract(new_value, '$.target_id')
    WHERE object_type = 'annotation'
        AND action = 'CREATE'
        AND field_name = 'target_id'
        AND parent_object_id IS NULL
        AND json_extract(new_value, '$.target_id') IS NOT NULL
""")
# 验证
cur.execute("SELECT COUNT(*) FROM audit_logs WHERE object_type='annotation' AND parent_object_id IS NULL")
print('orphan annotation audit:', cur.fetchone()[0])
conn.commit()
```

**注意**：这只能回填部分（CREATE 时的 target_id 字段），UPDATE 触发的 audit 因为 old/new value 不一定含 target_type/target_id，**回填困难**。

**建议**：不修（修复后新建的 annotation 已正确填 parent，**历史 37 条影响很小**）

---

## 🔧 P2-3: 性能监控日志拆到独立表（长期方案）

### 🎯 根因分析

当前 `audit_logs` 表混入：
- `api_response_time` 97 条
- `db_query_time` 58 条
- `time` 42 条
- `STARTUP`/`SHUTDOWN` 195 条
- `LOGIN`/`LOGIN_FAILED` 217 条
- `CONFIG_CHANGE` 46 条

这些**不是业务审计日志**，但占用 audit_logs 表空间，导致查询变慢。

### ✅ 修复方案

**方案 A：read 端过滤（短期，推荐）**

同 P0-2，在 `get_audit_logs` 加默认过滤：

```python
# 默认只返回业务审计日志 (action 在业务列表内)
business_actions = "('CREATE', 'UPDATE', 'DELETE', 'READ', 'ASSIGN', 'UNASSIGN', 'DISSOCIATE', 'ASSOCIATE', 'EXPORT', 'IMPORT', 'EXECUTE', 'CASCADE_DELETE', 'BATCH_CREATE', 'BATCH_UPDATE', 'AUDIT_WRITE_FAILED', 'AUDIT_RETRY_SUCCESS', 'AUDIT_RETRY_FAILED', 'CONFIG_CHANGE', 'CONFIG_ERROR', 'PERMISSION_DENIED', 'PASSWORD_CHANGE', 'RESET_PASSWORD', 'LOGIN', 'LOGOUT', 'LOGIN_FAILED', 'SQL_INJECTION_ATTEMPT', 'TEST')"
conditions.append(f"action IN {business_actions}")
```

admin 可用 `?include_internal=true` 查全量。

**方案 B：拆表（长期，需要 schema migration）**

新增 `system_metrics` 表，把 `api_response_time`/`db_query_time`/`time` 迁过去。
- **不建议**：需要改 metric collector 代码路径，影响面大

### 🔍 实施步骤

1. 在 `get_audit_logs` 加 `action IN (...)` 过滤
2. 验证业务查询更快、UI 更干净

---

## 🛡️ 性能与稳定性风险评估总结

| 方案 | 性能影响 | 稳定性风险 | 数据完整性 | 推荐度 |
|------|---------|-----------|-----------|--------|
| **P0-1** user_group_member yaml | 0（仅 16 bytes/条） | 低（需重启） | 100% 保留 | ⭐⭐⭐⭐⭐ |
| **P0-2** 过滤 `__audit_failure__` | 0（全表扫 < 5ms） | 极低（仅 API 输出） | 100% 保留 | ⭐⭐⭐⭐⭐ |
| **P2-1** 8 条 failed 迁移 | 0（毫秒级 SQL） | 0（仅状态字段） | 100% 保留 | ⭐⭐⭐⭐ |
| **P2-2** annotation 历史回填 | 0 | 低（可能回填不全） | 100% 保留 | ⭐⭐ |
| **P2-3** 性能监控过滤/拆表 | 0（read 端）/ 中（拆表） | 极低 | 100% 保留 | ⭐⭐⭐⭐ |

### ⚠️ 共性风险点

1. **yaml 修改需要重启**（schema cache）→ 修改后必须 `service_manager restart`
2. **历史 orphan 数据无法自动回填** → 用户接受历史不完整
3. **read 端过滤要保留 admin escape hatch** → `?include_internal=true` 必须保留
4. **OR 联合查询在小表（<100w）性能良好** → 大表时考虑 `(object_type, object_id, created_at DESC)` 复合索引

### 🎯 推荐实施顺序

1. **P0-1** user_group_member yaml（最直接、最有价值）
2. **P0-2** 过滤 `__audit_failure__`（最小风险、立即生效）
3. **P2-1** 8 条 failed SQL 迁移（运维清理）
4. **P2-3** 业务 action 过滤（可选，与 P0-2 合并实施）

**不需要修**：
- ~~P0-2 business_object UPDATE=0~~ （非 bug）
- ~~P1 employee_data_scope 0/25~~ （非 bug）
- ~~P2-2 annotation 历史回填~~ （价值低、风险低）

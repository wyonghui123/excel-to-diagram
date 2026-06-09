# M2 后端查询优化 — 详细实现方案

> **日期**: 2026-06-08
> **版本**: v1.0
> **范围**: FR-006 (N+1 修复) / FR-007 (虚拟字段排序) / FR-008 (relationships 索引) / FR-009 (audit_logs 索引)

---

## 一、FR-006: N+1 查询修复

### 1.1 问题全貌

经代码分析, 共发现 **4 处 N+1 查询**, 典型场景下产生 **66-80 次额外 SQL**:

| # | 文件 | 函数 | 行号 | 循环内查询 | 典型额外查询数 |
|---|------|------|------|-----------|--------------|
| 1 | enum_api.py | `list_enum_types()` | 252-254 | `_get_enum_value_count()` | 20 |
| 2 | role_api.py | `list_roles()` | 124-126 | `get_role_permissions()` + `_get_latest_change_time()` | 20 |
| 3 | user_api.py | `list_users()` | 162-163 | `get_user_roles()` | 20 |
| 4 | meta_api.py | `batch_get_enums()` | 364-394 | 2x `ds.execute()` per type | 6-20 |

### 1.2 已有正确模式 (参考)

`enum_api.py:96-144` 的 `_enrich_updated_at()` 已实现批量查询:

```python
cursor = _data_source.execute(
    f"SELECT object_id, MAX(created_at) as max_update_at "
    f"FROM audit_logs "
    f"WHERE object_type = ? AND object_id IN ({placeholders}) "
    f"AND action = 'UPDATE' "
    f"GROUP BY object_id",
    [object_type] + record_ids
)
```

**所有 N+1 修复均参照此模式**: `IN (?)` + `GROUP BY` 批量查询。

### 1.3 修复方案

#### N+1 #1: enum_api.py `list_enum_types()`

**当前代码** (第 252-254 行):
```python
for row in result:
    row['value_count'] = _get_enum_value_count(ds, row['id'])
    row['dimension_count'] = _get_dimension_count(row.get('dimension_schema'))
```

**修复后**:
```python
# 批量获取 value_count (替代逐行 _get_enum_value_count)
enum_ids = [row['id'] for row in result]
if enum_ids:
    placeholders = ','.join(['?'] * len(enum_ids))
    cursor = ds.execute(
        f"SELECT enum_type_id, COUNT(*) as cnt FROM enum_values "
        f"WHERE enum_type_id IN ({placeholders}) GROUP BY enum_type_id",
        enum_ids
    )
    count_map = dict(cursor.fetchall())
else:
    count_map = {}

for row in result:
    row['value_count'] = count_map.get(row['id'], 0)
    row['dimension_count'] = _get_dimension_count(row.get('dimension_schema'))
```

**注意**: `_get_dimension_count()` 是纯 Python JSON 解析, 无 DB 查询, 不需要修改。

**查询次数**: 20+1 → 2 (1 次列表 + 1 次批量 count)

#### N+1 #2: role_api.py `list_roles()`

**当前代码** (第 123-127 行):
```python
roles = _get_perm_service().get_all_roles()
for role in roles:
    role['permissions'] = _get_perm_service().get_role_permissions(role['id'])
    role['updated_at'] = _get_latest_change_time('role', role['id'])
```

**修复后**:
```python
roles = _get_perm_service().get_all_roles()
if roles:
    role_ids = [r['id'] for r in roles]

    # 批量获取角色权限
    placeholders = ','.join(['?'] * len(role_ids))
    cursor = ds.execute(
        f"SELECT rp.role_id, p.id, p.code, p.name, p.description, p.is_system "
        f"FROM permissions p JOIN role_permissions rp ON p.id = rp.permission_id "
        f"WHERE rp.role_id IN ({placeholders})",
        role_ids
    )
    perm_map = {}
    for row in cursor.fetchall():
        rid = row[0]
        perm_map.setdefault(rid, []).append({
            'id': row[1], 'code': row[2], 'name': row[3],
            'description': row[4], 'is_system': row[5]
        })

    # 批量获取 updated_at (参照 _enrich_updated_at 模式)
    cursor = ds.execute(
        f"SELECT object_id, MAX(created_at) as max_update_at "
        f"FROM audit_logs WHERE object_type = 'role' "
        f"AND object_id IN ({placeholders}) AND action = 'UPDATE' "
        f"GROUP BY object_id",
        role_ids
    )
    updated_map = dict(cursor.fetchall())

    for role in roles:
        role['permissions'] = perm_map.get(role['id'], [])
        role['updated_at'] = updated_map.get(role['id'])
```

**查询次数**: 20+1 → 3 (1 次列表 + 1 次权限 + 1 次 updated_at)

#### N+1 #3: user_api.py `list_users()`

**当前代码** (第 162-163 行):
```python
for u in users:
    u['roles'] = _get_perm_service().get_user_roles(u['id'])
```

**修复后**:
```python
if users:
    user_ids = [u['id'] for u in users]
    placeholders = ','.join(['?'] * len(user_ids))

    # 批量获取用户角色 (3 表 JOIN)
    cursor = ds.execute(
        f"SELECT ugm.user_id, r.id, r.code, r.name, r.description, r.is_system "
        f"FROM roles r "
        f"JOIN group_roles gr ON r.id = gr.role_id "
        f"JOIN user_group_members ugm ON gr.group_id = ugm.group_id "
        f"WHERE ugm.user_id IN ({placeholders})",
        user_ids
    )
    role_map = {}
    for row in cursor.fetchall():
        uid = row[0]
        role_map.setdefault(uid, []).append({
            'id': row[1], 'code': row[2], 'name': row[3],
            'description': row[4], 'is_system': row[5]
        })

    for u in users:
        u['roles'] = role_map.get(u['id'], [])
```

**查询次数**: 20+1 → 2 (1 次列表 + 1 次角色)

#### N+1 #4: meta_api.py `batch_get_enums()`

**当前代码** (第 364-394 行): 每个枚举类型执行 2 次查询 (存在性检查 + 值查询)

**修复后**:
```python
# 批量存在性检查
placeholders = ','.join(['?'] * len(enum_types))
cursor = ds.execute(
    f"SELECT id FROM enum_types WHERE id IN ({placeholders})",
    enum_types
)
existing_ids = set(row[0] for row in cursor.fetchall())

# 批量获取所有枚举值
cursor = ds.execute(
    f"SELECT enum_type_id, code, name, name_en, sort_order, is_active, parent_code "
    f"FROM enum_values WHERE enum_type_id IN ({placeholders}) AND is_active = 1 "
    f"ORDER BY enum_type_id, sort_order, code",
    enum_types
)
values_by_type = {}
for row in cursor.fetchall():
    tid = row[0]
    values_by_type.setdefault(tid, []).append({
        'code': row[1], 'name': row[2], 'name_en': row[3],
        'sort_order': row[4], 'is_active': row[5], 'parent_code': row[6]
    })

# 组装结果
for enum_type in enum_types:
    if enum_type not in existing_ids:
        # ... error handling
        continue
    result[enum_type] = values_by_type.get(enum_type, [])
```

**查询次数**: 6-20 → 2 (1 次存在性 + 1 次值查询)

### 1.4 修复汇总

| 端点 | 修复前查询数 | 修复后查询数 | 减少 |
|------|------------|------------|------|
| list_enum_types | 22 | 2 | 91% |
| list_roles | 21 | 3 | 86% |
| list_users | 21 | 2 | 90% |
| batch_get_enums | 6-20 | 2 | 67-90% |
| **总计** | **70-84** | **9** | **~88%** |

---

## 二、FR-007: 虚拟字段排序修复

### 2.1 问题分析

**核心 Bug**: 内存排序路径先 SQL 分页再 Python 排序, 导致虚拟字段排序**只在当前页内有效, 跨页排序结果不正确**。

**调用链**:
```
QueryService.search() (L208)
  ├── DB 层排序 (已优化, 全局正确)
  │   ├── virtual_join_info → JOIN 排序 (virtual_sort.py)
  │   └── count_relations → 子查询排序 (_execute_computed_field_query)
  └── 内存排序路径 (有 Bug)
      ├── builder.page(page, page_size) (L456) ← 先分页!
      ├── builder.execute() (L457) ← 取当前页
      ├── _enrich_audit_virtual_fields() (L466)
      ├── _sort_by_virtual_fields() (L480) ← 只对当前页排序
      └── _sort_by_computed_field() (L483) ← 只对当前页排序
```

**影响范围**: 仅影响 `memory_sort_field` 分支 (即虚拟字段没有 join_path 且不是 count_relations 的场景), 主要是 audit 派生字段 (如 `updated_at`)。

### 2.2 修复方案: 两阶段查询

**仅针对内存排序路径**, 不影响已优化的 DB 排序路径:

```
Phase 1: SELECT id FROM table WHERE <filters>
          → 批量获取排序字段值 (如 audit updated_at)
          → Python 排序 → 取当前页 IDs

Phase 2: SELECT * FROM table WHERE id IN (<page_ids>)
          → enrich + compute → 返回
```

**具体实现** (修改 `query_service.py` 的 `search()` 方法):

```python
# 当前代码 (L456-483):
builder.page(request.page, request.page_size)
data = builder.execute()
# ... enrich ...
data = self._sort_by_virtual_fields(meta_obj, data, order_clause)
data = self._sort_by_computed_field(...)

# 修复后:
if memory_sort_field:
    # Phase 1: 只查 ID, 不分页
    builder_copy = copy_builder_without_pagination(builder)
    all_ids = builder_copy.select('id').execute()  # 只查 ID

    # Phase 1b: 批量获取排序字段值
    if memory_sort_field == 'updated_at':
        sort_values = self._batch_get_audit_timestamps(
            meta_obj.object_type, [r['id'] for r in all_ids]
        )
        # 排序 + 分页
        sorted_ids = sorted(all_ids, key=lambda r: sort_values.get(r['id'], ''), reverse=is_desc)
        page_ids = [r['id'] for r in sorted_ids[offset:offset+limit]]

    # Phase 2: 用 page IDs 查完整数据
    data = ds.find(meta_obj.table_name, filters={'id': {'in': page_ids}})
    # ... enrich ...
else:
    # 非虚拟字段排序, 走原路径
    builder.page(request.page, request.page_size)
    data = builder.execute()
```

### 2.3 风险评估

| 风险 | 严重程度 | 缓解措施 |
|------|---------|---------|
| Phase 1 全量查 ID, 大表性能 | 中 | ID 列表比全量数据轻量得多; 加 WHERE 过滤后通常 < 1 万条 |
| computed_by 字段排序值依赖完整记录 | 高 | 对 hierarchy_scope/formula 类型, 退化为全量加载+排序 (与当前行为一致, 但分页正确) |
| 两阶段间数据变化 | 低 | 列表查询场景影响极小, 可忽略 |

### 2.4 实施策略

**分步实施**:
1. 先修复 `_sort_by_virtual_fields` 的分页 Bug (最小改动)
2. 再优化为两阶段查询 (性能提升)

**最小修复** (先做): 将 SQL 分页移到 Python 排序之后:

```python
# 修复前: 先分页再排序 (Bug)
builder.page(request.page, request.page_size)
data = builder.execute()
data = self._sort_by_virtual_fields(meta_obj, data, order_clause)

# 修复后: 先查全部再排序再分页 (正确但慢)
# 不分页, 查全部
data = builder.execute()
data = self._sort_by_virtual_fields(meta_obj, data, order_clause)
# Python 分页
start = (request.page - 1) * request.page_size
data = data[start:start + request.page_size]
```

**两阶段优化** (后续): Phase 1 只查 ID + 排序字段, Phase 2 查完整数据。

---

## 三、FR-008: relationships 表索引

### 3.1 现状

| 索引 | 列 | 状态 |
|------|-----|------|
| `idx_relationships_source_target` | (source_bo_id, target_bo_id) | 已存在 (v2 迁移) |
| `idx_relationships_source_bo_id` | (source_bo_id) | **缺失** |
| `idx_relationships_target_bo_id` | (target_bo_id) | **缺失** (最高优先级) |

**说明**: 复合索引 `(source_bo_id, target_bo_id)` 对 `WHERE source_bo_id = ?` 有效 (最左前缀), 但对 `WHERE target_bo_id = ?` **完全无效**。而 OR 查询 `WHERE source_bo_id = ? OR target_bo_id = ?` 中 SQLite 无法利用复合索引同时覆盖两个分支。

### 3.2 受益查询 (10+ 处)

| 文件 | 行号 | 查询模式 | 受益索引 |
|------|------|---------|---------|
| special_routes_api.py | 348 | `WHERE r.source_bo_id = ?` | source_bo_id |
| special_routes_api.py | 354 | `WHERE r.target_bo_id = ?` | **target_bo_id** |
| cascade_service.py | 386 | `WHERE source_bo_id = ? OR target_bo_id = ?` | 两个都需要 |
| computation_service.py | 294 | `WHERE source_bo_id = ? OR target_bo_id = ?` | 两个都需要 |
| association/fallback.py | 160 | `WHERE source_bo_id = ? OR target_bo_id = ?` | 两个都需要 |
| meta_api.py | 656 | `LEFT JOIN ... ON (r.source_bo_id = bo.id OR r.target_bo_id = bo.id)` | **target_bo_id** |
| consistency_guard.py | 187-188 | 级联更新 | 两个都需要 |
| query_service.py | 652-653 | computed count 子查询 | 两个都需要 |

### 3.3 新增索引

```sql
-- 最高优先级: target_bo_id 单列索引
CREATE INDEX IF NOT EXISTS idx_relationships_target_bo_id ON relationships(target_bo_id);

-- 高优先级: source_bo_id 单列索引 (复合索引可部分覆盖, 但单列索引对 OR 查询更优)
CREATE INDEX IF NOT EXISTS idx_relationships_source_bo_id ON relationships(source_bo_id);
```

---

## 四、FR-009: audit_logs 表索引

### 4.1 现状

已有 10 个索引, 但缺少 `(object_type, action)` 组合索引。

### 4.2 新增索引

```sql
-- 审计日志列表页核心筛选 + 排序覆盖
CREATE INDEX IF NOT EXISTS idx_audit_logs_type_action_created
ON audit_logs(object_type, action, created_at);
```

**说明**: 此索引覆盖 `(object_type, action)` 查询, 且包含 `created_at` 排序列, 实现覆盖索引扫描, 避免回表排序。替代单独创建 `(object_type, action)` 索引。

### 4.3 受益查询

| 文件 | 行号 | 查询模式 |
|------|------|---------|
| audit_api.py | 114-119 | `WHERE action = ? AND object_type = ?` (列表页筛选) |
| action_executor.py | 1016-1017 | `WHERE object_type = ? AND action IN ('CREATE', 'UPDATE')` |
| association/fallback.py | 187-191 | `WHERE object_type = ? AND action = ?` |

---

## 五、迁移脚本

### 5.1 新建 `add_performance_indexes_v3.py`

遵循 v2 的模式 (`create_indexes(conn)` + `verify_indexes(conn)`):

```python
"""性能索引 v3: relationships + audit_logs
- idx_relationships_target_bo_id: 关联关系 target 端查询 (10+ 处受益)
- idx_relationships_source_bo_id: 关联关系 source 端 OR 查询优化
- idx_audit_logs_type_action_created: 审计日志类型+操作筛选+排序覆盖
"""

INDEXES = [
    {
        'name': 'idx_relationships_target_bo_id',
        'table': 'relationships',
        'columns': ['target_bo_id'],
        'sql': 'CREATE INDEX IF NOT EXISTS idx_relationships_target_bo_id ON relationships(target_bo_id)',
        'priority': 'P0',
        'reason': 'target_bo_id 查询无索引覆盖, 影响 10+ 处查询'
    },
    {
        'name': 'idx_relationships_source_bo_id',
        'table': 'relationships',
        'columns': ['source_bo_id'],
        'sql': 'CREATE INDEX IF NOT EXISTS idx_relationships_source_bo_id ON relationships(source_bo_id)',
        'priority': 'P1',
        'reason': 'source_bo_id OR 查询优化, 复合索引最左前缀可部分覆盖'
    },
    {
        'name': 'idx_audit_logs_type_action_created',
        'table': 'audit_logs',
        'columns': ['object_type', 'action', 'created_at'],
        'sql': 'CREATE INDEX IF NOT EXISTS idx_audit_logs_type_action_created ON audit_logs(object_type, action, created_at)',
        'priority': 'P1',
        'reason': '审计日志列表页 object_type+action 筛选 + created_at 排序覆盖'
    },
]


def create_indexes(conn):
    """创建索引 (幂等)"""
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
    existing = {row[0] for row in cursor.fetchall()}

    for idx in INDEXES:
        if idx['name'] not in existing:
            conn.execute(idx['sql'])
            print(f"  [v3] Created index: {idx['name']}")
        else:
            print(f"  [v3] Index already exists: {idx['name']}")


def verify_indexes(conn):
    """验证索引是否存在"""
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index'")
    existing = {row[0] for row in cursor.fetchall()}

    results = []
    for idx in INDEXES:
        ok = idx['name'] in existing
        results.append((idx['name'], ok))
        status = 'OK' if ok else 'MISSING'
        print(f"  [v3] {idx['name']}: {status}")

    return all(ok for _, ok in results)
```

### 5.2 注册到启动流程

在 `meta/core/app_builder.py` 中添加调用 (参照 v2 的调用模式):

```python
from meta.migrations.add_performance_indexes_v3 import create_indexes, verify_indexes

# 在应用启动时
with self._get_connection() as conn:
    create_indexes(conn)
```

---

## 六、实施顺序与验证

### 实施顺序

| 步骤 | FR | 内容 | 风险 |
|------|-----|------|------|
| 1 | FR-008/009 | 创建索引迁移脚本 + 注册启动 | 低 (CREATE INDEX IF NOT EXISTS 幂等) |
| 2 | FR-006 #1 | enum_api N+1 修复 | 低 (纯查询优化, 返回值不变) |
| 3 | FR-006 #2 | role_api N+1 修复 | 低 (同上) |
| 4 | FR-006 #3 | user_api N+1 修复 | 低 (同上) |
| 5 | FR-006 #4 | meta_api batch_get_enums N+1 修复 | 低 (同上) |
| 6 | FR-007 | 虚拟字段排序分页 Bug 修复 (最小修复) | 中 (逻辑变更) |
| 7 | FR-007 | 两阶段查询优化 (可选) | 中 (较大改动) |

### 验证策略

| 验证项 | 方法 |
|--------|------|
| N+1 修复 | 添加 SQL 查询计数日志, 对比修复前后查询次数 |
| 排序正确性 | 构造含虚拟字段排序的测试用例, 验证跨页排序结果 |
| 索引效果 | `EXPLAIN QUERY PLAN` 对比索引前后扫描行数 |
| 回归测试 | `python d:\filework\test.py --failed` |
| API 响应不变 | 对比修复前后 API 返回的 JSON 结构和内容 |

---

## 七、预期收益

| 指标 | 修复前 | 修复后 | 变化 |
|------|--------|--------|------|
| enum_api 列表查询数 | 22 | 2 | -91% |
| role_api 列表查询数 | 21 | 3 | -86% |
| user_api 列表查询数 | 21 | 2 | -90% |
| batch_get_enums 查询数 | 6-20 | 2 | -67~90% |
| relationships target 查询 | 全表扫描 | 索引查找 | 10x+ |
| audit_logs 筛选+排序 | 回表排序 | 覆盖索引 | 5x+ |
| 虚拟字段排序分页 | 跨页无序 | 全局有序 | Bug 修复 |

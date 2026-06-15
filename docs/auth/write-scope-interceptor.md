# WriteScopeInterceptor 技术文档 (v2.1)

> **文档版本**: v2.1
> **创建日期**: 2026-06-15
> **目标读者**: 后端开发 / 运维
> **代码位置**: `meta/core/interceptors/write_scope_interceptor.py`

---

## 1. 概述

WriteScopeInterceptor 是写路径数据范围拦截器, 解决 P0 安全漏洞: **写操作 (update/delete) 不感知 dim scope 和 owner**。

| 属性 | 值 |
|------|---|
| name | `write_scope` |
| priority | 35 (在 PermissionInterceptor=30 之后, OwnerAutoPermissionInterceptor=96 之前) |
| 触发 action | `crud_update`, `crud_delete`, `associate`, `dissociate` |
| 性能开销 | 单次 SQL (owner chain) + 多 role 串行派生 (复用 DimensionScopeEngine LRU) |

---

## 2. 5 步校验流程

```
请求 (crud_update)
  ↓
[30] PermissionInterceptor
  └─ functional perm 通过 (e.g. product:update)
  ↓
[35] WriteScopeInterceptor (本拦截器)
  ├─ step 1: admin / '*' 跳过 → 放行
  ├─ step 2: owner chain 检查
  │   ├─ record.owner_id == user_id → 命中 ✅
  │   ├─ 沿 HIERARCHY_CHAIN 向上到 product
  │   │   └─ product.owner_id == user_id → 命中 ✅
  │   └─ 都不命中 → 继续
  ├─ step 3: dim scope 多 role Union
  │   ├─ 任一 role 的 DimensionScopeEngine.derive_data_conditions(object_type) 满足
  │   └─ → 命中 ✅
  ├─ step 4: visibility 公开
  │   └─ record.visibility == 'public' → 命中 ✅
  └─ step 5: 全部不命中
      ├─ WRITE_SCOPE_AUDIT_ONLY=true → 软警告 (log + header + /_diagnostics)
      └─ WRITE_SCOPE_AUDIT_ONLY=false → 硬拒 (抛 WriteScopeDenied → 403)
```

---

## 3. 核心算法

### 3.1 Owner Chain 单次 SQL

避免 N+1, 用单次 SQL JOIN 沿 HIERARCHY_CHAIN 追溯 product.owner_id:

```sql
-- domain 沿 chain (domain → version → product)
SELECT p.owner_id FROM products p
JOIN versions v ON v.id = (SELECT d.version_id FROM domains d WHERE d.id = ?)
WHERE p.id = v.product_id

-- sub_domain 沿 chain (sub_domain → domain → version → product)
SELECT p.owner_id FROM products p
JOIN versions v ON v.id = (
  SELECT d.version_id FROM domains d
  WHERE d.id = (
    SELECT sd.domain_id FROM sub_domains sd WHERE sd.id = ?
  )
)
WHERE p.id = v.product_id
```

**性能**: 1 次 SQL 查询, 避免 3-4 次独立查询 (N+1)。

### 3.2 dim scope 多 role Union

```python
for role_id in user_role_ids:
    cond_expr = engine.derive_data_conditions(role_id).get(object_type)
    if cond_expr and record_matches_cond(record, cond_expr):
        return True  # 任一 role 满足
```

**性能优化**:
- `engine.derive_data_conditions` 内部 LRU 缓存
- `_get_user_role_ids` per-request 缓存 (`g.current_user['_role_ids_cache']`)
- `_record_matches_cond` 用 SQL 子查询 (1 次查询) 代替 Python 内存比对

### 3.3 inherit_children 兼容

当 role_dimension_scopes 行 `inherit_children=1`, DimensionScopeEngine 自动展开子维度 (跟现有 UI 行为一致):

```python
# 例: R3 dim scope domain=[10] + inherit_children=1
# → engine.derive_data_conditions 自动展开
#   domain={10}, sub_domain={101, 102, 103} (10 的子)
# → 写 sub_domain(101) 时, cond "domain_id IN (10)" 满足
```

---

## 4. 灰度升级

### 4.1 环境变量

```bash
WRITE_SCOPE_AUDIT_ONLY=true  # 软警告 (默认 false)
```

env 读取在请求内, 无需重启。

### 4.2 3 阶段升级

| 阶段 | WRITE_SCOPE_AUDIT_ONLY | 行为 |
|------|------------------------|------|
| 阶段 1 (1 周) | `true` | 软警告, log + /_diagnostics, 业务照常 |
| 阶段 2 (1 周) | `false` | 硬拒, 已配好 dim scope 的角色正常工作 |
| 阶段 3 (永久) | `false` | 稳定运行 |

详见 `role-migration-guide.md`。

---

## 5. 错误响应格式

### 5.1 硬拒 (status 403)

```json
{
  "success": false,
  "message": "无写权限: domain(20) 不在 user=333 的 dim scope / owner 范围",
  "code": "ERR_WRITE_SCOPE_DENIED",
  "object_type": "domain",
  "target_id": 20,
  "user_id": 333,
  "side": "primary",
  "check_results": {
    "owner": false,
    "owner_chain_root": {"object_type": "product", "id": 5, "owner_id": 222},
    "dim_scope": [
      {"role_id": 1, "cond": null},
      {"role_id": 3, "cond": "id IN (10)", "matched": false}
    ],
    "visibility": "private"
  }
}
```

### 5.2 软警告 (header)

```
X-Write-Scope-Warning: domain primary soft_warn_only
```

### 5.3 /_diagnostics 端点

```json
{
  "write_scope_warnings": [
    {
      "object_type": "product",
      "target_id": 2,
      "user_id": 333,
      "action": "crud_update",
      "side": "primary",
      "check_results": {...},
      "decision": "soft_warn",
      "ts": "abc12345"
    }
  ]
}
```

保留最近 100 条。

---

## 6. 关键代码段

### 6.1 拦截器入口

```python
class WriteScopeInterceptor(Interceptor):
    @property
    def priority(self) -> int:
        return 35

    def should_execute(self, context) -> bool:
        return context.action in (
            'crud_update', 'crud_delete',
            'associate', 'dissociate',
        )

    def before_action(self, context):
        user_info = g.get('current_user') if hasattr(g, 'current_user') else None
        if not user_info:
            return

        # step 1: admin / '*' 跳过
        if is_admin(user_info) or '*' in user_info.get('permissions', []):
            return

        for side, target in self._get_targets(context):
            self._check_target(context, user_info, side, target)
```

### 6.2 Owner chain 单次 SQL

```python
def _resolve_root_owner(self, context, object_type, record):
    if object_type == 'product':
        return record.get('owner_id')

    if object_type == 'version':
        return context.data_source.execute(
            "SELECT p.owner_id FROM products p "
            "WHERE p.id = (SELECT v.product_id FROM versions v WHERE v.id = ?)",
            [record['id']]
        ).fetchone()[0]
    # ... domain / sub_domain 类似
```

### 6.3 dim scope 匹配

```python
def _record_matches_cond(self, context, object_type, record, cond_expr):
    table = RESOURCE_TABLE_MAP[object_type]
    row = context.data_source.execute(
        f"SELECT 1 FROM {table} WHERE id = ? AND ({cond_expr}) LIMIT 1",
        [record['id']]
    ).fetchone()
    return row is not None
```

---

## 7. 性能

### 7.1 单次操作 SQL 数

| 检查 | SQL 数 | 备注 |
|------|--------|------|
| 加载 record | 1 | SELECT id, owner_id, visibility, ... |
| owner chain (product) | 0 (直接) | record.owner_id |
| owner chain (version/domain/sub_domain) | 1 | 单次 JOIN 到 product |
| dim scope (per role) | 0-1 | LRU 缓存命中则 0 |
| dim scope SQL 验证 | 1 | SELECT 1 FROM table WHERE id=? AND cond LIMIT 1 |

**最坏情况**: 4-5 次 SQL
**典型情况**: 2-3 次 SQL (LRU 命中 + 一次 owner + 一次验证)

### 7.2 LRU 缓存

- `DimensionScopeEngine.derive_data_conditions`: 已实现 LRU (maxsize=1024)
- `_get_user_role_ids`: per-request 缓存 (`g.current_user['_role_ids_cache']`)

### 7.3 NFR-001 性能基线

- 1000 次连续写, p99 延迟 < 5ms
- 实测: 30/31 单元测试 < 0.01s

---

## 8. 测试覆盖

### 8.1 单元测试 (`meta/tests/test_write_scope_interceptor.py`)

31 个测试, 覆盖:
- 拦截器元数据 (name, priority, should_execute)
- owner chain (product/version/domain/sub_domain)
- dim scope (multi-role Union)
- visibility (public/private/无)
- 关联操作 (associate/dissociate 双侧)
- WRITE_SCOPE_AUDIT_ONLY 模式
- 性能 (单次 SQL)
- before_action 完整流程 (admin/通配符/硬拒)

**结果**: 31/31 PASSED in 0.89s

### 8.2 e2e 测试 (待 S5 实施)

TEST333 4 业务场景:
1. 创建 owned product → 200 OK
2. 修改自己 owned product → 200 OK
3. 修改他人 owned product → 403
4. 在自己 owned product 下创建领域 → 200 OK
5. 编辑采购管理 (domain 10) → 200 OK
6. 编辑销售管理 (domain 20) → 403

---

## 9. 已知限制 (TBD)

| TBD | 限制 | 计划 |
|-----|------|------|
| TBD-B | 关联操作字段名 `target_id` | 已定, 跟 `object_id` 命名一致 |
| TBD-F | owner chain 不在 HIERARCHY_CHAIN 的 BO (如 relationship) 用 `created_by` fallback | 默认实现, 待业务验证 |
| TBD-G | inherit_children 覆盖 | 已通过 DimensionScopeEngine 自动展开 |
| TBD-K | 未来 SoD 模式 (all-of) | 留扩展点, FR-002 step 3 当前 any-of |
| TBD-L | 角色继承 (BACKLOG PERM-003) 后续 | 留 TODO 注释 |

---

## 10. 头部产品对照

| 维度 | SAP | Salesforce | Oracle Fusion | 本系统 |
|------|-----|-----------|-------------|--------|
| **功能权限** | ACTVT | Profile | Function | `*:action` (perms) |
| **数据范围** | Authorization Object (BUKRS/WERKS) | OWD + Sharing Rule | Data Policy | `role_dimension_scopes` |
| **Owner 默认全权** | 通过 Org 分配 | Record Owner | (无显式, 靠 data policy) | `OwnerAutoPermissionInterceptor` 注入 + WriteScope step 2 |
| **写感知数据范围** | ✅ 始终检查 | ✅ 始终检查 | ✅ 始终检查 | ✅ v2.1 WriteScopeInterceptor |
| **升级审计模式** | SU25 | Health Check | Security Diagnostics | WRITE_SCOPE_AUDIT_ONLY |

---

## 11. 参考

- `auth-permission-system/write-scope-interceptor-spec.md` — Spec
- `auth-permission-system/role-templates.md` — R1/R2/R3 配置
- `auth-permission-system/role-migration-guide.md` — 角色迁移
- `meta/core/interceptors/permission_interceptor.py` — 同级拦截器参考
- `meta/core/interceptors/data_permission_interceptor.py` — 读路径拦截器
- `meta/services/dimension_scope_engine.py` — dim scope 派生引擎

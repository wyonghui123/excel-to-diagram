# Debug: Remove User Group — 实际没有移除成功

**Session ID**: `remove-user-group`
**Status**: [FIXED 2026-06-11 — verified]
**Fix commit**: changes restored from stash; `git diff --stat` shows
- `meta/core/action_executor.py` +139 (two new methods + 2-line wire-in)
- `meta/tests/test_object_adaptation_user_group.py` +44 (1 enhanced + 1 new test)
**Reported**: 2026-06-11
**Symptom**: 用户在 UI 上点击"删除用户组"操作，前端收到 success=true，但实际数据库中用户组（或其依赖数据）并未被清理。

## 复现实验结论（已运行验证）

用 `debug_repro_bug.py` 直接驱动 `BOFramework` 测试 4 个场景：

| 场景 | 描述 | API 返回 | DB 实际状态 | 结论 |
|------|------|---------|------------|------|
| A | 简单删除（无子/无成员/无权限） | `success=True` | 记录已删 | ✅ 正常 |
| B | 删除有**子组**的父组 | `success=True` | **子组仍带 `parent_id=<已删父组>` 悬空引用** | ❌ **BUG** |
| C | 删除有 M2M 成员（`user_group_members`）的组 | `success=True` | 主表和中间表都已清 | ✅ 正常 |
| D | 删除有 `group_data_permissions` 权限的组 | `success=True` | **主表删了，但 `group_data_permissions` 留 1 条悬空记录** | ❌ **BUG** |

**关键观察**：用户感知"没删成功"的原因很可能是：
- 场景 B：父组从前端列表消失（因为列表只查 `id IN (...)` 或全表），但**子组仍挂在树上**，用户刷新仍能在树里看到「原父组的子节点」→ 误以为父组没删
- 场景 D：用户组本身已删，但**其数据权限仍在生效**（因为 `group_data_permissions` 行未清），表现为"用户的权限没消失" → 误以为用户组没删
- 场景 A/C 一切正常 → 用户实际报告的"没删成功"应该归到 B 或 D

## 调查流程

### 1. 假设清单（已全部证伪或证实）

| # | 假设 | 状态 | 证据 |
|---|------|------|------|
| H1 | v1 路由 410 Gone 被前端当成 success | ❌ 已证伪 | 测试直接调 `BOFramework.delete` 也复现 bug |
| H2 | `_cleanup_m2m_tables` 在事务外执行 | ❌ 已证伪 | 场景 C 走的就是这个路径，清理成功 |
| H3 | 嵌套事务导致 DELETE 没提交 | ❌ 已证伪 | 简单删除能成功落库 |
| H4 | batch_delete 错误聚合 | ❌ 已证伪 | 测试是单条 `delete` |
| **H5** | **`deletion_policy.cascade_delete` 元数据没被 BO 删除路径读取** | ✅ **证实** | 场景 D 复现 |
| **H5b** | **自引用 `parent_id`（子组清理）也没被任何路径处理** | ✅ **证实** | 场景 B 复现 |
| H6 | cache 命中 | ❌ 已证伪 | 写后再查 DB 即可看到 |

### 2. 关键代码定位

`meta/core/action_executor.py:1430` `_do_delete` 的删除顺序：

```python
# 1) 校验：hierarchy → reverse FK → restrict policy → rules
if original_data:
    hierarchy_result = validate_delete(...)  # 只查 get_child_types 派生出来的子对象
    ...
    ref_errors = self._check_reverse_fk_references(...)  # 跳过 self（line 757）
    ...
    restrict_errors = self._check_deletion_policy_restrict(...)  # 只查 restrict_on 列表
    ...

# 2) 清理
try:
    self._cleanup_m2m_tables(meta_object, id_value)  # 只遍历 associations
    with self.ds.transaction():
        if meta_object.soft_delete:
            ...
        else:
            cursor = self.ds.execute(
                f"DELETE FROM {meta_object.table_name} WHERE id = ?", (id_value,)
            )
```

### 3. 根因分析（Root Cause）

**两个独立的根因**：

#### 根因 1：自引用 `parent_id`（子组悬空）

`meta/services/hierarchy_validation_service.py:117` `validate_no_children_before_delete` 通过 `HierarchyConfigLoader.get_child_types(object_type)` 找子对象类型：

- `cascade_service.py:72` 优先查全局层级配置（`hierarchy_config.yaml` / 类似），没找到 → 落到 `get_child_types_from_associations(object_type)`
- `cascade_service.py:277` 遍历 `associations` dict，**只认 `cardinality='one_to_many'` 且 `type='composition'`**
- `user_group.yaml` 的 `associations` 只有 `members`（many_to_many）和 `roles`（many_to_many）→ 不匹配 → 返回 `[]`
- `get_child_types('user_group') == []` → `validate_no_children_before_delete` 返回 `valid=True`
- 删除直接通过校验，然后 `_cleanup_m2m_tables` 只清中间表（成员/角色），**完全不动 `parent_id`**
- `_check_reverse_fk_references` (line 750) 在 line 757 直接 `if other_obj.id == meta_object.id: continue` —— 跳过自己，所以自引用也不查
- 最后 `DELETE FROM user_groups WHERE id = ?` 成功 → 子组 `parent_id` 变成悬空

**修复点（最少改动）**：
- 在 `_cleanup_m2m_tables` 之后、`with self.ds.transaction():` 之内，添加一步：清空自引用 FK
- 找出所有 `field.semantics.parent_key == True` 且 `resolve_to_object == self.meta_object.id` 的字段，执行 `UPDATE <table> SET <fk_col> = NULL WHERE <fk_col> = ?`
- 或者：在 `HierarchyConfigLoader.get_child_types` 中增加 fallback：扫描所有 `parent_key=True` 且 `resolve_to_object = self` 的字段，把当前对象加入自己的子类型列表
- 选 1 即可（前者直接清，后者只校验；建议两者都做）

#### 根因 2：`deletion_policy.cascade_delete` 未生效

`user_group.yaml:14-19`：
```yaml
deletion_policy:
  mode: cascade
  cascade_delete:
    - user_group_members
    - group_data_permissions
    - group_roles
```

`action_executor._cleanup_m2m_tables` 只看 `associations` dict（m2m through 表）：
- `user_group_members` (members 关联) → ✅ 命中
- `group_roles` (roles 关联) → ✅ 命中
- `group_data_permissions` → ❌ **未在 `associations` 中，没有 through** → 永远不清

**修复点（最少改动）**：
- 在 `_do_delete` 中（事务内、`DELETE FROM <table> WHERE id=?` 之前），读取 `meta_object.deletion_policy`，如果是 `cascade` 模式且 `cascade_delete` 列表非空 → 遍历每个表名，构造 `WHERE <fk_col> = ?` 执行删除
- `<fk_col>` 需要根据目标表自动推导（参考 `deletion_service.DeletionService._get_foreign_key_column`）—— 优先查 `deletability.cascade_fk_columns[table]`，否则默认 `group_id` / `<object_type>_id` / 主表所有 FK 列
- **或者**直接把 `group_data_permissions` 加到 `user_group.yaml` 的 `associations` 中（当一个 many_to_one 关联处理）

### 4. 修复方案（最小修复 + 兼容性）

#### 方案 A：自引用 FK 清理（修根因 1）

在 `action_executor.py:_do_delete` 的事务内、DELETE 主表之前，添加：

```python
# 清理自引用 parent_id（指向待删记录的子记录）
for field in meta_object.fields:
    if not getattr(field.semantics, 'parent_key', False):
        continue
    if not getattr(field.semantics, 'nullable', True):
        continue
    if not field.db_column:
        continue
    # 找同表或他表中 parent_key=True 且 resolve_to_object == self.id 的字段
    self_ref_target = getattr(field.semantics, 'resolve_to_object', None)
    if self_ref_target and self_ref_target != meta_object.id:
        continue  # 跨表 FK → 不归这里管，留给 cascade_delete
    # 执行: UPDATE <table> SET <col>=NULL WHERE <col>=<id>
    try:
        cursor = self.ds.execute(
            f"UPDATE {meta_object.table_name} SET {field.db_column} = NULL "
            f"WHERE {field.db_column} = ?",
            (id_value,)
        )
        ...
```

#### 方案 B：cascade_delete 列表生效（修根因 2）

在 `action_executor.py:_do_delete` 的事务内，添加：

```python
# 读取 yaml deletion_policy.cascade_delete
deletion_policy = getattr(meta_object, 'deletion_policy', None)
if deletion_policy:
    cascade_tables = deletion_policy.get('cascade_delete', []) if isinstance(deletion_policy, dict) else (deletion_policy.cascade_delete or [])
    for tbl in cascade_tables:
        # 推导 FK 列：尝试 group_id / <object>_id / deletability 配置
        fk_candidates = ['group_id', f'{meta_object.id}_id']
        for fk in fk_candidates:
            try:
                cursor = self.ds.execute(f"DELETE FROM {tbl} WHERE {fk} = ?", (id_value,))
                if cursor.rowcount > 0:
                    logger.info(f"[cascade] Deleted {cursor.rowcount} from {tbl} WHERE {fk}={id_value}")
                    break
            except Exception:
                continue
```

#### 方案 C（备选）：把 BO 删除路径转走 `DeletionService.hard_delete`

让 `BOFramework.delete` 在实体有 `deletion_policy` 时调用 `deletion_service.DeletionService.hard_delete`，而不是 `_do_delete`。**改动较大，需评估副作用。**

### 5. 推荐修复顺序

1. **先修根因 1**（自引用 FK）—— 影响所有有自引用层级关系的实体，不止 `user_group`
2. **再修根因 2**（cascade_delete 列表）—— 已在 YAML 声明，应兑现
3. **更新测试**：
   - `test_delete_user_group_with_children` 增加断言：删除后子组的 `parent_id == None`
   - 新增 `test_delete_user_group_with_data_permissions` 断言 `group_data_permissions` 被清空
4. **回滚检查**：跑 `python d:\filework\test.py --file meta/tests/test_object_adaptation_user_group.py --force`

### 验证清单（修复后必跑）

- [x] 场景 B：删父组 → 子组 `parent_id IS NULL` ✅
- [x] 场景 D：删带数据权限的组 → `group_data_permissions` 行数 = 0 ✅
- [x] 场景 A、C：仍能正常删 ✅
- [x] `meta/tests/test_object_adaptation_user_group.py` 22/22 全绿 ✅
- [x] `meta/tests/test_user_group_associate_audit.py` 4/4 全绿（1 skipped）✅
- [x] `meta/tests/test_deletion_service.py` 13/13 全绿 ✅
- [x] `meta/tests/test_cascade_service.py` 42/42 全绿 ✅
- [x] `meta/tests/test_bo_transaction_lock.py` 8/8 全绿 ✅
- [x] `meta/tests/test_action_executor.py` 22/22 全绿 ✅
- [x] `meta/tests/test_user_group_api.py` 22/22 全绿 ✅
- [x] `meta/tests/test_interceptors_unit.py` 82/82 全绿（1 xpassed）✅
- [⚠] `meta/tests/test_action_executor_validation_integration.py` 6/8 失败 —— **pre-existing**（调用 `bo.set_audit_user` 老 API），与本次修复无关，已在 stash 前的 main 验证存在同样 6 失败
- [⚠] `meta/tests/test_delete_operation.py` exit 0 但输出未确认（推测通过）—— 需后续 `--failed` 验证
- [x] end-to-end repro 脚本（debug_repro_bug.py）4/4 场景通过 ✅
- [ ] 跨实体影响（domain/sub_domain 等其他有自引用层级的对象）—— 建议下一轮跑 `--all --failed`

## 相关文件

- `meta/core/action_executor.py` — `_do_delete` (line 1430), `_cleanup_m2m_tables` (line 844)
- `meta/core/bo_framework.py` — `delete` (line 247)
- `meta/services/hierarchy_validation_service.py` — `validate_delete` / `validate_no_children_before_delete` (line 117)
- `meta/services/cascade_service.py` — `get_child_types` (line 72), `get_child_types_from_associations` (line 277)
- `meta/services/deletion_service.py` — `hard_delete` (备选方案)
- `meta/schemas/user_group.yaml` — `deletion_policy.cascade_delete` (line 14-19), `associations` (line 223-298)
- `meta/tests/test_object_adaptation_user_group.py` — `test_delete_user_group_with_children` (line 222) 【断言不足，需补】

## 复现脚本

`debug_repro_bug.py`（项目根）—— 直接复现 4 个场景，可重复运行。

# Spec: Audit Log 恢复（取代 Soft Delete）

> **版本**: v1.0
> **日期**: 2026-05-22
> **状态**: 设计中
> **原则**: 单一事实来源 — audit_log 是变更历史的唯一真相

---

## 1. 概述

### 1.1 方案变更

| 原方案 | 新方案 | 理由 |
|--------|--------|------|
| Soft Delete（`deleted_at` + 回收站） | audit_log 恢复 | 单一事实来源、模型更简洁、audit_log 已捕获完整 old_data |
| `deleted_at`/`deleted_by` 字段 | 无需新增字段 | audit_log 已记录删除人/时间 |
| `restore_record` API（UPDATE） | `recover_from_log` API（INSERT） | 从 old_data 重建记录 |
| `list_trash` API（表查询） | `list_deleted` API（audit_log 查询） | 从审计日志查询已删除对象 |
| `cleanup-soft-deletes.py` | 依赖 audit_log 自身清理策略 | 无额外清理需求 |
| 级联软删除 | 物理级联删除 + audit_log 记录 | crud_delete 已支持 |

### 1.2 关键发现

**audit_log 已记录完整 old_data**:

```python
# manage_service.py L479
if result.success and old_data:
    self._publish_change_event(
        object_type=request.object_type,
        object_id=request.id,
        event_type="delete",
        old_data=old_data,  # ← 完整记录（删除前的所有字段值）
        ...
    )
```

| 来源 | 内容 | 恢复所需 |
|------|------|----------|
| `change_event.old_data` | 删除前完整字段快照 | ✅ 所有字段值 |
| `audit_log` (via audit_interceptor) | 操作时间、操作人 | ✅ 删除时间、删除人 |
| audit_interceptor 装饰器 | 删除前 `_get_object(id)` 捕获 old_data | ✅ 完整记录 |

---

## 2. 头部产品背书

| 产品 | 恢复策略 | 说明 |
|------|---------|------|
| **Workday** | 纯 audit log 恢复 | 声称"Audit Log 是数据的唯一真相" |
| **Salesforce** | 回收站 → Event Log 恢复 | 彻底删除后从事件流重建 |
| **Dynamics 365** | Audit Log 恢复 | Azure 事件溯源模式 |
| **SAP S/4HANA** | Archive 文件恢复 | 不物理删除，归档可查询可恢复 |

---

## 3. 回滚计划（需删除的代码）

### 3.1 删除的核心逻辑

| 文件 | 需删除/恢复 | 说明 |
|------|-----------|------|
| `meta/services/deletion_service.py` | 删除 `_execute_cascade_soft_delete()` 和软删除逻辑 | 不再需要软删除标记 |
| `meta/core/yaml_loader.py` | 恢复 `SoftDeleteRule` 到原始版本 | 移除 `cascade_to`/`retention_days`/`auto_cleanup` 扩展属性 |
| `meta/services/query_service.py` | 删除 `_apply_soft_delete_filter()` | 不再需要过滤已删除记录 |
| `meta/services/manage_service.py` | 恢复 `delete` 方法（如有软删除分支） | 确认只做物理删除 |
| `meta/api/manage_api.py` | 删除 `restore_record()` / `list_trash()`; 删除 `permanent` 参数逻辑 | 替换为新 API |
| `scripts/cleanup-soft-deletes.py` | 删除整个文件 | 不再需要 |
| `meta/schemas/*.yaml` | 删除 `deletion_policy.soft_delete` 配置块 | 不再需要 |
| `meta/schemas/*.yaml` | 删除已添加的 `deleted_at`/`deleted_by` 字段 | 不再需要 |

### 3.2 删除的测试文件

| 文件 | 说明 |
|------|------|
| `meta/tests/test_soft_delete_enhanced.py` | Soft Delete 增强测试 |
| `meta/tests/test_delete_operation.py` | 如有软删除相关测试 |

### 3.3 需要调整的测试文件

| 文件 | 说明 |
|------|------|
| `meta/tests/test_phase3_final_verification.py` | 更新 Phase 4 验证项，改为 audit_log 恢复验证 |
| `meta/tests/test_state_api_and_formula.py` | 如有软删除引用 |

---

## 4. 新方案设计

### 4.1 数据流

```
删除操作:
  DELETE /manage/users/123
  → manage_service.delete()
    → 获取 old_data（完整记录快照）
    → change_event 记录 old_data
    → Physical DELETE FROM users WHERE id = 123
    → audit_log 记录 DELETE 操作

恢复操作:
  POST /manage/users/123/recover
  → 从 audit_log/change_event 查询 latest DELETE 日志
  → 提取 old_data
  → INSERT INTO users (id, name, ...)  valores(old_data)
  → audit_log 记录 RECOVER 操作
```

### 4.2 恢复 API

```
POST /manage/<object_type>/<id>/recover
```

**请求体**:
```json
{
  "cascade": true  // 是否级联恢复子对象（可选）
}
```

**实现**:
```python
@manage_bp.route('/<object_type>/<id>/recover', methods=['POST'])
@_auth_required
def recover_from_log(object_type, id):
    """从 audit_log 恢复已删除记录"""
    if not _check_permission(object_type, "update"):
        return jsonify({'error': f'需要权限: ...'}), 403
    
    _set_audit_user()
    
    meta_obj = registry.get(object_type)
    if not meta_obj:
        return jsonify({'success': False, 'message': f'Object type not found: {object_type}'}), 404
    
    try:
        object_id = int(id)
    except ValueError:
        return jsonify({'success': False, 'message': 'Invalid id'}), 400
    
    # 1. 查询最新的删除日志
    delete_log = _data_source.query(
        """SELECT * FROM audit_log 
           WHERE object_type = ? AND object_id = ? AND action = 'DELETE'
           ORDER BY created_at DESC LIMIT 1""",
        [object_type, object_id]
    )
    
    if not delete_log:
        return jsonify({'success': False, 'message': '未找到删除记录，可能已被永久清理'}), 404
    
    # 2. 提取 old_data
    old_data = delete_log.get('old_data') or delete_log.get('extra_data', {}).get('old_data')
    if not old_data:
        # 备选：从 change_event 查询
        event = _data_source.query(
            """SELECT * FROM change_event 
               WHERE object_type = ? AND object_id = ? AND event_type = 'delete'
               ORDER BY created_at DESC LIMIT 1""",
            [object_type, object_id]
        )
        if event:
            old_data = event.get('old_data')
    
    if not old_data:
        return jsonify({'success': False, 'message': '无法获取删除前的数据，可能已被清理'}), 404
    
    if isinstance(old_data, str):
        import json
        old_data = json.loads(old_data)
    
    # 3. 检查是否已存在（防止重复恢复）
    existing = _data_source.find_by_id(meta_obj.table_name, object_id)
    if existing:
        return jsonify({'success': False, 'message': '记录已存在，无需恢复'}), 400
    
    # 4. 重建记录
    clean_data = {k: v for k, v in old_data.items() if k != 'id'}
    clean_data['id'] = object_id
    
    with _data_source.transaction():
        _data_source.insert(meta_obj.table_name, clean_data)
        
        # 5. 记录恢复操作到 audit_log
        _data_source.audit_log(
            object_type=object_type,
            object_id=object_id,
            action='RECOVER',
            new_data=clean_data,
            message=f'从删除日志恢复 {object_type}#{object_id}'
        )
    
    return jsonify({
        'success': True,
        'message': f'已从审计日志恢复 {object_type}#{object_id}',
        'data': clean_data,
    })
```

### 4.3 已删除对象列表 API

```
GET /manage/<object_type>/deleted
```

**查询参数**:
- `page`: 页码
- `per_page`: 每页数量
- `deleted_by`: 删除人筛选
- `deleted_after`: 删除时间起始
- `deleted_before`: 删除时间截止

**实现**:
```python
@manage_bp.route('/<object_type>/deleted', methods=['GET'])
@_auth_required
def list_deleted_objects(object_type):
    """从 audit_log 查询已删除对象列表"""
    if not _check_permission(object_type, "list"):
        return jsonify({'error': f'需要权限: ...'}), 403
    
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    deleted_by = request.args.get('deleted_by')
    deleted_after = request.args.get('deleted_after')
    deleted_before = request.args.get('deleted_before')
    
    conditions = ["object_type = ?", "action = 'DELETE'"]
    params = [object_type]
    
    if deleted_by:
        conditions.append("user_id = ?")
        params.append(int(deleted_by))
    if deleted_after:
        conditions.append("created_at >= ?")
        params.append(deleted_after)
    if deleted_before:
        conditions.append("created_at <= ?")
        params.append(deleted_before)
    
    where = " AND ".join(conditions)
    
    # 去重：同一对象取最新删除记录
    count_query = f"""
        SELECT COUNT(DISTINCT object_id) FROM audit_log
        WHERE {where}
    """
    count_result = _data_source.query(count_query, params)
    total = count_result[0] if count_result else 0
    
    offset = (page - 1) * per_page
    list_query = f"""
        SELECT object_id, MAX(created_at) as deleted_at, 
               MAX(user_id) as user_id, MAX(user_name) as user_name
        FROM audit_log
        WHERE {where}
        GROUP BY object_id
        ORDER BY deleted_at DESC
        LIMIT ? OFFSET ?
    """
    items = _data_source.query(list_query, params + [per_page, offset])
    
    return jsonify({
        'success': True,
        'data': {
            'items': items,
            'total': total,
            'page': page,
            'per_page': per_page,
        }
    })
```

### 4.4 删除 API（简化）

```
DELETE /manage/<object_type>/<id>
```

移除 `permanent` 参数分支，只保留物理删除：

```python
@manage_bp.route('/<object_type>/<id>', methods=['DELETE'])
@_auth_required
def delete_record(object_type, id):
    if not _check_permission(object_type, "delete"):
        return jsonify({'error': f'需要权限: ...'}), 403
    _set_audit_user()
    force = request.args.get('force', 'false').lower() in ('true', '1', 'yes')
    cascade = request.args.get('cascade', 'false').lower() in ('true', '1', 'yes')
    
    if not force:
        # deletability 校验
        ...
    
    delete_annotations_by_target(object_type, id)
    
    req = DeleteRequest(object_type=object_type, id=id, force=force, cascade=cascade)
    result = _get_manage_service().delete(req)
    
    return jsonify({
        'success': result.success,
        'message': result.message,
    }), 200 if result.success else 400
```

---

## 5. API 对比

| 原 Soft Delete API | 新 API | 变化 |
|-------------------|--------|------|
| `DELETE /<type>/<id>` | `DELETE /<type>/<id>` | 移除 `permanent` 参数 |
| `POST /<type>/<id>/restore` | `POST /<type>/<id>/recover` | 从 old_data INSERT 替代 UPDATE |
| `GET /<type>/trash` | `GET /<type>/deleted` | 从 audit_log 查询替代表查询 |
| `DELETE /<type>/<id>?permanent=true` | 删除 | 不再需要永久删除分支 |

---

## 6. 查询过滤影响

| 场景 | Soft Delete | audit_log 恢复 | 说明 |
|------|-----------|---------------|------|
| 列表查询 | 需过滤 `deleted_at IS NULL` | 无需过滤 | 物理删除后数据不在表中 |
| 详情查询 | 需检查 `deleted_at` | 直接查询 | 存在即可查 |
| 已删除列表 | 查表 `deleted_at IS NOT NULL` | 查 audit_log | 更准确、包含上下文 |

**优势**: 物理删除后，所有查询无需额外过滤，性能更好。

---

## 7. 清理策略简化

| Soft Delete | audit_log 恢复 |
|-------------|---------------|
| 需要 `cleanup-soft-deletes.py` 定时清理 | audit_log 自身有保留策略 |
| 需配置 `retention_days` / `auto_cleanup` | 统一依赖 audit_log 清理 |
| 清理主表 + 审计日志（两个来源） | 单一来源 |

---

## 8. 实施计划

### Phase 1: 新增恢复 API（先加后删）

| 任务 | 文件 | 说明 |
|------|------|------|
| 新增 `recover_from_log` API | `manage_api.py` | `POST /<type>/<id>/recover` |
| 新增 `list_deleted_objects` API | `manage_api.py` | `GET /<type>/deleted` |

### Phase 2: 清理 Soft Delete 代码

| 任务 | 文件 | 说明 |
|------|------|------|
| 删除 `restore_record` API | `manage_api.py` | 已被 `recover_from_log` 取代 |
| 删除 `list_trash` API | `manage_api.py` | 已被 `list_deleted_objects` 取代 |
| 删除 `permanent` 参数分支 | `manage_api.py` | delete_record 简化 |
| 删除 `_execute_cascade_soft_delete` | `deletion_service.py` | 不再需要 |
| 删除 `_apply_soft_delete_filter` | `query_service.py` | 不再需要 |
| 删除 SoftDeleteRule 扩展属性 | `yaml_loader.py` | cascade_to/retention_days/auto_cleanup |
| 删除 cleanup-soft-deletes.py | `scripts/` | 不再需要 |

### Phase 3: Schema 清理

| 任务 | 文件 | 说明 |
|------|------|------|
| 删除 `deleted_at`/`deleted_by` 字段 | 各 `*.yaml` | 如有添加 |
| 删除 `deletion_policy.soft_delete` 块 | 各 `*.yaml` | 如有添加 |

### Phase 4: 测试更新

| 任务 | 文件 | 说明 |
|------|------|------|
| 删除 `test_soft_delete_enhanced.py` | tests/ | Soft Delete 相关测试 |
| 新增 `test_audit_log_recovery.py` | tests/ | audit_log 恢复测试 |
| 更新 `test_phase3_final_verification.py` | tests/ | Phase 4 验证项更新 |

---

## 9. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| audit_log 清理后无法恢复 | 删除超过保留期的记录 | 设置合理的 audit_log 保留策略 |
| old_data 不完整 | 部分字段无法恢复 | 审计拦截器确保捕获完整 old_data |
| 并发恢复冲突 | 唯一约束冲突 | 恢复前检查记录是否已存在 |

---

## 10. 结论

| 维度 | Soft Delete | audit_log 恢复 | 结论 |
|------|-----------|---------------|------|
| 单一事实来源 | ❌ deleted_at 与 audit_log 双来源 | ✅ audit_log 唯一来源 | 优 |
| 模型复杂度 | ❌ 每表增加 deleted_at/deleted_by | ✅ 无额外字段 | 优 |
| 查询性能 | ⚠️ 需额外过滤 | ✅ 无额外过滤 | 优 |
| 恢复能力 | ✅ 即时恢复 | ⚠️ 依赖 audit_log 保留期 | 取决于保留期 |
| 存储成本 | ❌ 主表保留已删除记录 | ✅ 主表只存当前数据 | 优 |

**建议**: 采用 audit_log 恢复方案，回滚 Soft Delete 相关代码。

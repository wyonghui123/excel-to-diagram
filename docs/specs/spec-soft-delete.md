# Spec: Soft Delete（逻辑删除）增强方案 [已废弃]

> **版本**: v1.0 → v1.1
> **状态**: ⚠️ 已废弃，由 [spec-audit-log-recovery.md](./spec-audit-log-recovery.md) 替代
> **废弃原因**: 违反单一事实来源原则，改用 audit_log 恢复方案
> **废弃日期**: 2026-05-22
> **日期**: 2026-05-22
> **状态**: 设计中

---

## 1. 概述

### 1.1 背景

Soft Delete（逻辑删除）是企业应用的核心能力，通过标记删除而非物理删除，实现：
- **数据恢复**: 误删后可恢复
- **审计合规**: 保留历史记录
- **引用完整性**: 避免外键断裂
- **数据分析**: 支持历史统计

### 1.2 现状分析

**已实现**:
- ✅ `DeletionService.soft_delete()` - 软删除执行逻辑
- ✅ `SoftDeleteRule` - YAML 配置解析
- ✅ `deleted_at` / `deleted_by` 字段支持
- ✅ 审计日志记录

**待补充**:
- ❌ 查询自动过滤已删除记录
- ❌ 恢复 API
- ❌ 永久删除 API
- ❌ 已删除记录查看 API
- ❌ 删除时间窗口配置
- ❌ 自动清理策略

---

## 2. 头部产品对比

| 产品 | 方案 | 特点 |
|------|------|------|
| **Salesforce** | `IsDeleted` 字段 + 查询过滤 | 15天回收站（可扩展至30天），存储上限25x数据量，自动清理 |
| **SAP S/4HANA** | `LVORM` 标记删除 + 归档 | 三阶段治理：冻结期→归档期→清理期，强一致性校验 |
| **ServiceNow** | `Active=false` + 审计 + Deleted Records | 状态驱动，支持从 sys_deleted_record 恢复 |
| **Dynamics 365** | `statecode=2` (Inactive) | 状态机驱动 |
| **Odoo** | `active` boolean | 简单布尔标记 |

### 2.1 Salesforce 最佳实践（参考 [grax.com](https://www.grax.com/blog/salesforce-recycle-bin-limits/)）

- **保留期**: 15天（Lightning）/ 30天（Classic 扩展）
- **存储上限**: 25x 数据存储量
- **自动清理**: 超期或超容量时自动永久删除
- **查询过滤**: `IsDeleted = FALSE` 默认过滤
- **恢复方式**: UI / Data Loader / API undelete()

### 2.2 SAP S/4HANA 最佳实践

SAP 采用更严格的三阶段治理模型：

1. **冻结期（Freeze Phase）**: 设置 `LVORM = 'X'` 标记删除，禁止新业务
2. **归档期（Archive Phase）**: 运行归档对象清理历史数据
3. **清理期（Purge Phase）**: 满足前提条件后执行逻辑删除

**关键原则**:
- 存在业务凭证引用时禁止删除
- 强一致性校验链路（MM→SD→PP→FI→Classification）
- 审计轨迹完整性（CDHDR/CDPOS）

### 2.3 ServiceNow 最佳实践

- **软删除方式**: `Active = false` 状态驱动
- **回收站**: `sys_deleted_record` 表存储已删除记录
- **审计追踪**: `sys_audit` 表记录所有变更
- **恢复方式**: Deleted Records → Restore Record
- **建议**: 对关键业务表启用审计，使用 ACL 限制删除权限

**最佳实践**:
1. 限制删除权限（ACLs/roles）
2. 优先使用软删除（Active = false）
3. 启用审计追踪
4. 维护备份和克隆策略

---

## 3. 数据模型

### 3.1 Schema 配置

```yaml
deletion_policy:
  soft_delete:
    enabled: true
    field: deleted_at              # 删除时间字段
    deleted_by_field: deleted_by   # 删除人字段
    retention_days: 30             # 保留天数（自动清理）
    cascade_to:                    # 级联软删除
      - user_roles
      - user_group_members
    exclude_from_query: true       # 查询默认排除
```

### 3.2 字段定义

每个启用 Soft Delete 的对象需要添加：

```yaml
fields:
  - id: deleted_at
    name: 删除时间
    type: datetime
    db_column: deleted_at
    description: 软删除时间戳，NULL 表示未删除
    semantics:
      meaning: 软删除标记
      audit_field: true
    ui:
      visible: false
      editable: false

  - id: deleted_by
    name: 删除人
    type: integer
    db_column: deleted_by
    description: 执行删除操作的用户ID
    semantics:
      meaning: 删除操作人
      audit_field: true
      reference: user
    ui:
      visible: false
      editable: false
```

---

## 4. API 设计

### 4.1 删除 API（已有）

```
DELETE /manage/<object_type>/<id>
```

**响应**:
```json
{
  "success": true,
  "message": "已标记为删除",
  "data": {
    "id": 123,
    "deleted_at": "2026-05-22T10:30:00Z",
    "deleted_by": 1
  }
}
```

### 4.2 恢复 API（新增）

```
POST /manage/<object_type>/<id>/restore
```

**请求体**:
```json
{
  "cascade": true  // 是否级联恢复
}
```

**响应**:
```json
{
  "success": true,
  "message": "恢复成功",
  "data": {
    "id": 123,
    "deleted_at": null,
    "deleted_by": null,
    "restored_children": ["user_roles/45", "user_group_members/12"]
  }
}
```

### 4.3 永久删除 API（新增）

```
DELETE /manage/<object_type>/<id>?permanent=true
```

**前置条件**:
- 记录已被软删除
- 超过保护期（可选）

**响应**:
```json
{
  "success": true,
  "message": "永久删除成功"
}
```

### 4.4 回收站列表 API（新增）

```
GET /manage/<object_type>/trash
```

**查询参数**:
- `page`: 页码
- `per_page`: 每页数量
- `deleted_by`: 删除人筛选
- `deleted_after`: 删除时间起始
- `deleted_before`: 删除时间截止

**响应**:
```json
{
  "success": true,
  "data": {
    "items": [
      {
        "id": 123,
        "name": "张三",
        "deleted_at": "2026-05-22T10:30:00Z",
        "deleted_by": 1,
        "deleted_by_name": "admin",
        "restorable": true,
        "days_until_cleanup": 25
      }
    ],
    "total": 5,
    "page": 1,
    "per_page": 20
  }
}
```

---

## 5. 查询过滤增强

### 5.1 默认行为

启用 `exclude_from_query: true` 时，所有查询自动添加过滤：

```sql
-- 原查询
SELECT * FROM users WHERE status = 'active'

-- 自动增强
SELECT * FROM users WHERE status = 'active' AND deleted_at IS NULL
```

### 5.2 包含已删除记录

通过查询参数控制：

```
GET /manage/users?include_deleted=true
```

或仅查看已删除：

```
GET /manage/users?deleted_only=true
```

### 5.3 实现方案

修改 `QueryService.build_query()`:

```python
def build_query(self, meta_obj, filters=None, include_deleted=False, deleted_only=False):
    query = base_query
    
    if meta_obj.has_soft_delete():
        if deleted_only:
            query = query.where(meta_obj.deleted_at_field.is_not(None))
        elif not include_deleted:
            query = query.where(meta_obj.deleted_at_field.is_(None))
    
    return query
```

---

## 6. 级联软删除

### 6.1 场景

删除父对象时，子对象也应标记删除：

```
用户删除 → user_roles 删除
        → user_group_members 删除
        → change_subscriptions 删除
```

### 6.2 配置

```yaml
deletion_policy:
  soft_delete:
    enabled: true
    field: deleted_at
    cascade_to:
      - table: user_roles
        foreign_key: user_id
      - table: user_group_members
        foreign_key: user_id
```

### 6.3 实现

```python
def soft_delete_with_cascade(self, entity_type, entity_id, ...):
    with self.data_source.transaction():
        # 1. 标记主记录
        self._mark_deleted(table_name, entity_id, now, operator_id)
        
        # 2. 级联标记子记录
        for cascade in policy.soft_delete.cascade_to:
            self.data_source.execute(
                f"UPDATE {cascade.table} SET deleted_at = ?, deleted_by = ? WHERE {cascade.foreign_key} = ?",
                [now, operator_id, entity_id]
            )
```

---

## 7. 自动清理策略

### 7.1 配置

```yaml
deletion_policy:
  soft_delete:
    retention_days: 30  # 保留30天
    auto_cleanup: true  # 启用自动清理
    cleanup_schedule: "0 2 * * *"  # 每天凌晨2点
```

### 7.2 实现方案

**方案一：Cron 调度（推荐）**

参考现有 [backup-scheduler.sh](../../scripts/backup-scheduler.sh)，使用 cron 定时任务：

```bash
# /etc/cron.d/excel-to-diagram-cleanup
# 每天凌晨2点清理过期软删除记录
0 2 * * * root /opt/app/excel-to-diagram/scripts/cleanup-soft-deletes.py >> /opt/app/logs/cleanup.log 2>&1
```

**清理脚本**: `scripts/cleanup-soft-deletes.py`

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Soft Delete 自动清理脚本
定时清理过期的软删除记录
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timedelta
from meta.core.models import registry
from meta.core.data_source import get_data_source

def cleanup_expired_soft_deletes(dry_run=False):
    """清理过期的软删除记录"""
    data_source = get_data_source()
    stats = {'checked': 0, 'deleted': 0, 'errors': 0}
    
    for meta_obj in registry.get_all():
        policy = getattr(meta_obj, 'deletion_policy', None)
        if not policy:
            continue
        
        soft_delete = getattr(policy, 'soft_delete', None)
        if not soft_delete or not getattr(soft_delete, 'auto_cleanup', False):
            continue
        
        retention_days = getattr(soft_delete, 'retention_days', 30)
        deleted_at_field = getattr(soft_delete, 'field', 'deleted_at')
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        # 查找过期记录
        table_name = meta_obj.table_name
        query = f"SELECT id FROM {table_name} WHERE {deleted_at_field} < ?"
        cursor = data_source.execute(query, [cutoff_date.isoformat()])
        expired_ids = [row[0] if not isinstance(row, dict) else row['id'] for row in cursor.fetchall()]
        
        stats['checked'] += len(expired_ids)
        
        if not expired_ids:
            continue
        
        if dry_run:
            print(f"[DRY-RUN] Would delete {len(expired_ids)} expired {meta_obj.id} records")
            continue
        
        # 永久删除
        try:
            placeholders = ','.join(['?'] * len(expired_ids))
            data_source.execute(
                f"DELETE FROM {table_name} WHERE id IN ({placeholders})",
                expired_ids
            )
            stats['deleted'] += len(expired_ids)
            print(f"[OK] Deleted {len(expired_ids)} expired {meta_obj.id} records")
        except Exception as e:
            stats['errors'] += 1
            print(f"[ERROR] Failed to delete {meta_obj.id}: {e}")
    
    return stats

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Cleanup expired soft-deleted records')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be deleted without actually deleting')
    args = parser.parse_args()
    
    print(f"Starting soft delete cleanup at {datetime.now()}")
    stats = cleanup_expired_soft_deletes(dry_run=args.dry_run)
    print(f"Completed: checked={stats['checked']}, deleted={stats['deleted']}, errors={stats['errors']}")
```

**方案二：数据库触发器（可选）**

对于 SQLite，可以使用触发器在插入时自动清理：

```sql
-- 创建触发器（示例）
CREATE TRIGGER cleanup_old_soft_deletes
AFTER UPDATE ON users
WHEN NEW.deleted_at IS NOT NULL
BEGIN
    DELETE FROM users 
    WHERE deleted_at < datetime('now', '-30 days');
END;
```

**注意**: 触发器方案性能较差，不推荐用于高并发场景。

### 7.3 调度安装

```bash
# 安装定时任务
cd /opt/app/excel-to-diagram/scripts
./cleanup-scheduler.sh install

# 查看状态
./cleanup-scheduler.sh status

# 移除定时任务
./cleanup-scheduler.sh remove
```

### 7.4 监控与告警

```python
# 在 cleanup-soft-deletes.py 中添加监控
def send_alert(stats):
    """发送清理统计告警"""
    if stats['errors'] > 0:
        # 发送错误告警
        pass
    if stats['deleted'] > 1000:
        # 发送大量删除告警
        pass
```

---

## 8. 前端集成

### 8.1 回收站页面

```
┌─────────────────────────────────────────────────────────────┐
│  回收站 - 用户                                              │
├─────────────────────────────────────────────────────────────┤
│  筛选: [删除时间] [删除人] [搜索]                            │
├─────────────────────────────────────────────────────────────┤
│  名称        删除时间        删除人    剩余天数    操作       │
│  ─────────────────────────────────────────────────────────  │
│  张三        2026-05-20     admin    28天       [恢复] [删除]│
│  李四        2026-05-15     admin    23天       [恢复] [删除]│
└─────────────────────────────────────────────────────────────┘
```

### 8.2 删除确认对话框

```
┌─────────────────────────────────────────┐
│  确认删除                                │
├─────────────────────────────────────────┤
│  删除后可在回收站恢复（保留30天）         │
│                                         │
│  [ ] 同时删除关联数据                    │
│      - 用户角色 (3条)                    │
│      - 用户组成员 (2条)                  │
│                                         │
│         [取消]  [确认删除]               │
└─────────────────────────────────────────┘
```

### 8.3 详情页已删除提示

```
┌─────────────────────────────────────────────────────────────┐
│  用户详情 - 张三                                            │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ ⚠️ 此记录已于 2026-05-20 被 admin 删除                 │  │
│  │                                    [恢复] [永久删除]  │  │
│  └───────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│  ...                                                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 9. 实施计划

### Phase 1: 核心增强（高优先级）✅ 已完成

| 任务 | 文件 | 说明 | 状态 |
|------|------|------|------|
| 查询过滤增强 | `query_service.py` | 自动过滤已删除记录 | ✅ 已完成 |
| 恢复 API | `manage_api.py` | `POST /<id>/restore` | ✅ 已完成 |
| 永久删除 API | `manage_api.py` | `DELETE /<id>?permanent=true` | ✅ 已完成 |
| 回收站 API | `manage_api.py` | `GET /trash` | ✅ 已完成 |
| 清理脚本 | `cleanup-soft-deletes.py` | 自动清理过期记录 | ✅ 已完成 |

**已实现文件清单**:

| 文件 | 类型 | 说明 |
|------|------|------|
| `meta/services/query_service.py` | 修改 | 新增 `_apply_soft_delete_filter` 方法，SearchRequest 新增 `include_deleted`/`deleted_only` 参数 |
| `meta/api/manage_api.py` | 修改 | 新增 `restore_record`、`list_trash` API，`delete_record` 支持 `permanent` 参数 |
| `scripts/cleanup-soft-deletes.py` | 新增 | 自动清理过期软删除记录脚本 |

### Phase 2: 级联与清理（中优先级）✅ 已完成

| 任务 | 文件 | 说明 | 状态 |
|------|------|------|------|
| 级联软删除 | `deletion_service.py` | cascade_to 配置支持 | ✅ 已完成 |
| YAML 配置解析 | `yaml_loader.py` | SoftDeleteRule 扩展 | ✅ 已完成 |
| 自动清理任务 | `cleanup-soft-deletes.py` | 定时清理过期记录 | ✅ 已完成 |

**已实现文件清单**:

| 文件 | 类型 | 说明 |
|------|------|------|
| `meta/services/deletion_service.py` | 修改 | 新增 `_execute_cascade_soft_delete` 方法 |
| `meta/core/yaml_loader.py` | 修改 | SoftDeleteRule 新增 `cascade_to`/`retention_days`/`auto_cleanup` 属性 |

### Phase 3: 前端集成（低优先级）

| 任务 | 文件 | 说明 |
|------|------|------|
| 回收站页面 | `TrashPage.vue` | 回收站视图 |
| 删除确认增强 | `DeleteConfirm.vue` | 级联删除选项 |
| 已删除提示 | `ObjectPage.vue` | 详情页提示 |

---

## 10. 测试用例

### 10.1 单元测试

```python
def test_soft_delete_marks_record():
    """测试软删除标记"""
    result = deletion_service.delete('user', 123)
    assert result['success']
    assert result['message'] == '已标记为删除'
    
    record = data_source.find_by_id('users', 123)
    assert record['deleted_at'] is not None
    assert record['deleted_by'] == current_user.id

def test_restore_deleted_record():
    """测试恢复"""
    deletion_service.delete('user', 123)
    result = deletion_service.restore('user', 123)
    assert result['success']
    
    record = data_source.find_by_id('users', 123)
    assert record['deleted_at'] is None

def test_query_excludes_deleted():
    """测试查询过滤"""
    deletion_service.delete('user', 123)
    
    results = query_service.list('user')
    assert all(r['deleted_at'] is None for r in results)

def test_cascade_soft_delete():
    """测试级联软删除"""
    deletion_service.delete('user', 123)
    
    roles = data_source.find_all('user_roles', user_id=123)
    assert all(r['deleted_at'] is not None for r in roles)
```

---

## 11. 存量对象采纳

### 11.1 建议启用对象

| 对象 | 理由 | 保留天数 | 级联删除 |
|------|------|----------|----------|
| user | 用户数据重要，误删需恢复 | 30 | user_roles, user_group_members |
| role | 角色权限配置重要 | 30 | user_roles |
| domain | 领域结构重要 | 60 | sub_domains |
| sub_domain | 子领域结构重要 | 60 | service_modules |
| service_module | 服务模块结构重要 | 60 | business_objects |
| business_object | 业务对象核心实体 | 90 | - |
| product | 产品线重要 | 90 | versions |
| version | 版本历史需保留 | 180 | domains |

### 11.2 层级对象分析（sub_domain / service_module / business_object）

**适用性分析**:

| 对象 | 层级 | 子对象 | 删除条件 | Soft Delete 适用性 |
|------|------|--------|----------|-------------------|
| sub_domain | 4 | service_module | child_count=0 AND relation_count=0 | ✅ **适合** - 层级结构重要，误删需恢复 |
| service_module | 5 | business_object | child_count=0 AND relation_count=0 | ✅ **适合** - 服务模块重要，误删需恢复 |
| business_object | 6 | - | relation_count=0 | ✅ **适合** - 核心实体，关系重要 |
| relationship | 7 | - | true（可随时删除） | ⚠️ **可选** - 关系可重建，但保留有审计价值 |

**推荐方案**:

1. **sub_domain / service_module / business_object** - **强烈建议启用**
   - 层级结构是核心资产，误删影响大
   - 已有 deletability 条件校验，Soft Delete 作为额外保护
   - 级联软删除：父对象删除时自动标记子对象

2. **relationship** - **建议启用**
   - 虽然可随时删除，但保留有审计价值
   - 支持分析删除趋势和模式
   - 恢复后可重建对象间关系

**级联软删除配置示例**:

```yaml
# sub_domain.yaml
deletion_policy:
  soft_delete:
    enabled: true
    field: deleted_at
    deleted_by_field: deleted_by
    retention_days: 60
    cascade_to:
      - table: service_modules
        foreign_key: sub_domain_id
    exclude_from_query: true

# service_module.yaml
deletion_policy:
  soft_delete:
    enabled: true
    field: deleted_at
    deleted_by_field: deleted_by
    retention_days: 60
    cascade_to:
      - table: business_objects
        foreign_key: service_module_id
    exclude_from_query: true

# business_object.yaml
deletion_policy:
  soft_delete:
    enabled: true
    field: deleted_at
    deleted_by_field: deleted_by
    retention_days: 90
    exclude_from_query: true

# relationship.yaml
deletion_policy:
  soft_delete:
    enabled: true
    field: deleted_at
    deleted_by_field: deleted_by
    retention_days: 30
    exclude_from_query: true
```

### 11.3 不建议启用对象

| 对象 | 理由 |
|------|------|
| audit_log | 审计日志不应删除，需完整保留 |
| change_event | 事件记录需完整保留，用于追溯 |
| user_session | 会话数据无需保留，直接物理删除 |
| enum_value | 枚举值被引用，删除应通过引用检查 |

---

## 12. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 查询性能下降 | 软删除字段索引 | 为 deleted_at 创建索引 |
| 存储空间增长 | 定期清理 | 自动清理策略 |
| 级联删除复杂度 | 事务管理 | 使用数据库事务 |
| 恢复冲突 | 唯一约束冲突 | 恢复前检查约束 |

---

> **下一步**: 确认方案后开始实施 Phase 1

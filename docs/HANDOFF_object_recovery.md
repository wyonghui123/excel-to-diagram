# [ARCHIVED] HANDOVER: 基于 audit_logs 的对象恢复框架 (L13)

> **归档日期**: 2026-07-14 | **取代文档**: [INCIDENT_RESPONSE_RUNBOOK.md](INCIDENT_RESPONSE_RUNBOOK.md) 事故 1
> 本文档内容已整合到事故响应手册，不再单独维护。

> **作者**: 协调智能体 (基础设施深度分析)
> **创建日期**: 2026-07-13
> **接手智能体**: 开发智能体
> **关联 commit**: 2a545a2 (release/pre-2026-06-29)
> **验证快照**: AM-ROLE 角色 (id=1201) 删除事件

---

## 一、任务背景 (TL;DR)

**生产事故**: 用户测试删除 `角色权限` 的 `角色ID 1201` (AM-ROLE 资产云编辑)，删除失败提示 "角色权限 的 角色ID 引用了此记录 (28 条)"，**级联删除不生效**。

**已修复**: 角色级联删除功能 (BUG-V061, commit `81ca348`)，AM-ROLE 已从 backup 恢复。

**本任务目标**: **基于现有 audit_logs 实现通用的"对象恢复"框架**，避免未来类似误删需要手工 SQL 恢复。

---

## 二、核心发现 (基于实测, 2026-07-13 16:35)

### 2.1 audit_logs 已经是事实上的"软删除快照表"

| 维度 | 数据完整性 | 实测证据 |
|------|-----------|---------|
| **主实体 DELETE** | ✅ 100% 完整 | `extra_data.deleted_data` 包含所有字段 (id/code/name/...) |
| **DISSOCIATE 关联表 (permissions)** | ⚠️ 26/28 (93%) | 缺 2 条 role_permissions 关联 |
| **DISSOCIATE 关联表 (menus)** | ❌ 0% | `role_menu_permissions` 删除无 DISSOCIATE 审计 |
| **DISSOCIATE 关联表 (dim_scopes)** | ❌ 0% | `role_dimension_scopes` 删除无 DISSOCIATE 审计 |
| **DISSOCIATE extra_data** | ✅ 100% | 包含 `through_table` + `fk_column` + `cascade_reason` |
| **DISSOCIATE old_value** | ✅ 100% | `{"target_type": "...", "target_id": N}` |
| **retention_until** | ✅ 1 年 | `2027-07-13` (自动) |

### 2.2 实测验证 (AM-ROLE id=1201 删除链)

```
11:56:01 #179540-179565  26 条 DISSOCIATE permissions (cascade 删除 role_permissions)
11:56:01 #179566         DELETE _record (role 1201 完整快照)
12:01:03 #179567         DELETE _record (角色被 AI 重新测试删除, 快照可恢复)
```

主实体恢复数据 (`#179566` extra_data.deleted_data)：
```json
{
  "id": 1201,
  "code": "AM-ROLE",
  "name": "资产云编辑",
  "description": "资产云编辑",
  "is_active": 1,
  "is_system": 0,
  "created_at": "2026-07-12T21:13:33.503082",
  "created_by": "",
  "updated_by": "",
  "menu_count": null,         // 动态计算列, 恢复时 null
  "permission_count": null,   // 同上
  ...
}
```

### 2.3 推荐方案对比

| 方案 | 工作量 | 准确性 | 风险 | 推荐度 |
|------|--------|--------|------|--------|
| **A. 基于 audit_logs 恢复** | 2d | 95%+ (4 个缺口需补) | 低 | ⭐⭐⭐⭐⭐ |
| B. 整库 backup 恢复 | 0.5d | 100% | 高 (覆盖其他变更) | ⭐⭐ |
| C. SQL WAL 解析 | 3d | 99% | 中 | ⭐⭐ |
| D. 数据库触发器 | 1d | 100% | 中 (性能) | ⭐⭐⭐ |
| E. 软删除 (deleted_at) | 1d | 100% | 高 (迁移) | ⭐ |

---

## 三、任务拆解 (建议)

### 阶段 1: 补全 audit 缺口 (0.5d) — P0

**目标**: 把 4 个 audit 缺口补全到 100% 覆盖

**位置**: `meta/core/action_executor.py`

**修改点**:
1. `_cascade_pre_delete_role` (BUG-V061 修复处, 已有) → 已审计 role_permissions 26/28
2. 新增: `log_dissociate_menu(role_id, menu_id, table='role_menu_permissions')` 调用
3. 新增: `log_dissociate_dim_scope(role_id, scope_id, table='role_dimension_scopes')` 调用
4. 调查 role_permissions 缺 2/28 的原因（可能 cascade 循环或事务回滚）
5. 同样检查 `user_group_members` (可能也有缺口)

**验证**:
```python
# 测试 1: 删除一个测试 role, 验证 audit_logs 行数 == 实际级联行数
# 测试 2: audit_coverage_check.py (自动覆盖率检测)
```

### 阶段 2: 通用恢复框架 (1d) — P0

**位置**: **新文件** `/opt/app/shared/audit_recovery.py` (不放在 core_service, 违反 4 问铁律)

**核心 API**:
```python
class AuditRecovery:
    def find_recoverable(object_type: str, object_id: int) -> dict:
        """从 audit_logs 收集可恢复信息"""
        return {
            'main_record': {...},        # deleted_data 完整快照
            'relations': [...],          # DISSOCIATE 列表
            'audit_log_ids': [...],      # 涉及的审计 ID
            'warnings': [...],           # 缺失的审计
            'confidence': 0.95,          # 0-1
        }
    
    def preview(object_type: str, object_id: int) -> list[str]:
        """生成预览 SQL 列表 (不执行)"""
        return [
            'INSERT INTO role (id, code, name, ...) VALUES (...);',
            'INSERT INTO role_permissions (role_id, permission_id) VALUES (1201, 16);',
            ...
        ]
    
    def restore(object_type: str, object_id: int, 
                dry_run: bool = True,
                skip_warnings: bool = False) -> dict:
        """执行恢复 (dry_run 默认 True)"""
        return {
            'success': True,
            'restored': 27,             # 实际恢复行数
            'skipped': 1,               # 跳过的警告
            'sql_executed': [...],
        }
```

**位置选择**:
- ✅ 放在 `/opt/app/shared/audit_recovery.py` (运维工具, 9206 health_supervisor 之类)
- ❌ 不放在 core_service.py (会突破 500 行, 违反 4 问)
- ❌ 不放在 dbops_service.py (9204, 职责是 DB ops, 不含恢复)

### 阶段 3: HTTP API 集成 (0.5d) — P0

**位置**: 集成到 dbops_service (9204) 或新建 audit_recovery_service

**API**:
```
GET  /api/audit/find?object_type=role&object_id=1201
     → 返回 find_recoverable() 结果

POST /api/audit/preview
     body: {"object_type": "role", "object_id": 1201}
     → 返回 SQL 列表

POST /api/audit/restore
     body: {"object_type": "role", "object_id": 1201, "dry_run": true, "skip_warnings": false}
     → 返回执行结果
```

**Token**: write+admin 级别 (危险操作)

### 阶段 4: admin UI (可选, 1d) — P2

在 admin 前端加"审计恢复"页面, 用户可以选择 audit_log_id 后预览 + 执行

---

## 四、关键文件路径

| 文件 | 路径 | 当前状态 |
|------|------|---------|
| audit_logs 表 | `/opt/app/deployments/meta/architecture.db` → `audit_logs` | ✅ 已有, 117K 行 |
| AuditLogger | `meta/core/action_executor.py:170-360` | ✅ 已有 |
| 角色级联删除 | `meta/core/action_executor.py:_cascade_pre_delete_role` | ✅ 已有 (BUG-V061) |
| dbops_service | `/opt/app/shared/dbops_service.py` | ✅ 9204, 可扩展 |

---

## 五、参考 SQL (接手智能体可复用)

### 5.1 查询可恢复的主实体

```sql
SELECT id, object_type, object_id, action, extra_data, user_name, created_at
FROM audit_logs
WHERE action = 'DELETE' 
  AND field_name = '_record'
  AND object_type = 'role'
  AND object_id = 1201
  AND created_at > datetime('now', '-1 year')  -- 在 retention 内
ORDER BY id DESC LIMIT 1;
```

### 5.2 查询级联关联表

```sql
SELECT id, old_value, extra_data
FROM audit_logs
WHERE action = 'DISSOCIATE'
  AND object_type = 'role'
  AND object_id = 1201
  AND json_extract(extra_data, '$.cascade_reason') LIKE '%role#1201 deletion%';
```

### 5.3 提取完整快照

```python
import json
log = json.loads(audit_log_row['extra_data'])
deleted_data = log.get('deleted_data', {})
# deleted_data 含所有字段, 可直接 INSERT 回主表
```

### 5.4 还原关联表 (Python)

```python
for dissociate_log in dissociate_logs:
    old_value = json.loads(dissociate_log['old_value'])
    extra = json.loads(dissociate_log['extra_data'])
    target_type = old_value['target_type']
    target_id = old_value['target_id']
    through_table = extra['through_table']
    fk_column = extra['fk_column']
    # INSERT INTO through_table (fk_column, target_pk) VALUES (object_id, target_id)
```

---

## 六、测试用例 (接手智能体必跑)

### 6.1 阶段 1 测试 (audit 补全)

```python
def test_role_delete_full_cascade_audit():
    """删除一个测试 role, 验证 audit_logs 完整覆盖所有关联表"""
    # 1. 创建测试 role + 关联 (permissions, menus, dim_scopes)
    test_role = create_test_role(name='TEST_CASCADE_001')
    perm_ids = [1, 2, 3, 4, 5]
    menu_ids = [10, 20, 30]
    scope_ids = [100, 200]
    
    # 2. 关联
    for pid in perm_ids: associate_role_permission(test_role.id, pid)
    for mid in menu_ids: associate_role_menu(test_role.id, mid)
    for sid in scope_ids: associate_role_dim_scope(test_role.id, sid)
    
    # 3. 删除
    delete_role(test_role.id)
    
    # 4. 验证 audit_logs
    cascade_logs = query_audit_logs(
        object_type='role', 
        object_id=test_role.id, 
        action='DISSOCIATE'
    )
    
    assert len(cascade_logs) == len(perm_ids) + len(menu_ids) + len(scope_ids), \
        f"audit gap: {len(cascade_logs)} != {len(perm_ids) + len(menu_ids) + len(scope_ids)}"
```

### 6.2 阶段 2 测试 (恢复框架)

```python
def test_restore_role_end_to_end():
    """端到端: 删除 + 恢复"""
    # 1. 创建 + 删除
    test_role = create_test_role(name='TEST_RESTORE_001')
    perm_ids = [1, 2, 3]
    for pid in perm_ids: associate_role_permission(test_role.id, pid)
    delete_role(test_role.id)
    
    # 2. 恢复 (dry_run)
    result = AuditRecovery().restore('role', test_role.id, dry_run=True)
    assert result['success'] == True
    
    # 3. 实际恢复
    result = AuditRecovery().restore('role', test_role.id, dry_run=False)
    assert result['restored'] >= 1  # 至少主实体
    
    # 4. 验证 role 重新存在
    assert get_role(test_role.id) is not None
    assert get_role(test_role.id).code == 'TEST_RESTORE_001'
```

---

## 七、风险与限制 (接手智能体必读)

### 7.1 已知限制

1. **仅恢复单层** — 不会递归恢复 (例如恢复 role 不会恢复其关联的 permission)
2. **不处理硬删除** — 物理 DROP TABLE / TRUNCATE 无解
3. **retention 限制** — 1 年, 超过 retention_until 的不可恢复
4. **race condition** — 恢复期间其他事务可能 INSERT 新数据, 需事务隔离
5. **敏感数据** — `deleted_data` 含 password/email, 恢复时需脱敏

### 7.2 风险点

1. **PII 泄露** — `deleted_data` 是完整快照, 含用户隐私, 需 access control
2. **数据一致性** — 恢复可能违反当前业务规则 (例如原 email 已注册新用户)
3. **审计链** — 恢复操作本身必须写 audit_log (`action=RESTORE`)
4. **回滚自身** — 恢复失败时如何回滚? 需要 dry_run + 事务包装

### 7.3 推荐实施步骤

1. 先做 audit 缺口补全 (阶段 1) — 0.5d
2. 写 audit_recovery.py 核心类 (阶段 2) — 1d, 写完整单元测试
3. HTTP API (阶段 3) — 0.5d, 注意 token 权限
4. (可选) admin UI (阶段 4) — 1d

---

## 八、关联 TODO (L8-L14 更新)

| ID | 主题 | 状态 | 关联本任务 |
|----|------|------|-----------|
| L8 | 上传契约 | ✅ 部分完成 | - |
| L9 | rebuild_zip ROOT + meta 同步 | ✅ 完成 | - |
| L10 | post_deploy_check 三层对账 | ✅ 完成 | - |
| **L11.3** | 危险操作二次确认 (DELETE) | ❌ TODO | **建议结合本任务, 恢复前强制 confirm** |
| **L12.1** | SSH 根因 | ❌ TODO | - |
| **L13** | 基于 audit_logs 通用恢复 | ❌ TODO | **= 本任务** |
| L14 | deploy_service 新建 | ❌ TODO | 阶段 3 可用 deploy_service 而非 dbops |

---

## 九、接手检查清单 (开发智能体)

接手后请按顺序完成:

- [ ] 读 `meta/core/action_executor.py:170-360` (AuditLogger)
- [ ] 读 `meta/core/action_executor.py` 中 `_cascade_pre_delete_role` 全文
- [ ] 跑阶段 1 测试 (6.1), 确认 audit 缺口位置
- [ ] 修复 audit 缺口 (0.5d)
- [ ] 创建 `audit_recovery.py` (1d)
- [ ] HTTP API 集成到 dbops_service (0.5d)
- [ ] 端到端测试 (6.2) PASS
- [ ] 部署到生产 (用 raw body 上传, 不要 multipart!)
- [ ] 实战验证: 找一个测试实体, 删除 + 恢复 + 验证

---

## 十、紧急联系电话 (出问题)

- 协调智能体 (本文档作者) 留下: TODO_LONGTERM.md CHANGELOG
- 生产监控: `monitor_prod.py` (8 项检查)
- 备份目录: `/opt/app/backups/`
- 数据库: `/opt/app/deployments/meta/architecture.db`

---

**CHANGELOG**:

| 日期 | 变更人 | 变更内容 |
|------|--------|----------|
| 2026-07-13 16:35 | 协调智能体 | 初版, 基于 AM-ROLE 删除事件复盘 + audit_logs 实测 |

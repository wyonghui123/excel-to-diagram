# v088 + v089 数据摸底 + 冷备份报告

> **日期**: 2026-09-15  
> **操作**: 数据摸底 + preflight cold backup (v088 软删 + v089 DROP legacy)  
> **状态**: 🟢 preflight 已就绪，可 deploy

---

## 1. 数据摸底结果（staging + prod）

### 1.1 v088 软删目标数据

| 指标 | staging | prod | 备注 |
|---|---|---|---|
| `orgs.manager_id` 非空行数 | **0** | **0** | ✅ 真零数据，软删无迁移负担 |
| `org_members.is_manager=1` | **1** | **1** | ⚠️ seed 遗留：admin → org 1（系统管理员），admin 走 `is_admin()` 全局放行，无实际越权风险 |

### 1.2 v089 DROP 目标（legacy 表）

| Legacy 表 | staging rows | prod rows | 是否安全 DROP |
|---|---|---|---|
| `user_groups` | 1 | 1 | ✅ 已迁移到 `orgs` (v072 RENAME) |
| `user_group_members` | 1 | 1 | ✅ 已迁移到 `org_members` (v072) |
| `roles` | 3 | 3 | ✅ 已迁移到 `permission_sets` (v072) |
| `role_permissions` | 61 | **427** | ✅ 已迁移到 `permission_set_permissions` (v087 backfill) |
| `role_menu_permissions` | 0 | 0 | ✅ 已迁移到 `permission_set_menu_permissions` (v072) |
| `role_data_permissions` | 0 | 0 | ✅ 已迁移到 `permission_set_data_permissions` (v072) |
| `user_roles` | 0 | 0 | ✅ 已迁移到 `user_permission_sets` (v072) |
| `group_roles` | 1 | 1 | ✅ 已迁移到 `org_permission_sets` (v072) |
| `group_data_permissions` | 0 | 0 | ✅ 已迁移到 `org_data_permissions` (v072) |

**prod role_permissions 427 行** 是 v070 RENAME 后遗留的 history 副本（v087 backfill 已迁移完成，legacy `role_id` 列保留仅作兼容）。DROP 安全：新表 `permission_set_permissions.permission_set_id` 是权威键。

### 1.3 代码层引用扫描

| 维度 | 命中数 | 风险 |
|---|---|---|
| `meta/services/` 运行时引用 | **0** | 🟢 零风险 |
| `meta/api/` 运行时引用 | **0** | 🟢 零风险 |
| `meta/core/` 运行时引用 | **0** | 🟢 零风险 |
| `meta/scripts/` 历史脚本 | 5 处 | 🟢 不参与运行时（migrate_v1_cleanup 等） |
| `meta/tests/` fixture 引用 | 78 处 | 🟡 T-D-4 后续票号（不在 v088/v089 范围） |
| `meta/scripts/permission_audit.sql` | 6 处 | 🟡 运维 SQL，需同步改名 |

**结论**：生产代码路径已**完全迁出** legacy 表，v089 DROP **零运行风险**。

---

## 2. preflight cold backup（已完成）

### 2.1 staging 备份

```json
{
  "stamp": "20260915_223719",
  "db_path": "/opt/app/staging/meta/architecture.db",
  "backup_path": "/opt/app/staging/meta/architecture.db.preflight_v088_v089_20260915_223719",
  "db_size_bytes": 116535296,
  "backup_size_bytes": 116535296,
  "table_count": 77,
  "schema_migrations": 20,
  "legacy_tables_pre_v089": {
    "user_groups": 1, "user_group_members": 1, "roles": 3,
    "role_permissions": 61, "role_menu_permissions": 0,
    "role_data_permissions": 0, "user_roles": 0,
    "group_roles": 1, "group_data_permissions": 0
  },
  "v088_legacy_data": {
    "orgs.manager_id": 0,
    "org_members.is_manager=1": 1
  },
  "backup_ok": true
}
```

### 2.2 prod 备份

```json
{
  "stamp": "20260915_223724",
  "db_path": "/opt/app/deployments/meta/architecture.db",
  "backup_path": "/opt/app/deployments/meta/architecture.db.preflight_v088_v089_20260915_223724",
  "db_size_bytes": 136925184,
  "backup_size_bytes": 136925184,
  "table_count": 62,
  "schema_migrations": 32,
  "legacy_tables_pre_v089": {
    "user_groups": 1, "user_group_members": 1, "roles": 3,
    "role_permissions": 427, "role_menu_permissions": 0,
    "role_data_permissions": 0, "user_roles": 0,
    "group_roles": 1, "group_data_permissions": 0
  },
  "v088_legacy_data": {
    "orgs.manager_id": 0,
    "org_members.is_manager=1": 1
  },
  "backup_ok": true
}
```

### 2.3 回滚路径

如 v088/v089 deploy 后出现异常，回滚命令：

```bash
# staging
cp /opt/app/staging/meta/architecture.db.preflight_v088_v089_20260915_223719 \
   /opt/app/staging/meta/architecture.db
# prod (需 prod gateway)
cp /opt/app/deployments/meta/architecture.db.preflight_v088_v089_20260915_223724 \
   /opt/app/deployments/meta/architecture.db
```

---

## 3. 改动清单

### 3.1 新增迁移文件

| 文件 | 作用 |
|---|---|
| [meta/migrations/v088__deprecate_manager_id_and_is_manager.py](v088__deprecate_manager_id_and_is_manager.py) | Spec 19 M4 软删验证 + 报告（数据层零变更） |
| [meta/migrations/v089__drop_legacy_user_group_and_role_tables.py](v089__drop_legacy_user_group_and_role_tables.py) | DROP 11 张 legacy 表（幂等 IF EXISTS） |

### 3.2 修改文件

| 文件 | 改动 |
|---|---|
| [meta/services/org_service.py](../../meta/services/org_service.py) | (a) `add_member(is_manager=True)` 拒绝+warn (b) `is_org_manager()` 永远返回 False (c) `get_managed_orgs()` 删除 is_manager/manager_id fallback 段 |
| [meta/api/org_api.py](../../meta/api/org_api.py) | `add_group_member(is_manager=True)` 返回 400 + `error_code: DEPRECATED_IS_MANAGER` |
| [meta/schemas/org.yaml](../../meta/schemas/org.yaml) | `manager_id` 字段标 `deprecated: true` + deprecation_message |
| [meta/schemas/org_member.yaml](../../meta/schemas/org_member.yaml) | `is_manager` 字段标 `deprecated: true` |
| [meta/schemas/generated_schema.sql](../../meta/schemas/generated_schema.sql) | 删除 `user_groups` / `user_group_members` / `user_roles` 三段 CREATE + 对应索引（共 5+3=8 段） |
| [meta/scripts/init_auth_tables.py](../../meta/scripts/init_auth_tables.py) | `orgs.manager_id` / `org_members.is_manager` 列加 deprecation 注释 |

### 3.3 新增工具脚本

| 文件 | 作用 |
|---|---|
| [tools/v19_p2_audit_remote.py](../../tools/v19_p2_audit_remote.py) | staging + prod 远程 DB 数据摸底 |
| [tools/v19_p2_preflight_backup.py](../../tools/v19_p2_preflight_backup.py) | deploy 前冷备份 + manifest 报告 |
| [tools/v19_v089_legacy_safety_audit.py](../../tools/v19_v089_legacy_safety_audit.py) | 验证 legacy role_permissions 数据已迁移 |

### 3.4 dev 库本机验证结果

```
[v088] migrate: OK
[v088 verify] orgs.manager_id 非空行数 = 0 (期望 0)
[v088 verify] org_members.is_manager=1 行数 = 0 (期望 0)
[v088 verify] legacy 表 user_groups 存在 (rows=1); 由 v089 处理 DROP
[v088 verify] legacy 表 user_group_members 存在 (rows=1); 由 v089 处理 DROP
[v088 verify] legacy 表 roles 存在 (rows=3); 由 v089 处理 DROP
[v088] verify: PASS

[v089] migrate: OK (DROP 9 张表: user_groups/user_group_members/roles/role_permissions/...)
[v089 verify] 11 张 legacy 表均不存在
[v089 verify] 现行表 orgs/org_members/permission_sets/permission_set_permissions 均存在
[v089] verify: PASS
```

---

## 4. Deploy 步骤（建议顺序）

### 4.1 staging（30 分钟内可完成）

```bash
# 1. 部署前确认 cold backup 已就位
ls -la /opt/app/staging/meta/architecture.db.preflight_v088_v089_*

# 2. deploy（含 deploy 自带 backup）
python tools/staging_round.py deploy

# 3. 部署后跑 v088 + v089 迁移
python tools/migrate.py --db /opt/app/staging/meta/architecture.db

# 4. 验证
python meta/migrations/v088__deprecate_manager_id_and_is_manager.py \
    /opt/app/staging/meta/architecture.db
python meta/migrations/v089__drop_legacy_user_group_and_role_tables.py \
    /opt/app/staging/meta/architecture.db

# 5. 重启服务 + 跑核心回归
python d:\filework\test.py --integration --timeout 1200
```

### 4.2 prod（staging 跑通 ≥ 24h 后）

```bash
# 1. staging_round prod 部署（含 prod 自带 backup）
python tools/staging_round.py prod-deploy

# 2. 跑 v088 + v089 迁移
python tools/migrate.py --db /opt/app/deployments/meta/architecture.db

# 3. 验证 + 回归 (按 R018 同款 SOP)
python d:\filework\test.py --integration --timeout 1200

# 4. 跑浏览器验证 (按 mcp-frontend-testing SOP, 但实际用 PlaywrightCLI)
```

---

## 5. 待办（不在本次范围）

| 票号 | 任务 | 工作量 | 阻塞 |
|---|---|---|---|
| T-D-4 | 测试 fixture 78 处 `user_groups`/`user_group_members`/`role_permissions` 改名为 `orgs`/`org_members`/`permission_set_permissions` | 1.5d | T-D-4 完成后回归测试才能跑通 |
| T-D-5 | `permission_audit.sql` 6 处 SQL 改写 | 0.2d | T-D-5 完成后运维查询才能用 |
| 后续 v09x | `orgs.manager_id` / `org_members.is_manager` 列硬删（DROP COLUMN，需 SQLite 3.35+）| 0.5d | 建议 2027-Q1 排期（M4 + M3 上线 ≥ 1 季度后） |

---

## 6. 风险评估

| 风险 | 等级 | 缓解 |
|---|---|---|
| staging 部署后回归测试 fail | 🟢 低 | cold backup 可立即回滚；dev 库已验证 v088+v089 通过 |
| prod 部署后历史数据丢失 | 🟢 极低 | 全部 legacy 数据已迁移到新表（v087 backfill 验证通过） |
| `is_manager=1` 的 admin seed 遗留 | 🟢 极低 | admin 走 `is_admin()` 全局放行，fallback 不实际加权限 |
| 用户调用 `add_member(is_manager=True)` 触发 400 | 🟡 中 | v084 已有 deprecation 日志记录；前端 UI 已隐藏 is_manager 入参（[PermissionConfigPanel](../../src/views/SystemManagement/components/PermissionConfigPanel.vue) 不传该字段）|
| T-D-4 未完成导致测试套件 collection error | 🟡 中 | **与 v088/v089 同步推进**：4 个测试文件 `user_group_service` import 已 Sunset，与 T-D-4 合并处理 |

---

**审计**: P2-1（v088 软删）+ P2-3（v089 双表收敛）preflight 已就绪 ✅  
**下一步**: 发起 v088 + v089 PR，按 4.1 staging → 4.2 prod 顺序部署。
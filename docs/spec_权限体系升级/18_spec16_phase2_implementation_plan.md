# Spec16 Phase 2 实施计划（一次性合并方案 B）

> 文档编号: 18 | 状态: 实施稿（用户已确认方案 B） | 更新: 2026-08-30
> 主题: Spec16 Phase 2 后端 56 文件改造 + Feature Flag + DB 迁移的合并实施
> 前置: [Spec16 §3.2/§3.3 影响面清单](./16_role_to_permission_set_and_user_group_to_org.md), [本次会话总结 worktree 4fc6130+15654ec](README.md)
> 范围: 后端改造 + Flag 接入 + DB 迁移执行 + 验证 + 跨轮边界

---

## TL;DR

| 项目 | 内容 |
|------|------|
| **方案** | B - 代码迁移与 DB 迁移一次性合并 |
| **Phase 2 工作量** | 56~80 后端文件、6 个 schema yaml、6 张表的所有引用改造；预计 200+ 处改动点 |
| **本日交付边界** | 子集 A（Flag + init_auth_tables 双轨）+ Plan 文档；其余越轮 |
| **跨轮边界** | 按 4 个 Plan 拆分子集，每个子集 1~2 轮会话可完成 |
| **下一步** | 用户审阅本计划 → 决定是否启动 Plan-1（核心服务/拦截器代码迁移） |

---

## 1. 已完成（本次会话）

### 1.1 工作树提交（在途）
| Commit | 内容 | 状态 |
|--------|------|------|
| `4fc6130` | fix(audit) materialization_registry 判空 + audit_api 别名归一化 + _audit_materialization 注册 orgs | 已推送 |
| `15654ec` | feat(perm) 权限预览优化 21 文件 | 已推送 |
| `1f8350c` | feat(org) 组织管理页 MOMP + org-management 菜单 + Spec17 | 已推送 |
| `ed8e799` | fix(migrations) Spec16 迁移脚本 runner 兼容 + 测试 fresh_db 隔离 + .gitignore snapshot | 已推送 |

### 1.2 本日新增代码改动（未提交）
| 文件 | 改动 | 验证 |
|------|------|------|
| `meta/core/permission_flags.py` | 新增 `permission_set_refactor_enabled` flag（默认 True） | 仅声明，未接入调用方 |
| `meta/scripts/init_auth_tables.py` | 同时支持旧名 + 新名（_table_exists 双轨 helper），索引/触发器/admin 用户初始化都双轨 | fresh_db + 模拟已迁 DB 双场景 PASS |

### 1.3 本日新增文档（未提交）
- `docs/spec_权限体系升级/18_spec16_phase2_implementation_plan.md`（本文档）

---

## 2. 完整改名映射表（56~80 文件）

### 2.1 DB 层（已完成）
| 旧表 | 新表 | 状态 |
|------|------|------|
| `roles` | `permission_sets` | 迁移脚本已就绪 |
| `role_permissions` | `permission_set_permissions` | 迁移脚本已就绪 |
| `role_data_permissions` | `permission_set_data_permissions` | 迁移脚本已就绪 |
| `role_dimension_scopes` | `permission_set_dimension_scopes` | 迁移脚本已就绪 |
| `role_menu_permissions` | `permission_set_menu_permissions` | 迁移脚本已就绪 |
| `user_roles` | `user_permission_sets` | 迁移脚本已就绪 |
| `user_groups` | `orgs` | 迁移脚本已就绪 |
| `user_group_members` | `org_members` | 迁移脚本已就绪 |
| `group_roles` | `org_permission_sets` | 迁移脚本已就绪 |
| `group_data_permissions` | `org_data_permissions` | 迁移脚本已就绪 |
| —（新增） | `org_functions` | 迁移脚本已就绪 |

### 2.2 Schema yaml（**未做**）
| 旧文件名 | 新文件名 |
|---------|---------|
| `meta/schemas/role.yaml` | `meta/schemas/permission_set.yaml` |
| `meta/schemas/role_permission.yaml` | `meta/schemas/permission_set_permission.yaml` |
| `meta/schemas/role_data_permission.yaml` | `meta/schemas/permission_set_data_permission.yaml` |
| `meta/schemas/role_dimension_scope.yaml` | `meta/schemas/permission_set_dimension_scope.yaml` |
| `meta/schemas/role_dimension_scopes.yaml` | `meta/schemas/permission_set_dimension_scopes.yaml` |
| `meta/schemas/role_effective_intents.yaml` | `meta/schemas/permission_set_effective_intents.yaml` |
| `meta/schemas/user_group.yaml` | `meta/schemas/org.yaml` |
| `meta/schemas/user_group_member.yaml` | `meta/schemas/org_member.yaml` |
| `meta/schemas/group_data_permission.yaml` | `meta/schemas/org_data_permission.yaml` |

### 2.3 后端 API 文件（**未做**）
| 旧名 | 新名 |
|------|------|
| `meta/api/role_api.py` | `meta/api/permission_set_api.py` |
| `meta/api/role_menu_api.py` | `meta/api/permission_set_menu_api.py` |
| `meta/api/role_dimension_scope_api.py` | `meta/api/permission_set_dimension_scope_api.py` |
| `meta/api/user_group_api.py` | `meta/api/org_api.py` |

注：API 路径 `/{prefix}/{resource}` 同步改名（如 `/api/v1/roles` → `/api/v1/permission_sets`、`/api/v1/user_groups` → `/api/v1/orgs`）。

### 2.4 后端服务（**未做**）
| 旧名 | 新名 |
|------|------|
| `meta/services/user_group_service.py` | `meta/services/org_service.py` |
| `meta/services/role_consistency_audit.py` | `meta/services/permission_set_consistency_audit.py` |

注：`role_service.py` / `permission_set_service.py` 已并存（Phase 13 引入），需合并或保留 `permission_set_service.py` 作为唯一入口。

### 2.5 前端 API 路径（**未做**）
- `src/services/boService.js`、`src/api/*` 中所有 `/api/v1/roles` → `/api/v1/permission_sets`、`/api/v1/user_groups` → `/api/v1/orgs`、`/api/v1/role_menus` → `/api/v1/permission_set_menus` 等。
- `src/views/SystemManagement/RolePermissionCenter.vue`、`GroupRoleDialog.vue` 等组件改名（保留 alias shim 二期）。

### 2.6 文档/测试（**未做**）
- 测试文件 `test_role_*.py` → `test_permission_set_*.py`、`test_user_group_*.py` → `test_org_*.py`（保留旧名作为 alias runner）。
- 文档 i18n 文案「角色」→「权限集」、「用户组」→「组织」。
- audit_log 历史 `object_type` 字符串 `'role'`/`'user_group'` → `'permission_set'`/`'org'`（需要双 alias 兼容历史日志查询）。

---

## 3. Feature Flag 接入（**本日已完成声明，未接入调用方**）

```python
# meta/core/permission_flags.py
_FLAGS = {
    ...
    'permission_set_refactor_enabled': True,  # Spec16: 默认开启
}
```

**接入策略**（**未做**，留作 Plan-1）：

```python
# 模式 A: 数据库层 alias（推荐 - 影响面小）
def _ps_table():
    """permission_set 表名选择"""
    if is_enabled('permission_set_refactor_enabled'):
        return 'permission_sets'
    return 'roles'

# 模式 B: SQL 字符串替换（不推荐 - 性能差、风险大）
# 模式 C: 在每个 service 层加 if/else（不推荐 - 噪音大）
```

**推荐模式 A**：在 `meta/services/_table_alias.py`（新建）集中定义所有别名表/列名 helper，所有 service 引用 helper 而非硬编码表名。这样**关闭 flag 时服务代码不变**，仅表名指向旧名，**回滚成本极低**。

---

## 4. 4 个 Plan（按依赖顺序分批）

### Plan-1：核心 SQL 适配层（关键路径，1~2 轮会话）

**目标**：抽出所有表名/列名到 `_table_alias.py`，所有 service/API 改用 helper。

**范围**：~30 文件
- `meta/services/_table_alias.py`（**新建**，~200 行，集中定义所有 PS_ORG 表/列别名 + helper）
- `meta/services/user_group_service.py`、`permission_set_service.py`、`role_consistency_audit.py`
- `meta/services/data_permission_service.py`、`condition_permission_service.py`、`menu_permission_service.py`
- `meta/services/dimension_scope_engine.py`、`permission_dimension_engine.py`、`import_export_service.py`
- `meta/api/user_group_api.py`、`role_api.py`、`role_menu_api.py`、`role_dimension_scope_api.py`、`unified_permission_api.py`、`permission_dimension_api.py`、`intent_api.py`、`diagnostics_api.py`、`special_routes_api.py`
- `meta/api/bo_api.py`（核心 BO 端点）

**验证**：
- `pytest meta/tests/test_role_* meta/tests/test_user_group_* -x --tb=short`
- `pytest meta/tests/test_object_adaptation_user_group.py meta/tests/test_audit_role_parent_query_e2e.py`
- fresh_db 启动 server，验证 admin 登录 + 列表查询

**风险**：高（修改面最大）；需在最后做整轮回归。

### Plan-2：Schema yaml + regenerated_schema.sql（1 轮会话）

**目标**：6 个 schema yaml 改名 + 模型加载器路径更新 + schema.sql 重新生成。

**范围**：~10 文件
- `meta/schemas/role.yaml` → `meta/schemas/permission_set.yaml`（+5 个系列）
- `meta/schemas/user_group.yaml` → `meta/schemas/org.yaml`（+3 个系列）
- `meta/schemas/.schema_version.json` 更新
- `meta/schemas/index_generator.py`、`schema_loader.py`、`model_registry.py`
- `meta/schemas/generated_schema.sql` 重新生成

**验证**：
- `python -c "from meta.schemas.schema_loader import load_all; load_all()"` 不报错
- `meta/scripts/init_db.py --fresh` 在 fresh_db 上跑通
- 对比 generated_schema.sql 行数变化

**风险**：中（schema 文件独立，影响面集中）。

### Plan-3：拦截器 + 派生 + Intent 层（**关键**，1~2 轮会话）

**目标**：`write_scope_interceptor.py`、`data_permission_interceptor.py`、`derivation_pipeline.py`、`effective_intent_dao.py`、`intent_resolver.py`、`intent_scope_adapter.py`、`runtime_dimension_resolver.py`、`permission_benchmark_suite.py` 全部改用 helper。

**范围**：~10 文件

**验证**：
- `pytest meta/tests/test_write_scope_phase2_hook.py meta/tests/test_interceptor_phase2_hook.py meta/tests/test_interceptors_unit.py meta/tests/test_intent_api.py meta/tests/test_condition_permission_service.py`
- e2e：`meta/tests/test_association_audit_e2e.py`、`test_audit_role_parent_query_e2e.py`
- 业务路径：用户登录 → 创建 BO → 列表查询 → 权限拦截链路

**风险**：高（拦截器是请求路径，性能/正确性敏感）。

### Plan-4：前端 API + i18n + 组件（1~2 轮会话）

**目标**：所有 `/api/v1/roles` → `/api/v1/permission_sets`、`/api/v1/user_groups` → `/api/v1/orgs`。

**范围**：~15 文件
- `src/services/boService.js`、`src/services/autocrudService.js`、`src/api/*`
- `src/views/SystemManagement/RolePermissionCenter.vue` → `PermissionSetCenter.vue`（同时保留 alias 路由）
- `src/views/SystemManagement/GroupRoleDialog.vue` → `OrgPermissionSetDialog.vue`
- `src/composables/useMenuPermission.ts`、`usePermissionDimension*.ts`
- `src/utils/auditLogFormat.js`（object_type 别名映射）
- `src/views/SystemManagement/__tests__/*`

**验证**：
- `npm run build` 成功
- `npm run test:unit`（vitest）
- playwright e2e：admin 登录 → org-management 列表 → 详情 → 操作日志

---

## 5. DB 迁移执行窗口（关键决策点）

### 5.1 触发条件（**全部满足才执行**）
1. Plan-1/2/3/4 全部完成并合入 release/integrated-main
2. 全量回归测试通过（meta/tests/ + playwright e2e）
3. 用户确认迁移窗口与回滚预案
4. staging 服务器已部署最新代码（含 alias helper）

### 5.2 执行步骤（staging）
```bash
ssh root@172.20.59.7
cd /opt/app/staging/deploy/current

# 1. 备份当前 DB（_deploy_delta_staging.py 已自动备份，确认有 .bak）
ls -lt /opt/app/staging/deploy/current/meta/architecture.db.* | head -3

# 2. 跑 migration_runner
python -m meta.core.migration_runner --db-path meta/architecture.db
# 预期:
#   ✓ DROP permission_sets / permission_set_permissions / user_permission_sets (残留)
#   ✓ RENAME 6 张 role_* → permission_set_*
#   ✓ RENAME 4 张 user_group_* / group_* → org_*
#   ✓ ADD COLUMN org_type / org_scope
#   ✓ 创建 org_functions 表 + 默认数据

# 3. 重启 backend
systemctl restart excel-to-diagram-staging

# 4. 验证
curl -s http://172.20.59.7:13011/api/v1/auth/dev-login?username=admin
curl -s http://172.20.59.7:13011/api/v1/orgs?limit=5   # 新名应工作
curl -s http://172.20.59.7:13011/api/v1/permission_sets?limit=5  # 新名应工作
```

### 5.3 回滚（5 分钟内）
```bash
cp /opt/app/staging/deploy/current/meta/architecture.db.<TIMESTAMP>.bak \
   /opt/app/staging/deploy/current/meta/architecture.db
# 然后部署旧版本代码（HEAD~10）→ restart
# 注意：rollback 时不能保留新代码，否则 init_auth_tables 会用新表覆盖
```

### 5.4 双轨（Flag 关闭）的安全网
如果迁移后发现问题，可临时关 flag：
```bash
# 编辑 deploy 配置
PERMISSION_FLAG_PERMISSION_SET_REFACTOR_ENABLED=0
systemctl restart excel-to-diagram-staging
# 此时 service 走旧表（roles/user_groups），但 DB 已迁 → 旧表不存在 → 必须立即回滚 DB
```

⚠️ **因此 Flag 关闭不是替代回滚方案**——一旦 DB 迁移完成，关闭 flag = 立即 500，必须回滚 DB。

---

## 6. 风险与回滚总览

| 风险 | 等级 | 缓解 |
|------|------|------|
| Plan-1 SQL helper 漏改导致查询失败 | 高 | 单元测试覆盖 + e2e 业务路径 |
| Plan-2 schema 改名遗漏导致加载失败 | 中 | generated_schema.sql 对比 + 启动检查 |
| Plan-3 拦截器回归 | 高 | 旧 e2e test_interceptors_unit + test_write_scope_phase2_hook |
| Plan-4 前端 API 路径不一致 | 中 | playwright e2e 验证 |
| DB 迁移中途失败 | 中 | _deploy_delta_staging.py db_backup 自动备份 |
| DB 迁移后旧名缺失导致 INSERT/SELECT 失败 | 中 | init_auth_tables 已双轨兼容 |
| 用户登录失败（roles 表不存在） | 高 | DB 回滚 + 旧代码恢复 |

---

## 7. 今日交付确认

### 7.1 已 commit 但未推送（如用户授权）
- `meta/core/permission_flags.py`（flag 声明）
- `meta/scripts/init_auth_tables.py`（双轨兼容）
- 本文档

### 7.2 未 commit（越轮工作）
- Plan-1/2/3/4 全部代码改动
- DB 迁移执行（待 Plan 全完成后）

---

## 8. 下一步

1. **本会话末尾**：将 7.1 改动 commit + 推送 release/integrated-main。
2. **下轮会话**：按 Plan-1 启动核心服务迁移（如用户决策继续）。
3. **关键决策点**：DB 迁移窗口由用户决策。

---

## 9. 跨轮工作交接清单

每个新会话开始前请提供：

```
- 分支: release/integrated-main (HEAD)
- 当前 Plan 编号: Plan-X
- 已完成 commit: <hash list>
- 本轮目标: <Plan-X 子任务>
- 关联 spec: docs/spec_权限体系升级/18_spec16_phase2_implementation_plan.md
- 已知风险: <见 §6>
- 验收标准: <见 Plan-X §验证>
```

---

## 附录 A：本日已运行验证

### A.1 init_auth_tables 双轨兼容（PASS）
```
=== fresh_db (空) ===
12 张新表全建好，admin 写入新表
=== 模拟已迁 DB ===
原 permission_sets 不被覆盖，新表正确添加
```

### A.2 迁移脚本（已在 ed8e799 完成验证）
- 3 个 migrate() 函数 + prerequisites() 与 migration_runner 兼容
- 完整迁移链：3 DROP 残留 + 6 RENAME + 4 RENAME + 959 orgs 分类 + org_functions 建表

### A.3 Spec16 端到端测试（已在 ed8e799 完成）
- 单元测试 5/5 PASSED
- e2e 测试 5/5 PASSED（fresh_db 隔离）
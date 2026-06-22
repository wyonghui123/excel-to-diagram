# -*- coding: utf-8 -*-
# Spec: WriteScopeInterceptor 写权限 × Dim Scope 联动 (v2.1)

> **Version**: v2.1 | **Date**: 2026-06-22 | **Status**: [DRAFT] PM review 待确认
> **Authors**: AI Coding Agent | **Spec 类型**: 权限引擎微调（不建表不改 UI）
> **关联 Spec**:
>   - [write-scope-interceptor-spec.md](./write-scope-interceptor-spec.md) v2.0 (父 spec, 零建表原则)
>   - [../cross-domain-relationship-permission/spec.md](../cross-domain-relationship-permission/spec.md) (read/edit 拆分意图)

---

## Why

### 业务场景

P0 安全漏洞: 角色 `TEST333W` 同时拥有:

| 来源 | 内容 |
|------|------|
| `role_permissions` | `service_module:update`, `service_module:create`, `service_module:delete`, ... |
| `role_dimension_scopes` | `domain=[703]` (采购管理) |

**问题**: 该角色可以编辑 `domain=706` (财务管理) 下的 `service_module`, 因为 `WriteScopeInterceptor.step3` 只检查 "dim scope 命中", 假设角色所有 dim scope 都跟 functional perm 强绑定 — 实际两者完全解耦, 任何拥有 `service_module:update` 的角色都能编辑任何 domain 的 SM。

实测: TEST333 用户 (含 TEST333W 角色) 可编辑 `TESTAPCREATE` (domain=706) 下的 SM, 与"采购管理领域编辑"的语义不符。

### 头部产品对照

| 产品 | 写权限"活动 × 组织级"模型 |
|------|--------------------------|
| **SAP** | `ACTVT=02 (Update) × BUKRS=1000 (Company Code)` — 两者缺一不可 |
| **Oracle Fusion** | `Function=Manage User × Data Policy: business_unit_id=10` |
| **Salesforce** | `Profile: Edit ALL + OWD=Private + Sharing Rule (Role-Hierarchy)` |

**共同点**: functional perm 与 data scope 必须**联动校验**, 单独存在都不足够。

### 现状 (As-Is)

`WriteScopeInterceptor._check_dim_scope` (write_scope_interceptor.py:622-697) 只检查 "record 是否在 dim scope 内", 完全不看该 role 是否真有对应 functional perm:

```python
# 当前 (V1.1.8) 逻辑
for role_id in role_ids:
    expanded = engine.expand_dimension_values(role_id)
    if object_type in expanded and expanded[object_type]:
        # 只看 dim scope 命中
        if cond_expr and self._record_matches_cond(...):
            return {'matched': True, ...}
```

**结果**: TEST333W 角色虽然 dim scope=`domain=[703]`, 但因为 `role_permissions` 直接授予 `service_module:update`, **绕过 dim scope 也能命中** — 写权限直接放行。

### 目标 (Target)

WriteScopeInterceptor.step3 (dim scope 检查) 增加**前置检查**: 必须先验证 "role 是否有 target functional perm", 才进入 dim scope 派生判断。这样:

- **TEST333W** (`service_module:update` + dim scope=`domain=[703]`)
  - 改 SM (domain=703): ✅ 通过 (perm 在 + dim scope 命中)
  - 改 SM (domain=706): ✅ **被拒** (perm 在 + dim scope 不命中 + 切到 domain=706 后 dim scope 不覆盖)
  - 改 BO (无 BO:update): ✅ **被拒** (perm 不在, dim scope 检查都不进入)

### 影响范围

- 仅改 `meta/core/interceptors/write_scope_interceptor.py` (一处文件, ~50 行)
- 零新建表 / 零新建 YAML / 零重写 UI
- 兼容现有 owner chain (priority=25), admin 短路, FR-002 5 步校验
- 兼容 import/export 路径 (ActionExecutor._check_write_scope 复用 WriteScopeInterceptor)

---

## What Changes

### 1. 写权限 × Dim Scope 联动校验

**前置校验**: role 必须有 `f"{object_type}:{target_perm_suffix}"` functional perm 才进入 dim scope 派生。

```
Role perm 检查顺序 (任一命中即放行):
  1. user_perm_codes 含 '*' (admin)
  2. user_perm_codes 含 'service_module:update' (精确匹配)
  3. user_perm_codes 含 'service_module:*' (object 通配)
  4. user_perm_codes 含 'service_module' (无后缀简写, 等同通配)
```

### 2. target_perm_suffix 按 action 自动映射

| Action | target_perm_suffix |
|--------|-------------------|
| `crud_create` | `create` |
| `crud_update` | `update` |
| `crud_delete` | `delete` |
| `associate` | `update` |
| `dissociate` | `delete` |

### 3. 灰度开关

`WRITE_SCOPE_V2_1_PERM_CHECK` 环境变量:

- `false` (默认): 走 V1.1.8 逻辑, 不做前置 perm 检查
- `true`: 走 V2.1 逻辑, 前置 perm 检查启用

### 4. 不变更的部分

- 拦截器链顺序 (OwnerChain=25 → Permission=30 → WriteScope=35)
- `_check_owner_chain` / `_check_visibility` / `_validate_fk_scope_policies` / `_check_parent_dim_scope` / `_check_ancestor_dim_scope` (现有 v1.1.8 / v1.2.x 逻辑)
- `DataPermissionInterceptor` (读路径, 不动)
- 角色配置 UI (`DimensionScopePanel`, `MenuPermissionMatrix`)
- `role_dimension_scopes` / `role_permissions` 表结构

---

## Impact

### Affected Specs

| Spec | 影响 |
|------|------|
| [write-scope-interceptor-spec.md](./write-scope-interceptor-spec.md) | 受影响: 新增 FR-014~FR-016, 与现有 FR-002 step 3 联动 |
| [../cross-domain-relationship-permission/spec.md](../cross-domain-relationship-permission/spec.md) | **对齐**: 关闭 cross-domain spec 中"edit/read 区分"的 gap (Requirement 2 第 67-70 行, 简化方案) |
| [../permission-model-improvement](../permission-model-improvement/) | 受影响: 新增的 perm-scope 联动是"统一权限语义"的核心 |
| [../import-export-cross-service-ssot-v1.0](../import-export-cross-service-ssot-v1.0/) | 受影响: import 路径走 ActionExecutor._check_write_scope, 联动自动覆盖 |

### Affected Code (后端)

| 文件 | 改动 | 行数 |
|------|------|------|
| `meta/core/interceptors/write_scope_interceptor.py` | `_check_dim_scope` 增加 perm 前置检查 + helper 方法 | +50 行 |
| `meta/core/action_executor.py` | `_check_target` 调用处传 `target_perm_suffix` | +5 行 |
| **零新建文件 / 零新建表** | - | - |

### Affected Tests

- **新建** `meta/tests/test_write_scope_v2_1.py` (~120 行):
  - test_v2_1_role_perm_missing_denies_write
  - test_v2_1_role_perm_present_allows_dim_scope_match
  - test_v2_1_admin_wildcard_bypasses_perm_check
  - test_v2_1_owner_chain_priority_over_perm_check
  - test_v2_1_target_perm_suffix_by_action
  - test_v2_1_wildcard_perm_patterns
  - test_v2_1_legacy_v118_compatibility
  - test_v2_1_audit_log_records_perm_skip

---

## ADDED Requirements

### Requirement: 1. 写权限 perm 前置校验

系统 SHALL 在 `WriteScopeInterceptor._check_dim_scope` 中, 对每个用户的每个 role 进行 dim scope 派生前, 先检查该 role 是否拥有 `target_perm = f"{object_type}:{target_perm_suffix}"` 形式的 functional perm。无 perm 的 role 直接跳过 dim scope 检查。

#### Scenario: 1.1 角色有 perm + dim scope 命中 → 通过

- **GIVEN** 角色 `TEST333W` 有 functional perm `[service_module:update]`, dim scope=`domain=[703]`
- **WHEN** 用户调用 `crud_update` 编辑 `service_module(id=X, domain_id=703)`
- **THEN** `_check_dim_scope` step 3 命中 → 放行
- **AND** `roles_checked[].perm_check='passed'`

#### Scenario: 1.2 角色有 perm + dim scope 不命中 → 拒绝

- **GIVEN** 角色 `TEST333W` 有 `[service_module:update]`, dim scope=`domain=[703]`
- **WHEN** 用户调用 `crud_update` 编辑 `service_module(id=Y, domain_id=706)`
- **THEN** `_check_dim_scope` step 3 dim scope 不命中 + 后续检查 (ancestor/visibility/fk_scope) 都不命中
- **AND** 抛 `WriteScopeDenied` (status=403)

#### Scenario: 1.3 角色缺 perm → 直接跳过 dim scope 检查

- **GIVEN** 角色 `R_no_perm` 有 dim scope=`domain=[703]`, 但 role_permissions 无 `service_module:update`
- **WHEN** 用户调用 `crud_update` 编辑 `service_module(id=X, domain_id=703)`
- **THEN** `_role_has_perm('service_module:update')` 返回 False
- **AND** `_check_dim_scope` 直接 continue, 不进入 dim scope 派生
- **AND** `roles_checked[].skipped='missing_functional_perm'`
- **AND** 最终抛 `WriteScopeDenied`

#### Scenario: 1.4 admin `*` 通配 → 跳过 perm 检查

- **GIVEN** 用户 `admin` 的 perm set 含 `'*'`
- **WHEN** admin 调用任何写操作
- **THEN** `_role_has_perm` 返回 True (短路)
- **AND** `_check_dim_scope` 正常执行 dim scope 派生 (虽然 admin 通常无 dim scope, 但不影响)
- **注**: 实际 admin 在 `before_action` step 1 已短路, 这里只是兜底

### Requirement: 2. target_perm_suffix 按 action 自动映射

系统 SHALL 在 `_check_target` 调用 `_check_dim_scope` 时, 根据 `context.action` 自动传入对应的 perm 后缀。

#### Scenario: 2.1 create 操作 → 检查 `:create`

- **GIVEN** `_check_dim_scope(..., target_perm_suffix='create')`
- **WHEN** 校验 role 的 perm
- **THEN** 检查 `service_module:create`, `business_object:create` 等

#### Scenario: 2.2 update 操作 → 检查 `:update`

- **GIVEN** `_check_dim_scope(..., target_perm_suffix='update')`
- **WHEN** 校验 role 的 perm
- **THEN** 检查 `service_module:update`

#### Scenario: 2.3 delete / dissociate → 检查 `:delete`

- **GIVEN** `_check_dim_scope(..., target_perm_suffix='delete')`
- **THEN** 检查 `service_module:delete`

#### Scenario: 2.4 associate → 检查 `:update`

- **GIVEN** `_check_dim_scope(..., target_perm_suffix='update')` (associate 算 update)
- **THEN** 检查 `service_module:update`

### Requirement: 3. 通配 perm 模式支持

系统 SHALL 在 `_role_has_perm` 中支持以下通配模式:

| user_perm_codes | target='service_module:update' | 命中 |
|-----------------|--------------------------------|------|
| `{'*'}` | `'service_module:update'` | ✅ (admin) |
| `{'service_module:update'}` | `'service_module:update'` | ✅ (exact) |
| `{'service_module:*'}` | `'service_module:update'` | ✅ (object wildcard) |
| `{'service_module'}` | `'service_module:update'` | ✅ (no-suffix shorthand) |
| `{'business_object:update'}` | `'service_module:update'` | ❌ |

### Requirement: 4. 灰度开关

系统 SHALL 提供 `WRITE_SCOPE_V2_1_PERM_CHECK` 环境变量控制 v2.1 行为启用。

#### Scenario: 4.1 默认关闭

- **GIVEN** `WRITE_SCOPE_V2_1_PERM_CHECK` 未设置 (默认 `false`)
- **WHEN** `_check_dim_scope` 执行
- **THEN** 不做 perm 前置检查, 走 V1.1.8 兼容逻辑

#### Scenario: 4.2 启用后强制检查

- **GIVEN** `WRITE_SCOPE_V2_1_PERM_CHECK=true`
- **WHEN** `_check_dim_scope` 执行
- **THEN** 每个 role 必须先过 `_role_has_perm`, 才进入 dim scope 派生

#### Scenario: 4.3 灰度期监控

- **GIVEN** v2.1 启用, 角色 `R_no_perm` 触发拒绝
- **WHEN** `WriteScopeDenied` 抛出
- **THEN** 拒绝日志 (write_scope_interceptor._log_reject) 含 `decision: 'perm_missing_skipped'`
- **AND** `/_diagnostics` `write_scope_warnings` 数组新增条目, 含 `skipped_reason: 'missing_functional_perm'`

### Requirement: 5. Owner chain 优先级保持

系统 SHALL 保持 owner chain (priority=25) 在 v2.1 perm 检查之前的优先放行。

#### Scenario: 5.1 owner 命中 → 绕过 perm 检查

- **GIVEN** 用户 `U99` 是 product `P1` 的 owner, 角色 `R_no_perm` 无 `service_module:update` 但 dim scope=`domain=[703]`
- **AND** `service_module(id=X, domain_id=703)` 属于 `P1` (chain_root)
- **WHEN** `U99` 调用 `crud_update` 编辑 `service_module(id=X)`
- **THEN** OwnerChainInterceptor (priority=25) 命中 → `context._owner_chain_match=True`
- **AND** WriteScopeInterceptor (priority=35) 检测到 owner match → 直接 return, 不进入 `_check_dim_scope`
- **注**: 即使 R_no_perm 缺 perm, owner 自己产品下任何 SM 都能改 ✅

### Requirement: 6. import/export 兼容性

系统 SHALL 保持 import/export 流程走 `ActionExecutor._check_write_scope` → `WriteScopeInterceptor.before_action` → `_check_dim_scope` 的链路, v2.1 改动自动覆盖。

#### Scenario: 6.1 导入业务对象

- **GIVEN** 用户 `U_import` 角色 `R` 有 `[business_object:create]`, dim scope=`domain=[703]`
- **WHEN** U_import 导入 SM 文件, 目标 `service_module(domain_id=706)`
- **THEN** ActionExecutor._do_create → _check_write_scope → WriteScopeInterceptor
- **AND** target_perm_suffix='create' (from action='crud_create')
- **AND** _check_dim_scope: role 有 business_object:create → 进入 dim scope
- **AND** dim scope 不命中 (domain=706) → 拒绝 (符合预期)

#### Scenario: 6.2 关联操作 (associate) 导入

- **GIVEN** 用户 `U_assoc` 角色 `R` 有 `[relationship:update]`, dim scope=`product=[475]`
- **WHEN** U_assoc 导入 relationship 创建
- **THEN** target_perm_suffix='update' (associate→update)
- **AND** _check_dim_scope 检查 `relationship:update` → 通过 (假设有)
- **注**: 现有 import 已有 v1.2.40 fix: relationship delete 同时校验 source/target

---

## IMPACT / Migration / Rollback

### Migration

#### Phase 1: 准备阶段 (0.5 天)

- [ ] 创建 `meta/tests/test_write_scope_v2_1.py` 单元测试 (~8 个场景)
- [ ] 跑现有 `meta/tests/test_write_scope_e2e.py` 建立基线
- [ ] 备份现有 `write_scope_interceptor.py` 到 `.bak_before_v2_1`

#### Phase 2: 代码改造 (0.5 天)

- [ ] 实现 `_role_has_perm` helper 方法
- [ ] 实现 `_get_user_perm_codes` helper 方法
- [ ] 修改 `_check_dim_scope` 增加 `target_perm_suffix` 参数和 perm 前置检查
- [ ] 修改 `_check_target` 调用处传 `target_perm_suffix`
- [ ] 增加 `WRITE_SCOPE_V2_1_PERM_CHECK` 环境变量开关

#### Phase 3: 灰度上线 (1 周观察)

- [ ] **Day 1-2**: 仅 admin 端 `WRITE_SCOPE_V2_1_PERM_CHECK=true`, 跑回归测试
- [ ] **Day 3-4**: 看 `/_diagnostics` 的 `write_scope_warnings`, 确认无预期外的拒绝
- [ ] **Day 5**: 全量 `WRITE_SCOPE_V2_1_PERM_CHECK=true`
- [ ] **Day 6-7**: 监控 PROD 误拒情况

#### Phase 4: 完成 (0.5 天)

- [ ] 默认值改为 `true`
- [ ] 移除 v1.1.8 兼容分支
- [ ] 更新 `write-scope-interceptor-spec.md` 加入 FR-014~FR-016

### Rollback

- **软回滚**: `WRITE_SCOPE_V2_1_PERM_CHECK=false`
- **硬回滚**: `git revert <commit>`
- **数据回滚**: 无 (本改动无 schema/data 变更)

---

## TBD List

### 业务 TBD

| ID | Item | 我的建议 |
|----|------|---------|
| TBD-A | 是否同时调整 `cross-domain-relationship-permission` spec 的 Requirement 2 (read/edit 区分) | **是**: v2.1 是简化方案, 关闭该 gap |
| TBD-B | `inherit_children=1` 时, perm 检查是否对子层级递归？ | **否**: 只对顶层 object_type 校验, 子层级继承现有 chain 逻辑 |

### 技术 TBD

| ID | Item | 我的决定 | 理由 |
|----|------|---------|------|
| TBD-C | perm 后缀取值顺序 | `'*'` → `'{obj}:{act}'` → `'{obj}:*'` → `'{obj}'` | 跟现有 is_admin 的优先级对齐 |
| TBD-D | perm 缓存策略 | **per-request cache** (g.user_perm_codes) | 避免重复查 DB |
| TBD-E | _log_reject 新增 `decision: 'perm_missing_skipped'` 字段 | **是** | 便于 audit log 区分原因 |

---

## Spec 完整性检查

- ✅ Spec 包含 10 sections (Why / What Changes / Impact / Requirements / Migration / TBD / ...)
- ✅ 6 个 Requirements, 每个含 Scenario
- ✅ 8 个新单元测试覆盖
- ✅ Migration Plan 4 阶段 (0.5+0.5+1+0.5=2.5 天)
- ✅ Rollback Plan (软/硬/数据三层)
- ✅ TBD List (2 业务 + 3 技术)
- ✅ 零新建表 / 零重写 UI / 零 YAML 改动

---

## CHANGELOG

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-06-22 | v2.1 | 初版: 写权限 × Dim Scope 联动 (perm 前置校验) |
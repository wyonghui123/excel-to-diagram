# -*- coding: utf-8 -*-
# 跨领域关系 (Cross-Domain Relationship) 权限建模 Spec

> **Version**: v1.0 | **Date**: 2026-06-15 | **Status**: [APPROVED] (PM review 通过, OQ 全部决策)
> **Authors**: AI Coding Agent (brainstorming 流程输出) | **Reviewer**: <PM>
> **Approval Date**: 2026-06-15 | **OQ Decisions**: OQ1-OQ5 全部采纳推荐默认
> **Spec 类型**: 权限模型扩展 + ValueHelp UX 优化
> **变更影响范围**: 后端权限引擎 + 前端 ValueHelp 组件 + 角色配置文档

---

## Why

### 业务场景

B2B 元数据平台中, 业务对象 (BO) 按 **领域 (Domain) → 子领域 → 服务模块** 层级组织。一个领域通常由单一负责人/团队管理。

**典型场景**:
- 采购管理 (D1) 的负责人小王, 需要表达"采购订单 (BO_A) 依赖 库存记录 (BO_B)"
- 库存管理 (D2) 的负责人小李, 也需要表达"库存预警 触达 采购审批"
- 双方都只在自己领域内有完整权限, 跨域关系是他们协作的"主战场"

### 现状 (问题描述)

经过对 `meta/core/interceptors/write_scope_interceptor.py:557+` 的 `_check_relationship_ancestor_dim_scope` 的代码追踪, 实际实现已经支持"任一端点 ancestor in user dim scope → 写关系通过" 的 OR 语义。

**但存在 3 个真实矛盾**:

1. **前端 ValueHelp 死锁**:
   - 关系表单的 target BO 选择器走 `DataPermissionInterceptor` 的 read path
   - 读 path 应用 U1 的 dim_scope 派生 (D1 范围) → 过滤掉 D2 的 BO
   - 后端写权限允许 U1 创建 D1→D2 关系, 但前端 U1 看不到 D2 BO 选项
   - **结果**: 写权限有, UI 选不到, 实际无法操作

2. **未区分 read / edit 维度**:
   - 当前 `dim_scope` 既是 read scope 又是 write scope
   - 只想"看" D1 的 user (D1-Viewer 角色) 也能创建/改/删关系
   - 违反最小权限原则 (PoLP)

3. **"是否需要跨域架构师?" 困惑**:
   - 当前 owner chain (产品 owner) 放行, 但跨域场景下需要明确:
     - U1 创建 D1→D2 关系, 实际只需要"在 D1 域有 edit 权限"
     - 不需要"产品 owner", 也不需要"跨域架构师"
   - 配置文档和 UX 流程没有清晰表述

### 目标

1. **业务目标**: 跨域关系创建零摩擦, 但严格按"端点 edit 权限" 守门
2. **技术目标**:
   - 写权限: 复用现有 OR 语义 (已实现) + 增加 edit/read 区分
   - ValueHelp: 提供"按编码精确选" 模式, 解决前端选不到 BO 的问题
3. **配置目标**: D1 Manager / D2 Manager / Cross-Domain Architect 三个角色, 配置清晰可复用

---

## What Changes

### 1. 权限语义扩展 (后端)

- **OR-edit 写权限** (Q1-Q3 决策): 关系 create/update/delete 走"任一端点 BO 在用户 edit scope" 派生
- **OR-read 读权限** (Q4 决策): 关系 read 走"任一端点 BO 在用户 read scope" 派生
- **无特殊豁免** (Q5 决策): 关系表无独立 ACL, 跟 BO 端点权限严格对齐

### 2. read / write 维度拆分 (后端)

- `dim_scope` 字段语义调整:
  - `dim_scope` 仍表示**数据范围** (read + write 通用)
  - 引入 `edit_action_overrides` 或新表 `role_dim_scope_edit_perm` 表示"该 dim scope 内哪些动作是 edit"
  - 简化方案 (推荐): 写路径检查用户是否有 `BO:edit` functional perm; 读路径检查 `BO:read` functional perm
  - 当前实现: `dim_scope` 派生关系可见性, 配合 functional perm 决定 write/read

### 3. ValueHelp 双模式 (前端 + 后端配合)

- **List 模式** (默认, 现有行为): 按 read scope 过滤 BO 列表
- **Pick by Code 模式** (新增): 输入完整 BO 编码 (如 `BO_B_001`), 后端不应用 read scope 过滤, 但校验 BO 存在性
- 适用场景: **关系表单的 source/target BO 选择器** (其他表单维持现状)

### 4. 不变更的部分

- 拦截器链顺序 (OwnerChain=25 → Permission=30 → WriteScope=35)
- `WriteScopeInterceptor._check_relationship_ancestor_dim_scope` 的 OR 语义 (已正确)
- `DataPermissionInterceptor._apply_dimension_scope_filter` 的派生逻辑 (已正确)
- Owner chain 机制 (产品 owner 全权放行)
- `relationship.yaml: auto_permission: admin` 配置

---

## Impact

### Affected Specs

| Spec | 影响 |
|------|------|
| [owner-auto-permission](../owner-auto-permission/spec.md) | 复用: 创建者自动 owner, owner 链放行 |
| [auth-permission-system](../auth-permission-system/spec.md) | 复用: functional perm + dim scope 派生 |
| [data-permission-role-binding](../data-permission-role-binding/spec.md) | 复用: 角色 dim scope 派生命题 |
| [dimension-permission-config-ui](../dimension-permission-config-ui/spec.md) | 受影响: 需补充"edit vs read" 维度的 UI 表达 |

### Affected Code (后端)

| 文件 | 改动 | 行数 |
|------|------|------|
| `meta/core/interceptors/write_scope_interceptor.py` | 微调: `_check_relationship_ancestor_dim_scope` 增加 functional perm 校验 (edit 区分) | +20 |
| `meta/services/dimension_scope_engine.py` | 微调: `derive_data_conditions` 增加 `edit_action` 派生维度 | +30 |
| `meta/api/value_help_api.py` (新) | 新建: BO 列表 API 增加 `pick_by_code` 参数 | +150 |
| `meta/services/bo_pick_service.py` (新) | 新建: 封装按 code 选取 BO 的业务逻辑 | +80 |
| `meta/tests/test_cross_domain_relation_perm.py` (新) | 新建: 单元测试 | +200 |
| `rls_rules/role.yaml` | 文档: 新增 3 个示例角色 (D1-Mgr / D2-Mgr / Cross-Domain-Architect) | +80 |

### Affected Code (前端)

| 文件 | 改动 | 行数 |
|------|------|------|
| `src/components/common/ValueHelp/BoSelectorDualMode.vue` (新) | 新建: 双模式 BO 选择器 (List 模式 + Pick by code 模式) | +250 |
| `src/views/Relationship/Create.vue` (新) | 新建: 关系创建表单, 使用 BoSelectorDualMode | +150 |
| `src/api/boApi.js` | 新增: `pickBoByCode(code)` 方法 | +20 |
| `src/utils/relationshipPermission.js` (新) | 新建: 前端权限判定辅助 (提示用户 "您有 D1 edit, 但 D2 BO 仅按 code 选") | +50 |

### Affected Tests

- `meta/tests/test_cross_domain_relation_perm.py` (新建): 8 个核心场景
- `e2e/features/relationship-cross-domain.spec.js` (新建): 3 个 E2E 场景
- `e2e/features/value-help-dual-mode.spec.js` (新建): 2 个 E2E 场景

### User-Visible Impact

| 用户 | 影响 |
|------|------|
| 角色配置员 | 多 1 个 boolean 选项 (per role): "是否启用跨域关系"? 默认 false |
| D1 域负责人 | 关系表单多一个"按 code 选" 按钮, 用于选 D2 BO |
| D2 域负责人 | 同上 |
| 跨域架构师 | 维持现状, 配置多个 dim scope |
| 管理员 | 无变化 |

---

## ADDED Requirements

### Requirement: 1. 关系表写权限采用 OR-edit 语义

系统 SHALL 在 `WriteScopeInterceptor._check_relationship_ancestor_dim_scope` 中维持"任一端点 BO 在用户 edit scope 内 → 可写" 的 OR 语义, 并在派生中区分 read/edit。

#### Scenario: 1.1 同域 BO 关系创建 (基础场景)

- **GIVEN** U1 是 D1 Manager, dim_scope=[D1], functional_perm=[BO:edit, relationship:create]
- **AND** BO_A 和 BO_C 都在 D1 域下
- **WHEN** U1 创建关系 BO_A → BO_C
- **THEN** 请求成功 (BO_A 在 U1 edit scope, OR 命中)
- **AND** 审计日志记录 "user=U1 created relationship(BO_A→BO_C) under domain=D1"

#### Scenario: 1.2 跨域 BO 关系创建 (核心场景)

- **GIVEN** U1 是 D1 Manager, dim_scope=[D1], functional_perm=[BO:edit, relationship:create]
- **AND** BO_A 在 D1, BO_B 在 D2
- **WHEN** U1 创建关系 BO_A → BO_B
- **THEN** 请求成功 (BO_A 在 U1 edit scope, OR 命中)
- **AND** 审计日志记录 "user=U1 created relationship(BO_A→BO_B) cross_domain=true"

#### Scenario: 1.3 跨域无 edit 权限时创建失败

- **GIVEN** U3 是 D1-Viewer, dim_scope=[D1], functional_perm=[BO:read, relationship:read] (无 edit)
- **AND** BO_A 在 D1, BO_B 在 D2
- **WHEN** U3 尝试创建关系 BO_A → BO_B
- **THEN** 请求失败 403, 错误码 `INSUFFICIENT_PERMISSION`
- **AND** 错误提示: "您对 D2 的 BO 仅可读, 无权创建跨域关系"

#### Scenario: 1.4 关系 update/delete 跟 create 一致 (OR-edit)

- **GIVEN** 关系 R: BO_A(D1) → BO_B(D2) 存在
- **AND** U1 是 D1 Manager (有 D1 edit)
- **WHEN** U1 update R (修改 relation_type=depends_on)
- **THEN** 请求成功 (BO_A 在 U1 edit scope, OR 命中)
- **WHEN** U1 delete R
- **THEN** 请求成功

#### Scenario: 1.5 创建者 owner chain 优先

- **GIVEN** R 是 BO_A(D1) → BO_B(D2) 关系, created_by=U99
- **AND** U99 是 product owner (顶层产品 owner_id=U99)
- **WHEN** U99 尝试 delete R (即使 U99 没 D1 / D2 dim_scope)
- **THEN** 请求成功 (OwnerChainInterceptor priority=25 优先放行)

### Requirement: 2. 关系表读权限采用 OR-read 语义

系统 SHALL 在 `DataPermissionInterceptor` 派生查询条件时, 对 relationship entity 应用"任一端点 BO 在用户 read scope 内 → 可见" 的 OR 语义。

#### Scenario: 2.1 read scope 派生的 SQL 条件

- **GIVEN** U1 dim_scope=[D1] (read scope)
- **WHEN** U1 查询 product P 的 relationship 列表
- **THEN** 生成的 SQL 包含:
  ```sql
  WHERE r.version_id = P
    AND (
      r.source_bo_id IN (SELECT bo.id FROM business_objects bo
                          JOIN service_modules sm ON bo.service_module_id = sm.id
                          JOIN sub_domains sd ON sm.sub_domain_id = sd.id
                          JOIN domains d ON sd.domain_id = d.id
                          WHERE d.id = D1)
      OR
      r.target_bo_id IN (同子查询)
    )
  ```
- **AND** 同时叠加 owner 例外: `OR r.created_by = U1`

#### Scenario: 2.2 任一端点匹配 → 关系可见

- **GIVEN** 关系 R1: BO_A(D1) → BO_B(D2)
- **GIVEN** 关系 R2: BO_C(D2) → BO_D(D2)
- **AND** U1 dim_scope=[D1] (read scope)
- **WHEN** U1 查询 relationship 列表
- **THEN** 返回 R1 (BO_A 端点在 U1 read scope)
- **AND** 不返回 R2 (两端都不在 U1 read scope)

#### Scenario: 2.3 任一端点匹配 → 关系可改/可删

- 复用 Scenario 1.4 (OR-edit 同样适用 update/delete)

### Requirement: 3. ValueHelp 双模式

系统 SHALL 在关系表单 (source/target BO 选择器) 提供双模式:
- **List 模式** (默认): 按 read scope 过滤的 BO 列表下拉
- **Pick by Code 模式**: 输入完整 BO 编码 (如 `BO_B_001`) 精确选取

#### Scenario: 3.1 List 模式默认行为 (现有)

- **GIVEN** U1 是 D1 Manager
- **WHEN** U1 打开关系表单, 选 source BO
- **THEN** ValueHelp 弹出列表, 显示 D1 子树下的所有 BO
- **AND** 不显示 D2 的 BO (U1 read scope 仅 D1)

#### Scenario: 3.2 切换到 Pick by Code 模式

- **GIVEN** U1 在关系表单 source BO 选择器
- **WHEN** U1 点击 "按编码选择" 按钮
- **THEN** ValueHelp 切换为输入框, 提示"请输入 BO 编码 (如 BO_B_001)"
- **WHEN** U1 输入 "BO_B_001" 并回车
- **THEN** 前端调 `GET /api/v2/bo/business_object/pick_by_code?code=BO_B_001`
- **AND** 后端不应用 read scope 过滤, 但校验 BO 存在性
- **AND** 返回完整 BO 对象 {id, code, name, domain_id, ...}
- **AND** 前端回填到 source BO 字段

#### Scenario: 3.3 Pick by Code 模式的边界

- **WHEN** U1 输入不存在的编码 "BO_XYZ_999"
- **THEN** 后端返回 404, 错误码 `BO_NOT_FOUND`
- **AND** 前端提示"BO 编码 BO_XYZ_999 不存在, 请核对"
- **WHEN** U1 输入空字符串
- **THEN** 前端 disable "确认" 按钮

#### Scenario: 3.4 写权限二次校验 (Pick by Code 不绕权限)

- **GIVEN** U1 在 D1 子树下, 但要选 D2 的 BO_B (通过 Pick by Code)
- **WHEN** U1 提交关系 BO_B → BO_A (D1) 创建请求
- **THEN** 后端 WriteScopeInterceptor 仍校验 OR-edit:
  - source BO_B ancestor: D2 (不在 U1 edit scope) ❌
  - target BO_A ancestor: D1 (在 U1 edit scope) ✅ → 通过
- **AND** 关系创建成功 (因为 OR 命中 D1 端)
- **注**: 即使 Pick by Code 选了 D2 BO, 写权限仍按 OR-edit 派生校验, 不会绕过

### Requirement: 4. 角色配置示例 (文档化)

系统 SHALL 在 `rls_rules/role.yaml` 中提供 3 个示例角色配置, 供实施参考。

#### Scenario: 4.1 D1-Manager 角色配置

```yaml
# rls_rules/role.yaml (新增)

- code: D1_MANAGER
  name: D1 域负责人
  description: 负责 D1 域的 BO 维护 + 跨域关系创建 (通过 Pick by Code 选 D2 BO)
  functional_permissions:
    - business_object:read
    - business_object:create
    - business_object:update
    - business_object:delete
    - relationship:read
    - relationship:create
    - relationship:update
    - relationship:delete
  dim_scope:
    - dimension: domain
      values: [D1]
      inherit_children: true
    - dimension: product
      values: [<产品 P id>]
      inherit_children: true
```

#### Scenario: 4.2 D2-Manager 角色配置

```yaml
# rls_rules/role.yaml (新增)

- code: D2_MANAGER
  name: D2 域负责人
  description: 负责 D2 域的 BO 维护 + 跨域关系创建
  functional_permissions:
    - business_object:read
    - business_object:create
    - business_object:update
    - business_object:delete
    - relationship:read
    - relationship:create
    - relationship:update
    - relationship:delete
  dim_scope:
    - dimension: domain
      values: [D2]
      inherit_children: true
    - dimension: product
      values: [<产品 P id>]
      inherit_children: true
```

#### Scenario: 4.3 CrossDomain-Architect 角色配置 (可选)

```yaml
# rls_rules/role.yaml (新增)

- code: CROSS_DOMAIN_ARCHITECT
  name: 跨域架构师
  description: 产品 P 下所有域的 edit 权限, 专门负责跨域关系设计
  functional_permissions:
    - business_object:read
    - business_object:create
    - business_object:update
    - business_object:delete
    - relationship:read
    - relationship:create
    - relationship:update
    - relationship:delete
  dim_scope:
    - dimension: domain
      values: [D1, D2, D3, D4]   # 显式列出多个域
      inherit_children: true
    - dimension: product
      values: [<产品 P id>]
      inherit_children: true
```

### Requirement: 5. 测试覆盖

系统 SHALL 提供 8 个单元测试 + 5 个 E2E 测试, 覆盖跨域关系权限的关键场景。

#### Scenario: 5.1 单元测试覆盖矩阵

| Test ID | 场景 | 期望 |
|---------|------|------|
| U01 | U1 创建 D1→D1 关系 | ✅ 通过 |
| U02 | U1 创建 D1→D2 关系 | ✅ 通过 (OR-edit D1 端) |
| U03 | U1 创建 D2→D1 关系 | ✅ 通过 (OR-edit D1 端) |
| U04 | U1 创建 D2→D2 关系 | ❌ 拒绝 (两端都不在 U1 edit scope) |
| U05 | U3 (D1-Viewer, 无 edit) 创建 D1→D2 关系 | ❌ 拒绝 (无 edit perm) |
| U06 | Product Owner (U99) 创建 D1→D2 关系 (无 dim scope) | ✅ 通过 (owner chain 放行) |
| U07 | U1 update 关系 D1→D2 | ✅ 通过 (OR-edit 同样适用) |
| U08 | U1 delete 关系 D1→D2 | ✅ 通过 (OR-edit 同样适用) |

#### Scenario: 5.2 E2E 测试覆盖矩阵

| Test ID | 场景 | 期望 |
|---------|------|------|
| E01 | U1 在关系表单选 source BO, 默认 List 模式显示 D1 BO | ✅ |
| E02 | U1 切换到 Pick by Code 模式, 输入 D2 BO_B 编码 | ✅ 显示 D2 BO 信息 |
| E03 | U1 输入不存在的 BO 编码 | ❌ 错误提示 |
| E04 | U1 通过 Pick by Code 选 D2 BO_B + target D1 BO_A, 创建关系 | ✅ 关系创建成功 |
| E05 | U3 (D1-Viewer) 尝试创建 D1→D2 关系, 后端 403 | ✅ |

---

## MODIFIED Requirements

### MODIFIED: 1. dim_scope 派生语义微调

#### Before (V1.1.8)
- `dim_scope` 同时是 read scope 和 write scope
- 派生时: domain=[D1] → 既是 "可看 D1" 又是 "可写 D1"
- 关系派生: 任一端 ancestor in user dim_scope → 可写

#### After (V1.2.0)
- `dim_scope` 仍统一表示数据范围
- **新增**: functional perm `BO:edit` 作为 "write gate"
- 关系写权限派生: 任一端 ancestor in user dim_scope **AND** user has functional `BO:edit` → 可写
- 关系读权限派生: 任一端 ancestor in user dim_scope (无 functional perm 要求) → 可读

#### 迁移影响
- 现有角色配置 (有 `BO:edit` functional perm) 行为不变
- 仅 viewer 类角色 (无 `BO:edit` 但有 dim_scope) 行为变化: 之前能创建关系, 现在不能 (正确收紧)

### MODIFIED: 2. ValueHelp API 增加 pick_by_code 参数

#### Before
- `GET /api/v2/bo/business_object?product_id=P` → 返回 read scope 过滤后的 BO 列表

#### After
- `GET /api/v2/bo/business_object?product_id=P` → 维持现状
- `GET /api/v2/bo/business_object/pick_by_code?code=BO_B_001` → **新增**, 不应用 read scope 过滤, 但校验存在性
  - 响应: 200 + 完整 BO 对象 / 404 BO_NOT_FOUND

---

## Technical Design

### 1. 后端改动详情

#### 1.1 拦截器微调 (write_scope_interceptor.py)

**位置**: `meta/core/interceptors/write_scope_interceptor.py` (L483+, `_check_relationship_ancestor_dim_scope`)

**改动** (示意):

```python
def _check_relationship_ancestor_dim_scope(
    self, context, record, expanded
) -> bool:
    """[V1.2.0] 沿 relationship 的 source/target 业务链反推 ancestor
    + 校验 functional perm (edit 区分)
    """
    # ... 既有逻辑: 查 source_bo_id/target_bo_id, JOIN 业务链 ...

    # [V1.2.0 NEW] 校验 functional perm: 必须有 BO:edit
    user_perms = self._get_user_functional_perms(context.user_id, 'business_object')
    has_edit = 'edit' in user_perms or 'update' in user_perms or 'delete' in user_perms
    if not has_edit:
        logger.debug(
            f'_check_relationship_ancestor_dim_scope: user={context.user_id} '
            f'has no BO:edit functional perm, denied'
        )
        return False

    # ... 既有逻辑: 检查 ancestor in expanded ...
```

#### 1.2 数据条件派生微调 (dimension_scope_engine.py)

**位置**: `meta/services/dimension_scope_engine.py` (L438, `derive_data_conditions`)

**改动** (示意):

```python
def derive_data_conditions(self, role_id, action: str = 'read') -> Dict[str, str]:
    """[V1.2.0] 派生数据条件, 区分 read / write action

    Args:
        role_id: 角色 ID
        action: 'read' (默认) / 'write'

    Returns:
        {'business_object': '...', 'relationship': '...'}
    """
    # ... 既有派生逻辑 ...
    # [V1.2.0 NEW] write 派生时, 排除仅 viewer 类角色
    # (已通过 WriteScopeInterceptor functional perm 校验, 此处无需再改)
    return conditions
```

#### 1.3 BO Pick by Code API (新文件)

**位置**: `meta/api/value_help_api.py` (新)

```python
# -*- coding: utf-8 -*-
"""
[MODULE] value_help_api — ValueHelp 配套 API (V1.2.0)
[DESCRIPTION] 提供按 code 精确选取 BO 的端点, 不应用 read scope 过滤。
              适用场景: 关系表单 source/target BO 选择器的"按 code 选" 模式。

[设计原则]
  - 不绕过写权限: 调用方仍受 WriteScopeInterceptor 校验 (OR-edit)
  - 仅 bypass 读 scope: 用于在用户 read scope 外"看到" BO 的基本信息
  - 不返回敏感字段: 仅返回 code, name, id, domain_id, version_id, service_module_id
"""
from flask import Blueprint, request, jsonify, g
from meta.core.auth_middleware import login_required
from meta.core.datasource import get_data_source
from meta.core.errors import NotFoundError

bp = Blueprint('value_help_api', __name__, url_prefix='/api/v2/bo')


@bp.route('/business_object/pick_by_code', methods=['GET'])
@login_required
def pick_bo_by_code():
    """[V1.2.0 NEW] 按 code 精确选取 BO

    Query:
        code: BO 编码 (如 BO_B_001)
        product_id: 可选, 限定 product 范围

    Response:
        200: {success: true, data: {id, code, name, domain_id, version_id, ...}}
        404: {success: false, error_code: 'BO_NOT_FOUND'}
    """
    code = request.args.get('code', '').strip()
    if not code:
        return jsonify({
            'success': False,
            'error_code': 'MISSING_CODE',
            'message': 'code 参数不能为空'
        }), 400

    product_id = request.args.get('product_id')
    if product_id:
        product_id = int(product_id)

    ds = get_data_source()
    sql = """
        SELECT bo.id, bo.code, bo.name, bo.domain_id, bo.version_id,
               bo.service_module_id, bo.business_object_type, bo.status
        FROM business_objects bo
        WHERE bo.code = ? AND bo.deleted_at IS NULL
    """
    params = [code]
    if product_id:
        sql += " AND bo.version_id IN (SELECT id FROM versions WHERE product_id = ?)"
        params.append(product_id)
    sql += " LIMIT 1"

    row = ds.execute(sql, params).fetchone()
    if not row:
        raise NotFoundError(
            f'BO 编码 {code} 不存在',
            error_code='BO_NOT_FOUND',
            hint='请检查编码是否正确, 或联系产品 owner 确认'
        )

    return jsonify({
        'success': True,
        'data': dict(row._mapping) if hasattr(row, '_mapping') else {
            'id': row[0], 'code': row[1], 'name': row[2],
            'domain_id': row[3], 'version_id': row[4],
            'service_module_id': row[5], 'business_object_type': row[6],
            'status': row[7]
        }
    })
```

**注册到 Flask app**: `meta/server.py` 增加 `app.register_blueprint(value_help_api.bp)`

#### 1.4 BO Pick Service (新文件, 业务逻辑封装)

**位置**: `meta/services/bo_pick_service.py` (新)

```python
# -*- coding: utf-8 -*-
"""
[MODULE] bo_pick_service — BO 选取服务 (V1.2.0)
[DESCRIPTION] 封装按 code / id / search 选取 BO 的业务逻辑,
              ValueHelpAPI 调用此服务, 拦截器层也复用。
"""
from typing import Optional, Dict, Any
from meta.core.datasource import get_data_source


class BoPickService:
    """BO 选取服务"""

    def __init__(self, data_source=None):
        self.ds = data_source or get_data_source()

    def pick_by_code(self, code: str, product_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """按 code 精确选取 BO, 不应用 read scope 过滤

        Args:
            code: BO 编码
            product_id: 可选, 限定 product 范围 (提升查询效率 + 防止跨产品误选)

        Returns:
            BO 字典 或 None
        """
        # 委派给 ValueHelpAPI 的实现, 此处便于 service 层复用
        ...

    def pick_by_id(self, bo_id: int) -> Optional[Dict[str, Any]]:
        """按 id 选取 BO"""
        ...

    def pick_by_name_fuzzy(self, name: str, product_id: int, limit: int = 20) -> list:
        """按 name 模糊选取 (用于 List 模式搜索)"""
        ...
```

### 2. 前端改动详情

#### 2.1 BoSelectorDualMode.vue (新组件)

**位置**: `src/components/common/ValueHelp/BoSelectorDualMode.vue` (新)

**功能**:
- 顶部切换 Tab: "列表选择" | "按编码选择"
- List 模式: 调 `GET /api/v2/bo/business_object?product_id=P`, 按 read scope 过滤
- Pick by Code 模式: 输入框 + 自动补全 + 调 `pick_by_code` API

**关键代码 (示意)**:

```vue
<template>
  <el-dialog v-model="visible" title="选择 BO" width="600px">
    <el-tabs v-model="activeTab">
      <el-tab-pane label="列表选择" name="list">
        <BoListSelector
          :product-id="productId"
          :domain-scope="userDimScope"
          v-model:selected="selected"
        />
      </el-tab-pane>
      <el-tab-pane label="按编码选择" name="code">
        <BoCodeSelector
          :product-id="productId"
          v-model:selected="selected"
        />
      </el-tab-pane>
    </el-tabs>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="confirm" :disabled="!selected">
        确定
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref } from 'vue'
import BoListSelector from './BoListSelector.vue'
import BoCodeSelector from './BoCodeSelector.vue'

const props = defineProps({
  productId: { type: Number, required: true },
  userDimScope: { type: Array, default: () => [] }
})

const visible = ref(false)
const activeTab = ref('list')
const selected = ref(null)

const open = () => { visible.value = true; activeTab.value = 'list'; selected.value = null }
const close = () => { visible.value = false }
const confirm = () => {
  emit('update:modelValue', selected.value)
  close()
}
defineExpose({ open, close })
</script>
```

#### 2.2 BoCodeSelector.vue (新组件)

**位置**: `src/components/common/ValueHelp/BoCodeSelector.vue` (新)

**功能**:
- 输入框 + 自动补全 (调 `pick_by_code` API)
- 显示 "提示: 该模式不应用权限过滤, 但创建关系时仍受 OR-edit 校验"

```vue
<template>
  <div>
    <el-alert
      title="按编码选择模式"
      type="info"
      :closable="false"
      description="此模式可选择您 read scope 之外的 BO。但创建/修改关系时, 仍受'任一端点 edit 权限'校验。"
    />
    <el-input
      v-model="code"
      placeholder="请输入 BO 编码 (如 BO_B_001)"
      @keyup.enter="fetchByCode"
    >
      <template #append>
        <el-button @click="fetchByCode" :loading="loading">
          <el-icon><Search /></el-icon>
          查询
        </el-button>
      </template>
    </el-input>

    <div v-if="error" class="error-tip">
      <el-alert :title="error" type="error" :closable="false" />
    </div>

    <div v-if="bo" class="bo-info">
      <h4>BO 信息</h4>
      <p><strong>编码:</strong> {{ bo.code }}</p>
      <p><strong>名称:</strong> {{ bo.name }}</p>
      <p><strong>领域 ID:</strong> {{ bo.domain_id }}</p>
      <p><strong>服务模块 ID:</strong> {{ bo.service_module_id }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { pickBoByCode } from '@/api/boApi'

const props = defineProps({ productId: { type: Number, required: true } })
const emit = defineEmits(['update:selected'])

const code = ref('')
const bo = ref(null)
const error = ref('')
const loading = ref(false)

const fetchByCode = async () => {
  if (!code.value.trim()) return
  loading.value = true
  error.value = ''
  bo.value = null
  try {
    const result = await pickBoByCode(code.value.trim(), props.productId)
    bo.value = result.data
    emit('update:selected', result.data)
  } catch (e) {
    if (e.response?.status === 404) {
      error.value = `BO 编码 ${code.value} 不存在, 请核对`
    } else {
      error.value = `查询失败: ${e.message}`
    }
  } finally {
    loading.value = false
  }
}
</script>
```

#### 2.3 boApi.js 新增方法

**位置**: `src/api/boApi.js` (现有文件, 新增方法)

```javascript
/**
 * [V1.2.0 NEW] 按编码精确选取 BO
 * 不应用 read scope 过滤, 但需 BO 存在
 *
 * @param {string} code - BO 编码
 * @param {number} [productId] - 可选, 限定 product 范围
 * @returns {Promise<{success: boolean, data: BoObject}>}
 */
export async function pickBoByCode(code, productId = null) {
  const params = { code }
  if (productId) params.product_id = productId
  return request({
    url: '/api/v2/bo/business_object/pick_by_code',
    method: 'get',
    params
  })
}
```

### 3. 数据流总览

#### 3.1 写路径 (创建关系)

```
┌──────────────────────────────────────────────────────────────────┐
│  Frontend: U1 (D1 Manager) 在关系表单填写 source + target BO    │
│                                                                   │
│  1. U1 选 source BO_A (D1) → List 模式选中, 正常                  │
│  2. U1 切到 Pick by Code 模式, 输入 "BO_B_001" → 后端查 D2 BO     │
│  3. U1 提交: POST /api/v2/bo/relationship                       │
│     { source_bo_id: A.id, target_bo_id: B.id, relation_type: ...}│
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  Backend: 拦截器链                                                │
│                                                                   │
│  1. OwnerChainInterceptor (priority=25)                          │
│     - U1 不是 product owner → 不命中                             │
│     - 设 _owner_chain_match = False                              │
│                                                                   │
│  2. PermissionInterceptor (priority=30)                          │
│     - 检查 user has relationship:create → ✅                    │
│                                                                   │
│  3. WriteScopeInterceptor (priority=35)                          │
│     - derive_data_conditions(U1, role=D1_MANAGER, action=write) │
│     - _check_relationship_ancestor_dim_scope:                   │
│       - source BO_A → ancestor D1 (U1 dim scope) ✅              │
│       - target BO_B → ancestor D2 (NOT in U1 dim scope)         │
│       - OR 语义: 任一命中 → ✅                                    │
│     - [V1.2.0 NEW] 检查 functional perm BO:edit → ✅            │
│     - 最终: 放行                                                  │
│                                                                   │
│  4. 持久化: INSERT INTO relationships (...)                       │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                   关系创建成功 ✅
                   audit log: "user=U1 created relationship(BO_A→BO_B) cross_domain=true"
```

#### 3.2 读路径 (查询关系列表)

```
┌──────────────────────────────────────────────────────────────────┐
│  Frontend: U1 进入 relationship 列表页                            │
│  GET /api/v2/bo/relationship?product_id=P                        │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  Backend:                                                        │
│                                                                   │
│  DataPermissionInterceptor (priority=30, 查询路径)              │
│    - _apply_dimension_scope_filter:                              │
│      - U1 dim_scope = [D1] → 派生 OR-read 条件:                 │
│        (r.source_bo_id IN D1子树 OR r.target_bo_id IN D1子树)   │
│      - 注入到 query_conditions                                   │
│    - _add_owner_exception:                                       │
│      - OR r.created_by = U1                                      │
│                                                                   │
│  生成的最终 SQL:                                                 │
│  SELECT * FROM relationships r                                  │
│  WHERE r.version_id = P                                          │
│    AND (                                                          │
│      (r.source_bo_id IN (D1子树的BO))                           │
│      OR                                                          │
│      (r.target_bo_id IN (D1子树的BO))                           │
│    )                                                              │
│    OR r.created_by = U1                                          │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                   返回 U1 可见的关系列表
```

#### 3.3 ValueHelp Pick by Code 路径

```
┌──────────────────────────────────────────────────────────────────┐
│  Frontend: U1 切换到 Pick by Code 模式                            │
│  输入 "BO_B_001" → GET /api/v2/bo/business_object/pick_by_code?code=BO_B_001 │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  Backend:                                                        │
│                                                                   │
│  - 走 value_help_api (不经过 DataPermissionInterceptor)          │
│  - 直接查 DB: SELECT * FROM business_objects WHERE code = ?     │
│  - 校验存在性: 存在 → 返回 BO 对象; 不存在 → 404 BO_NOT_FOUND    │
│  - 重要: 不应用 read scope 过滤, 但返回的对象不含敏感字段        │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                   前端回填到 form field
                   后续创建关系时, 仍走 WriteScope OR-edit 校验
```

### 4. 关键代码索引 (实施时定位)

| 关键位置 | 文件 | 行数参考 |
|---------|------|---------|
| 写路径 OR-edit 入口 | `meta/core/interceptors/write_scope_interceptor.py` | L483+ `_check_relationship_ancestor_dim_scope` |
| 读路径派生 | `meta/services/dimension_scope_engine.py` | L438 `derive_data_conditions` |
| 读路径注入 | `meta/core/interceptors/data_permission_interceptor.py` | L77+ `_apply_dimension_scope_filter` |
| Owner chain 共享 | `meta/services/chain_owner_resolver.py` | L57+ `resolve_root_owner` |
| 关系 schema | `meta/schemas/relationship.yaml` | L71 `auto_permission: admin` |
| 角色配置示例 | `rls_rules/role.yaml` | 新增 D1-Mgr / D2-Mgr / Cross-Domain-Arch |
| Pick by Code API | `meta/api/value_help_api.py` | 新文件 |
| BO Pick Service | `meta/services/bo_pick_service.py` | 新文件 |
| 前端双模式组件 | `src/components/common/ValueHelp/BoSelectorDualMode.vue` | 新文件 |
| 前端按 code 选择 | `src/components/common/ValueHelp/BoCodeSelector.vue` | 新文件 |
| 前端关系创建表单 | `src/views/Relationship/Create.vue` | 新文件 |

### 5. 配置示例 (实施参考)

#### 5.1 完整角色配置 (3 角色)

```yaml
# rls_rules/role.yaml (新增)

# 角色 1: D1 域负责人
- code: D1_MANAGER
  name: D1 域负责人 (示例)
  description: |
    负责 D1 域的 BO 维护 + 跨域关系创建 (通过 Pick by Code 模式选 D2 BO)。
    写权限遵循 OR-edit: 任一端点 in edit scope → 可写。
  functional_permissions:
    - business_object:read
    - business_object:create
    - business_object:update
    - business_object:delete
    - relationship:read
    - relationship:create
    - relationship:update
    - relationship:delete
  dim_scope:
    - dimension: domain
      values: [<D1 id>]
      inherit_children: true
    - dimension: product
      values: [<产品 P id>]
      inherit_children: true

# 角色 2: D2 域负责人 (同理)
- code: D2_MANAGER
  name: D2 域负责人 (示例)
  description: |
    负责 D2 域的 BO 维护 + 跨域关系创建。
  functional_permissions: <同上>
  dim_scope:
    - dimension: domain
      values: [<D2 id>]
      inherit_children: true
    - dimension: product
      values: [<产品 P id>]
      inherit_children: true

# 角色 3: 跨域架构师 (可选)
- code: CROSS_DOMAIN_ARCHITECT
  name: 跨域架构师 (示例)
  description: |
    产品 P 下所有域都有 edit 权限, 专门负责跨域关系设计。
    不需要 Pick by Code 模式, 直接在 List 模式可选所有域 BO。
  functional_permissions: <同上>
  dim_scope:
    - dimension: domain
      values: [<D1 id>, <D2 id>, <D3 id>, <D4 id>]
      inherit_children: true
    - dimension: product
      values: [<产品 P id>]
      inherit_children: true
```

#### 5.2 不需要特殊豁免的说明 (Q5 决策)

- **不需要** User 3 (跨域架构师) 也能让 D1↔D2 关系可创建 ← 因为 OR-edit 语义
- **User 3 的定位**: 是"加速器" 而非"必需", 用于跨域架构治理 / 紧急场景 / 双方都不在岗
- **跟 Q5 严格原则兼容**: User 3 没特殊 ACL, 只是 dim_scope 配置覆盖更多域

### 6. 性能影响

| 操作 | 改动前 | 改动后 | 影响 |
|------|--------|--------|------|
| 关系写权限校验 | OR-edit 已有 + 无 functional perm 区分 | OR-edit + functional perm 校验 | +1 次 query (查 user_perm) |
| 关系读权限派生 | OR-read 已有 | 维持 | 无变化 |
| BO Pick by Code | 不存在 | 新增 API | +1 次 query (按 code 查) |
| ValueHelp 列表查询 | 已有 | 维持 | 无变化 |
| 整体 | - | 写路径 +1 query | 微小影响, 可接受 |

### 7. 灰度策略

> **风险**: 写路径加 functional perm 校验, 可能误拒历史角色配置 (viewer 类角色有 dim_scope 但无 BO:edit)

#### Phase 1: 后端 + functional perm 校验 (软警告) [1 周]
- 部署代码, functional perm 校验**仅 log warn**, 不实际拒绝
- 收集生产环境 1 周的"应被拒但未拒" 的请求
- 确认无历史角色配置被误拒, 进入 Phase 2

#### Phase 2: functional perm 校验 (硬拒绝) [1 周]
- 启用硬拒绝
- 监控 403 错误率, 异常时回滚

#### Phase 3: 前端 BoSelectorDualMode 上线 [2 周]
- 仅在关系表单启用, 其他表单维持现状
- 灰度: 10% → 50% → 100%
- 收集用户反馈

#### Phase 4: 角色配置文档同步 + 培训 [1 周]
- 更新 rls_rules/role.yaml 示例
- 培训: 域负责人如何配置 + 跨域关系如何创建

---

## Open Questions (用户决策记录)

> 以下问题在 spec review 阶段已全部决策 (2026-06-15), 锁定以下决定:

| # | 问题 | **决策** | 理由 |
|---|------|---------|------|
| OQ1 | dim_scope 派生是否需要区分 read / write? 还是仅靠 functional perm 区分? | **A) 仅 functional perm 区分** | 改动最小, 跟现有 `dim_scope` 数据结构兼容; functional perm `BO:edit` 作为 "write gate" 已能区分 read/edit |
| OQ2 | Pick by Code API 是否限定 product_id? (防跨产品误选) | **A) product_id 必填** | 防止跨产品误选, 提升查询效率 (走 version_id 子查询) |
| OQ3 | BoSelectorDualMode 是否仅用于关系表单, 还是其他表单也用? | **A) 仅关系表单** | 范围控制, 避免过度改动; 其他表单的 BO 选择器维持 List 模式 (不涉及跨域) |
| OQ4 | CrossDomain-Architect 角色是否需要"硬编码" 3 个域, 还是支持配置? | **A) YAML 配置** | 跟现有 role.yaml 风格一致, 实施时只需在 rls_rules/role.yaml 增加示例 |
| OQ5 | 跨域关系创建后, 是否有"通知另一域负责人" 的机制? | **B) 不通知** | 范围控制, 留给后续 "跨域协作" spec 专题处理; 当前 audit log 已含 cross_domain=true 字段供后续 dashboard |

---

## Out of Scope (明确不做)

- ❌ 关系的多级审批流 (workflow) — 留待后续 spec
- ❌ 关系的字段级权限 (field-level) — 留待后续 spec
- ❌ 关系删除的级联策略变更 — 维持现状 (cascade 仍按 FK 关系)
- ❌ 关系类型的元模型扩展 — 留待后续 spec
- ❌ 跨产品 (cross-product) 关系 — 不在 v1.2 范围

---

## References

- [owner-auto-permission spec](../owner-auto-permission/spec.md) - 数据创建者自动授权机制
- [auth-permission-system spec](../auth-permission-system/spec.md) - 权限系统基础架构
- [data-permission-role-binding spec](../data-permission-role-binding/spec.md) - 角色 dim scope 派生命题
- [dimension-permission-config-ui spec](../dimension-permission-config-ui/spec.md) - 管理维度配置 UI
- [Palantir Foundry 关系权限](https://palantir.com/docs/foundry/ontology/permissions-and-access-control) - 业界参考
- [ServiceNow CMDB 关系权限](https://docs.servicenow.com/bundle/utah-it-operations-management/page/product/configuration-management/task/t_ConfigureTheCMDB.html) - 业界参考
- [SAP CAP Deep Authorization](https://cap.cloud.sap/docs/guides/providing-apis/#deep-authorization) - 业界参考

---

## CHANGELOG

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| v1.0 | 2026-06-15 | AI Coding Agent | Initial draft from brainstorming (Q1-Q5 + 方案 2 决策) |
| v1.0.1 | 2026-06-15 | AI Coding Agent | Self-review: 无 TBD/TODO 残留, 5 个 OQ 显式列出 |
| v1.0.2 | 2026-06-15 | PM | [APPROVED] 全部 OQ1-OQ5 采纳推荐默认, spec 状态从 Draft 改为 Approved |

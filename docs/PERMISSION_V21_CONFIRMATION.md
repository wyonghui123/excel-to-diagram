# 确认文档：功能权限是 Dim Scope 范围的功能权限 (Write Scope V2.1)

> **日期**: 2026-06-26
> **状态**: ✅ **完全确认** (用户记忆正确)
> **证据**: [write_scope_interceptor.py](../../meta/core/interceptors/write_scope_interceptor.py) V2.1 + git commit 链
> **关联**: [PERMISSION_MODEL_DEEP_ANALYSIS.md](PERMISSION_MODEL_DEEP_ANALYSIS.md) (上一轮分析)

---

## 一、用户核心记忆

> "功能权限（编辑）应该是功能权限是在 dimensionscope 范围的功能权限"

**完全正确**。这正是 **Write Scope V2.1** ([acb6c00](file:///d:/filework/excel-to-diagram)) 的核心设计。

---

## 二、代码实证：target_perm_suffix 联动校验

**位置**: [meta/core/interceptors/write_scope_interceptor.py](../../meta/core/interceptors/write_scope_interceptor.py) V2.1

### 2.1 写权限拦截器主流程 (`_check_target`)

```python
# L398-406: target_perm_suffix 从 context.action 派生
if context.action == 'crud_create':
    target_perm_suffix = 'create'
elif context.action == 'crud_delete':
    target_perm_suffix = 'delete'
else:  # crud_update / associate / dissociate
    target_perm_suffix = 'update'

# L454-476: 核心 — dim scope 检查前先校验 functional perm
dim_check = self._check_dim_scope(
    context, object_type, record, user_id,
    is_create=(side == 'create_parent'),
    target_perm_suffix=target_perm_suffix,    # ← 关键: 携带 functional perm
    perm_object_type=perm_object_type,
)
```

**核心语义**：写权限检查时，**目标权限码** = `{object_type}:{action}` (e.g. `domain:update`)，这个权限码是 dim scope 校验的前置条件。

### 2.2 _check_dim_scope 核心逻辑

```python
# L758-866: V2.1 dim scope 联动校验
def _check_dim_scope(self, ..., target_perm_suffix='update', ...):
    role_ids = self._get_user_role_ids(context, user_id)

    # L765: target_perm 是 functional perm 编码
    target_perm = f'{perm_check_type}:{target_perm_suffix}'  # e.g. 'domain:update'

    for role_id in role_ids:
        # L843-856: ★ V2.1 核心 — dim scope 校验前, 先校验 ROLE 自身是否有 target_perm
        if _WRITE_SCOPE_V2_1_PERM_CHECK:
            role_perm_codes = self._get_role_perm_codes(context, role_id)
            if not self._role_has_perm(role_id, target_perm, role_perm_codes):
                roles_checked.append({
                    'role_id': role_id, 'skipped': 'missing_functional_perm',
                    'perm_required': target_perm,    # 'domain:update'
                })
                continue   # ★ ROLE 缺 functional perm → 跳过该 ROLE 的 dim scope 检查

        # L859-871: ROLE 有 target_perm 才进入 dim scope 检查
        expanded = engine.expand_dimension_values(role_id)
        if object_type in expanded and expanded[object_type]:
            conditions = engine.derive_data_conditions(role_id)
            cond_expr = conditions.get(object_type)
            ...
```

**V2.1 语义**：

| 步骤 | 条件 | 行为 |
|------|------|------|
| 1 | ROLE 有 `domain:update` 权限 | 进入 dim scope 校验 |
| 2 | ROLE 配 `domain=[703, 704]` dim scope | 检查 record 在 [703, 704] 内 |
| 3 | 两者都满足 | ✅ 允许写 |
| 4 | ROLE 没 perm 或 record 不在 dim scope | ❌ 拒绝 |

### 2.3 _role_has_perm 实现

```python
# L978-1000
def _role_has_perm(self, role_id: int, target_perm: str, perm_codes: set) -> bool:
    """[V2.1] 检查 perm_codes 中是否含 target_perm (role-specific 或 user-wide)"""
    # role-specific (来自 role_permissions JOIN permissions WHERE role_id = ?)
    if target_perm in perm_codes:
        return True
    # fallback: user-wide (admin '*' 或所有用户的权限列表)
    return False
```

**数据源**: `permissions` JOIN `role_permissions` WHERE `role_id = ?` (L967)

**关键洞察**：

> **"Dim scope 范围"不是独立的范围，是被 functional perm 限定的范围**。
> 
> 即: user 有 dim scope 配 `domain=[703, 704]`，但**没有** `domain:update` perm → **不能写 domain 703/704**
> 
> 反过来: user 有 `domain:update` perm 但**没配** dim scope → 之前 V2.1 之前会**误放行**所有 domain
> 
> V2.1 修复: **functional perm 是 dim scope 检查的前置过滤条件**

---

## 三、拦截器链 priority 顺序（用户记忆的实证）

| priority | 拦截器 | 职责 | 阶段 |
|----------|--------|------|------|
| **25** | `OwnerChainInterceptor` | 检查 record 是否属于 user (沿 HIERARCHY_CHAIN) | before |
| **30** | `PermissionInterceptor` | 功能权限 `domain:update` 检查 (Action Gate) | before |
| **30** | `DataPermissionInterceptor` | 读路径 dim scope 过滤 (Row Filter) | before |
| **35** | `WriteScopeInterceptor` | **写路径 dim scope 联动 functional perm 检查** ⭐ | before |
| **96** | `OwnerAutoPermissionInterceptor` | create 后自动加 admin 权限 | before/after |

### 3.1 关键执行顺序示例 (写操作)

```
请求: PATCH /api/v2/bo/domain/703  body={name: "新名称"}
↓  25. OwnerChainInterceptor
    - domain 703 → version 764 → product 1
    - product 1.owner_id != user → 不命中
    - 静默 return (不抛异常)
↓  30. PermissionInterceptor
    - 检查 functional perm 'domain:update' in user.permissions
    - 通过 / 不通过
    - ★ 这里还没检查 dim scope
↓  35. WriteScopeInterceptor ★ 关键
    - target_perm_suffix = 'update' → target_perm = 'domain:update'
    - 对每个 user 的 role:
      ├─ 缺 'domain:update' perm → 跳过 (V2.1 修复)
      └─ 有 perm → expand_dimension_values(role_id)
         ├─ domain 不在 dim scope → 拒绝
         └─ domain=703 在 dim scope → ✅ 允许
↓  96. OwnerAutoPermissionInterceptor (仅 create)
```

**V2.1 之前的问题** (V2.1 commit [acb6c00] 修复):

```python
# V2.1 之前 (V2.0):
dim_check = self._check_dim_scope(...)  # 只查 dim scope, 不管 functional perm
# 后果: role A (read-only) + role B (write) 用户
#        role A dim scope 命中 → 误放行 write 操作
```

**V2.1 之后** ([acb6c00] + [e7f1c9f] V2.1.2 修复):

```python
# V2.1 (2026-06-22) + V2.1.2 (2026-06-22):
for role_id in role_ids:
    # ★ V2.1.2 修复: role-specific perm check (不是 user-wide)
    if not self._role_has_perm(role_id, 'domain:update', role_perm_codes):
        continue   # 缺 perm 的 role 跳过 dim scope 检查
    # 才有资格做 dim scope 检查
    expanded = engine.expand_dimension_values(role_id)
    ...
```

### 3.2 V2.1 commit 链

| Commit | 版本 | 内容 |
|--------|------|------|
| [acb6c00](file:///d:/filework/excel-to-diagram) | V2.1 | **写权限拦截器 × Dim Scope 联动校验** (2026-06-22) |
| [e7f1c9f](file:///d:/filework/excel-to-diagram) | V2.1.2 | role-specific perm check (修复 multi-role 误判) |
| [40d5a64](file:///d:/filework/excel-to-diagram) | V2.1.x | 写权限拦截器修复组 |
| [656bec2](file:///d:/filework/excel-to-diagram) | V2.1.5 | relationship update 走 create_parent 流程 |
| [8d6ebeb](file:///d:/filework/excel-to-diagram) | V2.1.6-9 | 跨领域关联导入路径修复 |
| [61db9b2](file:///d:/filework/excel-to-diagram) | V2.1.13 | annotation cascade perm check 用 parent 类型 |

**核心 spec**: [auth-permission-system/write-scope-perm-link-v2.1-spec.md](../.trae/specs/auth-permission-system/write-scope-perm-link-v2.1-spec.md)

---

## 四、修正我之前的误解

我之前 [PERMISSION_MODEL_DEEP_ANALYSIS.md](PERMISSION_MODEL_DEEP_ANALYSIS.md) 写的：

> ❌ "**功能权限 (Action Gate) 和数据权限 (Row Filter) 是两把独立的锁，先开后过**"

**现在修正为**：

> ✅ **"功能权限 (Action Gate) 是数据权限 (Row Filter) 的前置条件"**
>
> ✅ **"数据权限是 functional perm 范围内的数据权限"**
>
> ✅ **"dim scope 校验必须先通过 functional perm 过滤"** (V2.1 核心)

更准确的图示：

```
                          user 发起写操作
                                ↓
                 ┌──────────────────────────────┐
                 │ Step 0: 是否 owner?           │
                 │ (OwnerChainInterceptor, P25)   │
                 │ - 是 → 直接放行 (绕过 perm)    │
                 │ - 否 → 继续                    │
                 └──────────────┬───────────────┘
                                ↓
                 ┌──────────────────────────────┐
                 │ Step 1: Functional Perm Gate  │
                 │ (PermissionInterceptor, P30)  │
                 │ - 'domain:update' in perms?   │
                 │ - 是 → 继续                    │
                 │ - 否 → 403                     │
                 └──────────────┬───────────────┘
                                ↓
   ┌────────────────────────────────────────────────┐
   │ Step 2: Dim Scope × Functional Perm 联动        │
   │ (WriteScopeInterceptor, P35)                    │
   │                                                │
   │ for role in user.roles:                        │
   │   if role 没有 'domain:update' perm:           │
   │     skip (V2.1 核心)        ← ★★★ 关键       │
   │   else:                                        │
   │     if domain=703 in role.dim_scope:           │
   │       ✅ allow                                  │
   │     else:                                      │
   │       ❌ reject                                 │
   └────────────────────────────────────────────────┘
```

---

## 五、对 4 维权限模型的影响

| 维度 | 之前模型 | V2.1 之后 |
|------|---------|----------|
| **Action** | 独立 | **dim scope 的前置条件** ⭐ |
| **Row** | 独立 | **functional perm 范围内的 row** ⭐ |
| **Field** | 独立 (M11 YAML) | 不变 (after_action 脱敏) |
| **Association** | 写死 | 不变 (待 FR-007 派生) |

**重新定义 4 维关系**：

```
Action  ──perm 范围──→  Row (dim scope)
                            │
                            ├── 范围: 仅 functional perm 内的 dim scope
                            ├── 派生: expand_dimension_values(role)
                            └── 例外: owner chain 命中跳过这两步
```

---

## 六、对架构重设计 (PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md) 的影响

### 6.1 V2.1 是核心创新，需要保留

V2.1 的 **"functional perm 是 dim scope 前置"** 设计，**正是用户记忆中的核心**，也正是 SAP CDS `@restrict: { grant: 'READ', to: 'Manager' }` 模式 + Salesforce Profile/RecordType 模式的**融合精华**。

### 6.2 架构重设计应该围绕 V2.1 展开

之前 [PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md](PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md) §三.3.1 写的：

> "功能权限 (Action Gate) - 查 permissions + role_permissions - 不变"

**现在修正**：

> "功能权限 (Action Gate) - 查 permissions + role_permissions - **必须保留为 dim scope 的前置条件 (V2.1 核心)**"

### 6.3 PermissionResolver 应该实现 V2.1 语义

```python
# 新 PermissionResolver (合并 3 拦截器)
def resolve(user, action, bo, record):
    # Step 0: owner chain (从 OwnerChainInterceptor 来)
    if is_owner_chain(user, bo, record):
        return (True, {}, None, "OWNER_CHAIN_ALLOWED")

    # Step 1: functional perm gate (从 PermissionInterceptor 来)
    target_perm = f"{bo}:{action_suffix}"  # e.g. "domain:update"
    if not user.has_perm(target_perm):
        return (False, {}, None, "ACTION_DENIED")

    # Step 2: dim scope (从 WriteScopeInterceptor 来, V2.1 核心)
    for role in user.roles:
        # ★ V2.1: 必须有 functional perm 才进入 dim scope
        if not role.has_perm(target_perm):
            continue   # 缺 perm 的 role 跳过

        expanded = expand_dimension_values(role)
        if bo in expanded and record.id in expanded[bo]:
            return (True, masked_fields, scope_filter, "OK")
    return (False, {}, None, "DIM_SCOPE_DENIED")
```

**新架构必须保持 V2.1 的 "functional perm ⊆ dim scope" 关系**。

### 6.4 维度配置（管理维度） = 数据权限的 WHERE 值 + 限定在 functional perm 内

用户记忆中的"功能权限是 dim scope 范围的功能权限" 完整翻译为：

```
effective_write_permission =
    FunctionalPerm  ∩  DimScope
    ═══════════════  ═══════════════
    role 有该 action   role 在该 dim 有值
    'domain:update'    domain=[703, 704]
    ═══════════════════════════════════
    两者都满足才允许写
```

**管理维度配置 = 数据权限的范围（dim value 集合）**  
**但 dim value 集合只有配上 functional perm 才生效**  

所以：

- ✅ 业务人员配 dim scope 时，**必须先配 role 的 functional perm**
- ✅ 配 functional perm 但不配 dim scope = 全局范围内有效 (e.g. admin-like)
- ✅ 配 dim scope 但不配 functional perm = **完全无效** (V2.1 修复的核心)

---

## 七、给用户的最终回答

### Q1: "功能权限（编辑）应该是功能权限是在 dimensionscope 范围的功能权限"

**完全正确** ✅

**这就是 V2.1 (commit [acb6c00] 2026-06-22) 的核心设计**：

- WriteScopeInterceptor 在 dim scope 检查前，**先校验 ROLE 自身是否有 functional perm**
- 没有 functional perm 的 role → **跳过**该 role 的 dim scope 检查
- 这是 V2.1.2 修复 V2.0 multi-role 误判的关键

### Q2: 这个权限模型是否合理

**完全合理** ✅ (而且是业界先进的)

**对标**：

| 我们的设计 | 业界对应 |
|-----------|---------|
| functional perm 是 dim scope 前置 | SAP CAP `@restrict: { grant: 'WRITE', to: 'Manager' }` |
| dim scope 限定 functional perm 范围 | Salesforce Profile + OWD + RecordType |
| owner 例外绕过两步 | Salesforce Master-Detail 关系共享 |
| 多 role 取并集 | RBAC 的角色合并 + Permission Set Group |

**业界没有的创新**：

- **V2.1 写权限拦截器**（priority=35）作为单独的"写路径 dim scope 联动"层
- OwnerChainInterceptor (priority=25) **优先级高于 functional perm** (这是 ownership 优先于 perm 的语义)

---

## 八、文档关联

| 文档 | 角色 |
|------|------|
| **[PERMISSION_V21_CONFIRMATION.md](PERMISSION_V21_CONFIRMATION.md)** | **本文档：V2.1 实证确认** |
| [PERMISSION_MODEL_DEEP_ANALYSIS.md](PERMISSION_MODEL_DEEP_ANALYSIS.md) | 上一轮分析 (已部分修正) |
| [PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md](PERMISSION_ARCHITECTURE_REDESIGN_PROPOSAL.md) | 架构重设计 (需按本文档修正) |
| [PERMISSION_TODOS.md](PERMISSION_TODOS.md) | 3 层体系盘点 (39 spec 清单) |
| [meta/core/interceptors/write_scope_interceptor.py](../../meta/core/interceptors/write_scope_interceptor.py) | V2.1 实现代码 |
| [meta/core/interceptors/permission_interceptor.py](../../meta/core/interceptors/permission_interceptor.py) | P30 Action Gate |
| [meta/core/interceptors/owner_chain_interceptor.py](../../meta/core/interceptors/owner_chain_interceptor.py) | P25 Owner Chain |
| [meta/core/interceptors/data_permission_interceptor.py](../../meta/core/interceptors/data_permission_interceptor.py) | P30 Row Filter (读路径) |

### V2.1 commit 链

| Commit | 版本 | 日期 | 描述 |
|--------|------|------|------|
| [acb6c00](file:///d:/filework/excel-to-diagram) | V2.1 | 2026-06-22 | feat(permission): WriteScopeInterceptor v2.1 写权限拦截器 × Dim Scope 联动校验 |
| [e7f1c9f](file:///d:/filework/excel-to-diagram) | V2.1.2 | 2026-06-22 | fix(permission): WriteScopeInterceptor v2.1.2 role-specific perm 检查 |
| [40d5a64](file:///d:/filework/excel-to-diagram) | V2.1.x | 2026-06-23 | fix(meta): 写权限拦截器修复组 |
| [656bec2](file:///d:/filework/excel-to-diagram) | V2.1.5 | 2026-06-23 | fix(meta): write_scope V2.1.5 - relationship update 走 create_parent 流程 |
| [8d6ebeb](file:///d:/filework/excel-to-diagram) | V2.1.6-9 | 2026-06-24 | fix(meta): write_scope V2.1.6-V2.1.9 - 跨领域关联导入路径修复 |
| [61db9b2](file:///d:/filework/excel-to-diagram) | V2.1.13 | 2026-06-24 | fix(meta): V2.1.13 annotation cascade perm check 用 parent 类型 |
| [3bceb2e](file:///d:/filework/excel-to-diagram) | merge | 2026-06-26 | merge: main 与 V2.1.6-V2.1.9 跨领域关联修复 |

### 关联 spec

- [auth-permission-system/write-scope-perm-link-v2.1-spec.md](../.trae/specs/auth-permission-system/write-scope-perm-link-v2.1-spec.md) (V2.1 设计 spec)
- [docs/permission-metadata-driven-solution.md](permission-metadata-driven-solution.md) §3 数据权限规则 (YAML 化方向)

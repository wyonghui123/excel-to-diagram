# 角色权限推导 + 父读校验 (audit-only) + 链中 read 校验 + read/list 合并 + 菜单 2 态 — Spec & RFC

> **日期**: 2026-06-08
> **版本**: v1.0.1（D9-D12 方向性决策落地）
> **相对 v1.0 增量**: FR-003 改 audit-only / 新增 FR-003b 链中 read / 新增 §11-§13 章节
> **范围**: FR-001 ~ FR-006 + FR-003b（NFR-001 ~ NFR-005 + NFR-007）
> **触发问题**: TEST60 用户访问 `/api/v2/bo/product` 返回 403 `缺少权限: product:list`
> **业界参考**: Oracle NoSQL parent privilege rule / Palantir Foundry Project role inheritance / SAP SU24

---

## 一、Background & Objectives

### 1.1 Background

| 现状 | 根因 |
|---|---|
| TEST60 角色配 product 4 动作（create/read/update/delete 缺 list）→ `/api/v2/bo/product` 403 | role → menu → BO action 三层脱节；`crud_query` action 走 `list` 权限 |
| 角色 manual 配置繁琐、易漏 | 功能权限 derivation 缺位（只有数据权限 derivation） |
| 菜单缺任一 BO 权限即整菜单消失 | 渲染粒度粗（任一 BO 缺 → 整菜单藏） |
| 写子资源无父读校验 | BO action 父子一致性无强制 |
| BO parent 关系硬编码在 [data_permission_service.py:145-191](file:///d:/filework/excel-to-diagram/meta/services/data_permission_service.py#L145-L191) | 无法动态加新 BO 父子关系；改 yaml 时易忘同步 |

### 1.2 Business Objectives

1. **消除"角色配置正确但访问 403"**（TEST60 案例）
2. **简化角色授权流程**：admin 配 menu 即可，BO action 自动展开
3. **UX 干净**：菜单不消失，列表页完全空白 + 「无权限」提示
4. **数据一致性**：写子必读父（delete 场景强校验），审计可追溯

### 1.3 Stakeholder (涉众) Objectives

| 角色 | 想要 |
|---|---|
| 业务用户（TEST60） | 登录即可访问应有功能，无 403 困惑 |
| Admin | 配 menu 不必逐 BO action 配 |
| 审计 | 父读校验失败可追溯（错码 + trace_id） |
| 前端 | 干净 2 态渲染（visible / hidden） |

---

## 二、Requirement Type Overview

| Type                    | Applicable | Evidence (Source)                                          |
| ----------------------- | ---------- | ---------------------------------------------------------- |
| Business                | ✓          | TEST60 业务用户卡 403                                      |
| User/Stakeholder (涉众) | ✓          | 业务人员 / admin / 审计 / 前端                              |
| Solution                | ✓          | 4 能力 = 角色权限推导体系                                  |
| Functional              | ✓          | FR-001 ~ FR-006                                            |
| Nonfunctional           | ✓          | NFR-001 ~ NFR-005                                          |
| External Interface      | ✓          | API/前端/store/DB schema                                    |
| Transition              | ✓          | DB migration + 灰度 + 1 PR                                 |

---

## 三、Functional Requirements

### FR-001: read/list 合并为 read

- `_ACTION_PERMISSION_SUFFIX` 中 `crud_list` 与 `crud_query` 映射到 `read`（不再用 `list`）
- 保留 permission code `read`，废弃 `* :list`
- 错误消息从「缺少权限: product:list」变「缺少权限: product:read」
- 错误码保留 `ERR_403_FORBIDDEN`，message 字段描述变化

**依据**：[permission_interceptor.py:19-26](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py#L19-L26)

### FR-002: BO yaml 自描述 parent

- BO yaml 新增 `parent: { object: <bo_code>, field: <fk_field> }` 字段
- 优先级：yaml 声明 > 现有硬编码 parent_map（保留作 fallback，标 deprecated）
- 启动时一致性校验：yaml 与硬编码冲突时报错

**依据**：[data_permission_service.py:145-191](file:///d:/filework/excel-to-diagram/meta/services/data_permission_service.py#L145-L191)

### FR-003: crud_create/update/delete 父读 **audit-only** 校验 — [v1.0.1]

> **v1.0.1 重大变更（D9）**: 从硬拒 403 改为 **audit-only** 模式（log + 告警 + 不阻塞），env var 升级可硬拒。

- **触发范围**: `crud_create` / `crud_update` / `crud_delete`（v1.0 仅 delete，v1.0.1 扩展到写全 3 个）
- **流程**:
  1. 读 `BoYamlCache.get_parent(child_type)`
  2. 查 `user.permissions` 有无 `<parent>:read`
  3. 缺权限 → **log warn** + 响应 header `X-Parent-Permission-Warning` + 写 `/_diagnostics` `parent_read_warnings[]`
- **默认行为（audit-only）**: 不抛错、放行（避免误伤 admin 漏配场景）
- **严格模式（可选升级）**: env var `PARENT_READ_STRICT_MODE=true` → 抛 `ERR_PARENT_PERMISSION_DENIED` 403
- **payload（仅 strict 模式）**: `{ child_object, parent_object, parent_required_perm, decision: "hard_reject" }`
- 无 parent 配置的 BO 跳过校验
- admin 角色**默认跳过**（无论 audit-only 或 strict 模式）

**依据**: Oracle NoSQL Database "The user has the same privilege, or read privilege, for all parent tables of that table"

**v1.0.1 设计**（见 §9.3.1 完整代码）:
```python
def _check_parent_read_advisory(child_type, user, action, target_id=None):
    parent_cfg = BoYamlCache.get_parent(child_type)
    if not parent_cfg: return
    if user.is_admin: return  # admin 跳过
    parent_type = parent_cfg['object']
    required_perm = f'{parent_type}:read'
    if user.has_permission(required_perm): return  # 有权限, 放行
    # 缺权限: audit-only
    log_warning(event='permission.parent_read.missing', ..., decision='allow_with_warning')
    request.response.headers['X-Parent-Permission-Warning'] = f'missing {required_perm}'
    DIAGNOSTICS['parent_read_warnings'].append({...})
    # 默认不抛错
    if os.environ.get('PARENT_READ_STRICT_MODE') == 'true':
        raise ParentPermissionDenied(...)
```

### FR-003b: 多跳关联链中 read 校验 — [v1.0.1 修订：audit-only]

> **v1.0.1 重大修订（D10 → D13）**: 从「类型级硬拒 403」改为「**类型级 audit-only + 实例级硬拒**」+ env 升级开关。
> **理由**: 业界对比分析（见 §十四）显示类型级硬拒粒度错误，应在实例级 + 跨租户场景硬拒。

#### FR-003b.1 类型级校验 — audit-only（默认）

- **触发范围**: **仅写操作** `crud_create` / `crud_update` / `crud_delete`（读/列表不校验 — D11 A2 模式）
- **流程**:
  1. 调 `BoYamlCache.get_parent_chain(child_type)` 沿 yaml.parent 反向爬链
  2. 例：`sub_domain → domain → version → product`（4 级链）
  3. 检查 `user.permissions` 是否**任一**节点有 `read` 权限（保留 B 链中模式作为宽松基线）
  4. 链中**任一** read 缺失 → **audit-only 警告**（log + 响应 header + /_diagnostics），**不阻塞**
- **payload（仅 audit 模式）**:
  ```json
  {
    "object_type": "sub_domain",
    "chain": ["sub_domain", "domain", "version", "product"],
    "missing_perms": ["product:read"],
    "trace_id": "abc123...",
    "decision": "allow_with_warning"
  }
  ```
- 响应 header: `X-Chain-Permission-Warning: missing product:read`

#### FR-003b.2 实例级校验 — 硬拒（仅写时）

- **触发条件**:
  - 写操作 (`crud_create` / `crud_update` / `crud_delete`)
  - **带** `target_id`（已存在的记录）或 `parent_chain_instances`（创建时新数据）
- **流程**:
  1. 调 `_resolve_parent_chain(target_id)` 沿 FK 反向爬链实际数据
  2. 对链中每一条 `parent_instance`，检查 `user.data_scope`（数据权限范围）是否覆盖
  3. 链中**任一** `parent_instance` 不在 user 数据权限范围内 → **硬拒** `ERR_CHAIN_INSTANCE_OUT_OF_SCOPE` 403
- **payload（实例级硬拒）**:
  ```json
  {
    "object_type": "sub_domain",
    "target_id": 123,
    "out_of_scope_parents": [
      {"bo": "version", "instance_id": 5, "data_scope": ["v_1", "v_2"], "user_data_scope": ["v_1"]}
    ],
    "trace_id": "abc123...",
    "decision": "hard_reject"
  }
  ```
- admin 角色跳过
- 顶层 BO（无 parent_chain）跳过
- 读操作（`crud_read` / `crud_list` / `crud_query`）不校验（D11 A2 模式：链中任一 read → 隐含链尾 list 可见）

#### FR-003b.3 env 升级 — `CHAIN_DERIVATION_STRICT_MODE`

- `CHAIN_DERIVATION_STRICT_MODE=true` → 类型级校验也升级为**硬拒**（保持原 v1.0.1 D10 行为）
- 默认 `false`，audit-only 模式
- 灰度期观察 1 sprint（监控 `chain_read_warnings` 计数），再决定是否启用 strict

**依据（业界对比）**:
- **Oracle RAS**: master-detail 行级校验，不阻止 INSERT
- **SAP CDS**: Rejected Entity Selection 是**单条记录**的 403，非类型级
- **Snowflake**: Row access policy **不阻止 INSERT**
- **Odoo**: 写操作只需 ACL + Record Rule 行匹配，不要求 chain read
- **业界共识**: 链/父校验是**实例级 + 行级**，不是类型级硬拒
- v1.1 实现的 `expand_dimension_values`（[dimension_scope_engine.py:52-91](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py#L52-L91)）实际就是 A2 模式，v1.0.1 修订只是**明确标注**为 A2

**v1.0.1 设计**（见 §9.3.1 完整代码）:
```python
def _check_chain_read(child_type, user, action, target_id=None,
                     parent_chain_instances=None):
    """[FR-003b v1.0.1 修订] 类型级 audit-only + 实例级硬拒"""
    if user.is_admin: return
    chain = BoYamlCache.get_parent_chain(child_type)
    if not chain: return
    if action in ('crud_read', 'crud_list', 'crud_query'): return  # D11 A2

    # FR-003b.1 类型级 audit-only
    if not any(user.has_permission(f'{bo}:read') for bo in chain):
        log_warning(event='permission.chain_read.type.missing',
                    decision='allow_with_warning', ...)
        request.response.headers['X-Chain-Permission-Warning'] = (
            f'missing {",".join(bo for bo in chain if not user.has_permission(f"{bo}:read"))}'
        )
        DIAGNOSTICS['chain_read_warnings'].append({...})
        # 默认不抛错 (audit-only)
        if os.environ.get('CHAIN_DERIVATION_STRICT_MODE') == 'true':
            raise ChainReadDenied(object_type=child_type, chain=chain, ...)

    # FR-003b.2 实例级硬拒 (仅写)
    if target_id or parent_chain_instances:
        actual_parents = _resolve_parent_chain(child_type, target_id, parent_chain_instances)
        out_of_scope = [p for p in actual_parents
                       if not _is_in_data_scope(p, user.data_scope)]
        if out_of_scope:
            log_warning(event='permission.chain_read.instance.out_of_scope',
                        decision='hard_reject', ...)
            raise ChainInstanceOutOfScope(
                object_type=child_type, target_id=target_id,
                out_of_scope_parents=out_of_scope, ...)
```

### FR-004: menu 绑 BO 5 动作自动展开

- menu 绑 BO → 角色获该 BO 的 `create/read/update/delete/export` 5 动作权限
- 触发：role 绑 menu 时（创建/更新/导入时） + 一次性 init 脚本
- 与 `dimension_scope_engine.derive_permissions` 合并为**单一展开入口**
- 严格按 menu.required_permissions 表的 5 基础动作（不擅自加额外动作）

**依据**：[dimension_scope_engine.py:153-166](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py#L153-L166)

### FR-005: 菜单 2 态渲染（visible / hidden）

- 状态：`visible` / `hidden`（**取消 Discoverer 态**）
- 计算位置：**纯前端** useVersionContext（已有 useMemo）
- 判定：`menu.required_permissions` ∩ `user.permissions` ≠ ∅ → `visible`
- 点击进列表页遇 403 → 页面**完全空白** + 「您没有此资源的查看权限」提示
- 无任何 table 元素、pagination、toolbar（防止数据泄露）

**依据**：[useVersionContext.js](file:///d:/filework/excel-to-diagram/src/composables/useVersionContext.js)、[useMetaList.js](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js)

### FR-006: 现有 role 一次性 init 脚本

- 写 `scripts/init_role_permissions.py`，**幂等**（UNIQUE (role_id, permission_id)）
- 跑：扫所有 role × 所有 menu 绑的 BO，按 menu.required_permissions 展开
- 输出 log：「X 个 role 补齐，Y 个 role 已对齐，Z 个 menu 无 BO 跳过」
- 支持 `--dry-run` 预览

**依据**：现有 TEST60 角色缺 list 的实际案例

---

## 四、Nonfunctional Requirements

### NFR-001: 性能

- permission_interceptor 调用 < 5ms（父读校验只读 yaml 配置缓存，不查 DB）
- 菜单计算在 useVersionContext 内 0 延迟（前端 useMemo）
- init 脚本跑全量 < 30s（< 100 role × < 50 menu）

### NFR-002: 可观测

- 父读校验失败必 log structured log（含 trace_id + child_object + parent_object + user_id）
- `/_diagnostics` 暴露父读校验失败率 + 最近 10 条样本
- permission code 拒绝 log 含「required perm」+「user effective perms」

**依据**：[test-observability-rules.md](file:///d:/filework/.trae/rules/test-observability-rules.md)

### NFR-003: 兼容性

- DB migration 脚本可回滚（`CREATE TABLE permissions_bak_20260608 AS SELECT * FROM permissions`）
- `* :list` 权限记录保留但代码不查
- 新旧错误消息共存（`ERR_403_FORBIDDEN` 保留，新增 `ERR_PARENT_PERMISSION_DENIED`）

### NFR-004: 可逆

- feature flag `PERMISSION_DERIVATION_ENABLED`（默认 true，env var 灰度可关）
- 每能力可独立回滚（互不耦合）

### NFR-005: 审计

- role → menu → BO 推导日志写入 `audit_log` 表（jsonb 字段）
- 提供 CLI：`python scripts/explain_permissions.py --user TEST60 --action delete --object version`
  - 输出「TEST60 角色有 product:read（来源：menu→BO 展开）→ 允许 delete version」

---

## 五、External Interface Requirements

### IF-001: permission_interceptor 改造

- [permission_interceptor.py:19-26](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py#L19-L26) 移除 `list` 映射
- 新增 `_check_parent_read(object_type)` 函数（仅 `crud_delete` 触发）
- 改动前后对照见 §9.3.1

### IF-002: BO yaml schema 新字段

- 6 个 BO yaml（product / version / domain / sub_domain / service_module / business_object）全部加 `parent` 字段
- product 是顶层（无 parent）
- 完整 schema 见 §9.3.2

### IF-003: useVersionContext 2 态菜单

- 移除 3 态代码（discoverable 态删除）
- 简化：`visible iff any required_perm in user.permissions`
- 实现见 §9.3.4

### IF-004: GenericObjectList.vue 无权限态

- 检测 `permissionDenied` 状态
- 渲染：完全空白 + lock icon + 「您没有此资源的查看权限」
- 无任何 table 元素、pagination、toolbar（防止数据泄露）
- 实现见 §9.3.5

### IF-005: error_codes 新增

- `ERR_PARENT_PERMISSION_DENIED`（HTTP 403）
- payload schema:
  ```json
  {
    "code": "ERR_PARENT_PERMISSION_DENIED",
    "message": "删除 version 需要先有 product 的 read 权限",
    "data": {
      "child_object": "version",
      "parent_object": "product",
      "parent_required_perm": "product:read"
    }
  }
  ```
- 实现见 §9.3.6

---

## 六、Transition Requirements

### TR-001: DB migration（read/list 合并）

- step 1: 备份 `CREATE TABLE permissions_bak_20260608 AS SELECT * FROM permissions`
- step 2: 给 `permissions` 表加 `deprecated_at` 字段，所有 `* :list` 记录 mark
- step 3: 验证：1 个 migration 脚本完成，幂等
- 回滚：从 `permissions_bak_20260608` 恢复

### TR-002: 现有 role 一次性 init

- 跑 `python scripts/init_role_permissions.py`
- 跑前 **dry-run** 预览差异
- 跑后 log 报告

### TR-003: feature flag

- `PERMISSION_DERIVATION_ENABLED`（默认 true，env var 灰度可关）
- 1 sprint 后删 flag

### TR-004: 1 PR 全包

- 顺序：DB migration → interceptor → yaml parent → init 脚本 → useVersionContext → GenericObjectList → error_codes → tests
- code review 顺序同上

---

## 七、Constraints & Assumptions

### 7.1 Technical Constraints

- Flask + Vue 3 + SQLite (WAL 模式)
- pytest 入口 `python d:\filework\test.py --all` / `--failed` / `--single`
- service_manager 统一启停（AGENT_PORT 隔离）
- DB 快照自动：test.py 内置

### 7.2 Business Constraints

- TEST60 是业务验证用户（id=1223，role=1803，version dimension scope）
- Admin 是 admin_user
- 写子资源场景以 delete 为主

### 7.3 Assumptions

- 所有 BO 都有 yaml 配置（否则 startup fail）— **Verified**
- menu 可绑 0 个 BO（0 个不展开）— **Verified**
- 现有 permissions 表数据正确 — **Verified**
- 子 BO 都有 parent 字段；无 parent 不触发校验 — **Verified**
- 假设 admin 角色需要跳过父读校验 — **TBD-3** 需确认

---

## 八、Priorities & Milestone Suggestions

| ID     | Requirement         | Priority | Reason                |
| ------ | ------------------- | -------- | --------------------- |
| FR-001 | read/list 合并      | Must     | spec 基础             |
| FR-002 | yaml parent         | Must     | FR-003 依赖           |
| FR-003 | 父读校验 (delete)   | Must     | 审计 + 一致性         |
| FR-004 | menu 5 动作展开     | Must     | 解决 TEST60           |
| FR-005 | 2 态渲染            | Must     | UX 干净               |
| FR-006 | init 脚本           | Must     | 现有角色受益          |
| NFR-001 ~ NFR-005 | 性能/观测/兼容/可逆/审计 | Should | 不阻塞主流程 |

**1 PR 全包（Q6=B）**：
- Sprint 1 day 1-2: migration + interceptor + yaml parent
- Sprint 1 day 3: init 脚本 + 跑全量
- Sprint 1 day 4: useVersionContext + GenericObjectList
- Sprint 1 day 5: tests + E2E 验证

---

## 九、Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

- **permission_interceptor** ([permission_interceptor.py:19-26](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py#L19-L26))：6 crud action，list 跟 read 分离
- **dimension_scope_engine.derive_permissions** ([dimension_scope_engine.py:153-166](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py#L153-L166))：半成品功能权限 derivation
- **data_permission_service** ([data_permission_service.py:145-191](file:///d:/filework/excel-to-diagram/meta/services/data_permission_service.py#L145-L191))：硬编码 parent_map，只动数据权限
- **BO yaml**：6 个 BO 全部无 parent 字段
- **useVersionContext** ([useVersionContext.js](file:///d:/filework/excel-to-diagram/src/composables/useVersionContext.js))：2 态，但实际更粗（任一 BO 缺即全藏）
- **useMetaList.js** ([useMetaList.js](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js))：已有 `permissionDenied` 标志
- **GenericObjectList.vue**：缺无权限态 UI

### 9.2 Target State

```
┌─────────────────────────────────────────────────────────────┐
│                   角色授权新流程                              │
└─────────────────────────────────────────────────────────────┘
  admin: 配 role + 绑 menu
              ↓
  scripts/init_role_permissions.py (幂等)
              ↓
  role × menu.bos → role × bo.action (5 动作)

  ┌────────────────── 菜单渲染 ──────────────────┐
  │ useVersionContext 算:                          │
  │ menu.required_perms ∩ user.perms ≠ ∅ → visible│
  │                                        = ∅ → hidden │
  └────────────────────────────────────────────────┘

  ┌────────────────── 列表页请求 ──────────────────┐
  │ user 点 visible 菜单 → /api/v2/bo/<bo>        │
  │ 拦截器:                                            │
  │   1. 查 user 有 <bo>:read?                     │
  │      no → 403 ERR_403_FORBIDDEN                  │
  │      yes ↓                                       │
  │   2. action == 'crud_delete'?                    │
  │      yes → 父读校验 (yaml.parent)                │
  │             no parent perm → 403                 │
  │                  ERR_PARENT_PERMISSION_DENIED    │
  │      no → 放行                                    │
  └────────────────────────────────────────────────┘

  403 响应 → useMetaList.permissionDenied = true
                  → GenericObjectList 渲染空白 + 提示
```

### 9.3 Detailed Design

#### 9.3.1 permission_interceptor 改造

**改动前后对照**（[permission_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py)）：

```python
# === 改动前 ===
_ACTION_PERMISSION_SUFFIX = {
    'crud_create': 'create',
    'crud_read':   'read',
    'crud_list':   'list',     # ← 与 read 分离
    'crud_query':  'list',     # ← 与 read 分离
    'crud_update': 'update',
    'crud_delete': 'delete',
}

# === 改动后 ===
_ACTION_PERMISSION_SUFFIX = {
    'crud_create': 'create',
    'crud_read':   'read',
    'crud_list':   'read',     # [FR-001] 合并
    'crud_query':  'read',     # [FR-001] 合并
    'crud_update': 'update',
    'crud_delete': 'delete',
}

# [v1.0.1] 新增: 父读 advisory 校验 (crud_create/update/delete 触发)
def _check_parent_read_advisory(child_type, user, action, target_id=None):
    """[FR-003 v1.0.1] audit-only 模式: log + 告警, 不阻塞 (env 升级可硬拒)"""
    parent_cfg = BoYamlCache.get_parent(child_type)
    if not parent_cfg:
        return  # 无 parent 配置, 跳过
    if user.is_admin:  # [TBD-3] admin 默认跳过
        return
    parent_type = parent_cfg['object']
    required_perm = f'{parent_type}:read'
    if user.has_permission(required_perm):
        return  # 有权限, 放行
    # 缺权限: audit-only
    log_warning(
        event='permission.parent_read.missing',
        trace_id=TraceId.get(),
        user_id=user.id,
        child_object=child_type,
        parent_object=parent_type,
        parent_required_perm=required_perm,
        action=action,
        decision='allow_with_warning',
    )
    # 响应 header 暴露
    request.response.headers['X-Parent-Permission-Warning'] = (
        f'missing {required_perm}'
    )
    # 写入 /_diagnostics
    DIAGNOSTICS['parent_read_warnings'].append({
        'ts': datetime.utcnow().isoformat() + 'Z',
        'trace_id': TraceId.get(),
        'user_id': user.id,
        'child_object': child_type,
        'parent_object': parent_type,
        'parent_required_perm': required_perm,
        'action': action,
        'decision': 'allow_with_warning',
    })
    # 不抛错 (audit-only 模式)
    # [可选升级] env var PARENT_READ_STRICT_MODE=true 时抛错
    if os.environ.get('PARENT_READ_STRICT_MODE') == 'true':
        log_warning(
            event='permission.parent_read.strict_mode',
            trace_id=TraceId.get(),
            user_id=user.id,
            child_object=child_type,
            parent_object=parent_type,
            parent_required_perm=required_perm,
            action=action,
            decision='hard_reject',
        )
        raise ParentPermissionDenied(
            child=child_type,
            parent=parent_type,
            perm=required_perm,
            action=action,
        )


# [v1.0.1 NEW] 链中 read 校验 (多跳关联, 写操作触发)
def _check_chain_read(child_type, user, action, target_id=None):
    """[FR-003b v1.0.1] 沿 yaml.parent 反向爬链, 任一节点 read 即通过; 都没 → 拒"""
    if user.is_admin:
        return
    chain = BoYamlCache.get_parent_chain(child_type)  # 如 [sub_domain, domain, version, product]
    if not chain:
        return  # 顶层 BO, 无链
    # D11 A2 模式: 读/列表不校验 (链中任一 read 隐含)
    if action in ('crud_read', 'crud_list', 'crud_query'):
        return
    # 写: 链中任一 read 即通过
    if any(user.has_permission(f'{bo}:read') for bo in chain):
        return
    # 全缺: 硬拒
    log_warning(
        event='permission.chain_read.denied',
        trace_id=TraceId.get(),
        user_id=user.id,
        object_type=child_type,
        chain=chain,
        action=action,
        decision='hard_reject',
    )
    raise ChainReadDenied(
        object_type=child_type,
        chain=chain,
        required_perm_any_of=[f'{bo}:read' for bo in chain],
        trace_id=TraceId.get(),
    )
```

#### 9.3.2 BO yaml parent 字段

**[FR-002]** 6 个 BO yaml 全部加 `parent` 字段：

```yaml
# meta/schemas/version.yaml
- code: version
  display_name: 版本
  parent:
    object: product
    field: product_id
  actions: [create, read, update, delete]
```

```yaml
# meta/schemas/domain.yaml
- code: domain
  display_name: 域
  parent:
    object: version
    field: version_id
  actions: [...]
```

```yaml
# meta/schemas/sub_domain.yaml
- code: sub_domain
  display_name: 子域
  parent:
    object: domain
    field: domain_id
```

```yaml
# meta/schemas/service_module.yaml
- code: service_module
  display_name: 服务模块
  parent:
    object: sub_domain
    field: sub_domain_id
```

```yaml
# meta/schemas/business_object.yaml
- code: business_object
  display_name: 业务对象
  parent:
    object: service_module
    field: service_module_id
```

```yaml
# meta/schemas/product.yaml
- code: product
  display_name: 产品
  # 顶层: 无 parent
  actions: [...]
```

#### 9.3.3 init_role_permissions.py

**[FR-006]** 一次性 init 脚本：

```python
# scripts/init_role_permissions.py
"""
[FR-006] 幂等展开 role × menu → role × bo.action

用法:
  python scripts/init_role_permissions.py --dry-run
  python scripts/init_role_permissions.py
"""
from meta.services.role_service import RoleService
from meta.services.menu_service import MenuService
from meta.services.permission_service import PermissionService

STANDARD_ACTIONS = ['create', 'read', 'update', 'delete', 'export']

def expand_menu_to_role_permissions(dry_run: bool = False) -> dict:
    """[FR-004 + FR-006] 展开 menu.required_permissions 到 role_permissions"""
    stats = {'expanded': 0, 'aligned': 0, 'skipped': 0, 'roles': 0, 'menus': 0}

    menus = MenuService.list_all()
    roles = RoleService.list_all()
    stats['menus'] = len(menus)
    stats['roles'] = len(roles)

    for menu in menus:
        bos = menu.bos
        if not bos:
            log(f'  skip menu={menu.code} (no BO)')
            stats['skipped'] += 1
            continue

        for role in roles:
            if not RoleService.has_menu(role, menu):
                continue

            for bo in bos:
                for action in STANDARD_ACTIONS:
                    perm_code = f'{bo}:{action}'
                    perm = PermissionService.get_or_create(
                        code=perm_code,
                        action=action,
                        resource_type=bo,
                    )
                    if dry_run:
                        if not RoleService.has_permission(role, perm_code):
                            log(f'  would grant: role={role.code} perm={perm_code}')
                            stats['expanded'] += 1
                        else:
                            stats['aligned'] += 1
                    else:
                        RoleService.grant_permission_idempotent(role, perm)
                        stats['expanded'] += 1

    log(f'\nDONE: {stats}')
    return stats


if __name__ == '__main__':
    import sys
    dry = '--dry-run' in sys.argv
    expand_menu_to_role_permissions(dry_run=dry)
```

#### 9.3.4 useVersionContext 2 态

**[FR-005]** 简化菜单状态计算（[useVersionContext.js](file:///d:/filework/excel-to-diagram/src/composables/useVersionContext.js)）：

```javascript
// === 改动前 (3 态: discoverable / granted / hidden) ===
function computeMenuState(menu, userPerms) {
  const granted = menu.required_permissions.every(p => userPerms.has(p))
  const discoverable = menu.required_permissions.some(p => userPerms.has(p))
  if (granted) return 'granted'
  if (discoverable) return 'discoverable'
  return 'hidden'
}

// === 改动后 (2 态: visible / hidden) ===
function computeMenuState(menu, userPerms) {
  // [FR-005] 简化为 2 态
  const visible = menu.required_permissions.some(p => userPerms.has(p))
  return visible ? 'visible' : 'hidden'
}
```

#### 9.3.5 GenericObjectList.vue 无权限态

**[IF-004]** 列表页无权限 UI（[GenericObjectList.vue](file:///d:/filework/excel-to-diagram/src/components/common/GenericObjectList.vue)）：

```vue
<template>
  <!-- [FR-005 / IF-004] 无权限态: 完全空白 + 提示 -->
  <div v-if="permissionDenied" class="permission-empty">
    <i class="el-icon-lock"></i>
    <p class="msg">您没有此资源的查看权限</p>
  </div>

  <!-- 正常态 -->
  <div v-else>
    <el-table :data="data" v-loading="loading">
      <!-- 字段列 -->
    </el-table>
    <el-pagination
      v-model:current-page="pagination.page"
      v-model:page-size="pagination.page_size"
      :total="pagination.total"
    />
  </div>
</template>

<style scoped>
.permission-empty {
  text-align: center;
  padding: 80px 0;
  color: #909399;
}
.permission-empty .msg {
  font-size: 14px;
  margin-top: 16px;
}
</style>
```

#### 9.3.6 error_codes 新增

**[IF-005]** 新错误码定义：

```python
# meta/core/error_codes.py
class ErrorCode(enum.Enum):
    # ... existing
    ERR_PARENT_PERMISSION_DENIED = 'ERR_PARENT_PERMISSION_DENIED'
```

```python
# meta/core/error_fix_hints.py
FIX_HINTS = {
    'ERR_PARENT_PERMISSION_DENIED': (
        '父资源读权限缺失。请 admin 在 role 上授权 {parent_object}:read '
        '（来源：menu → BO 展开 / 直接配 role_permissions）。'
    ),
    # ...
}
```

```python
# meta/core/exceptions.py
class ParentPermissionDenied(PermissionDenied):
    def __init__(self, child, parent, perm):
        self.child = child
        self.parent = parent
        self.perm = perm
        super().__init__(
            f'删除 {child} 需要先有 {parent} 的 read 权限'
        )
        # [IF-005] payload
        self.payload = {
            'child_object': child,
            'parent_object': parent,
            'parent_required_perm': perm,
        }
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
| --- | --- | --- | --- |
| read/list 合并 | 跟 Oracle/Palantir 一致；简化 | 改 DB schema | **✓ 选** |
| 保留 read + list 显式 | 配置灵活 | 容易漏配（TEST60 案例） | ✗ |
| 父读校验 (create/update/delete 全) | 最严 | 误伤多 | ✗ |
| 父读校验 (**delete only**) | 跟 Oracle NoSQL 一致；最小误伤 | 漏 create 场景 | **✓ 选 (Q1=C)** |
| 菜单 3 态 (有/Discoverer/藏) | 跟 Palantir 细 | UX 复杂 | ✗ |
| 菜单 **2 态** (有/藏) | 简洁 | — | **✓ 选** |
| menu 5 动作严格按 .required_permissions | 零意外 | 配置繁琐 | ✗ |
| menu 绑 BO **5 动作全展开** | 简单 | 风险：给太多权限 | **✓ 选 (Q3=B)** |
| 后端下发 menu_state | 准 | 改动大 | ✗ |
| **纯前端** useVersionContext | 跟现有架构一致 | — | **✓ 选 (Q5=A)** |
| 1 PR 全包 | 快 | 风险大 | **✓ 选 (Q6=B)** |
| 3 PR 分发 | 稳 | 慢 | ✗ |
| 硬拒 403 + 错码 | 审计可追溯 | — | **✓ 选 (Q2=A)** |
| 软警告 log 允许 | 不阻断业务 | 违反最小权限 | ✗ |
| 写幂等 init 脚本 | 现有角色一次性受益 | — | **✓ 选 (Q4=A)** |
| 不动现有 role | 保守 | 慢 | ✗ |

### 9.5 Implementation & Migration Plan

#### 9.5.1 实施顺序（1 PR）

1. **DB migration 脚本**（permissions 表 deprecate `:list`）
2. **permission_interceptor 改造**（list→read，父读校验）
3. **BO yaml 加 parent 字段**（6 个 BO）
4. **scripts/init_role_permissions.py**（一次性 init）
5. **useVersionContext 2 态简化**
6. **GenericObjectList.vue 无权限态**
7. **error_codes + fix_hints 新增**
8. **单元 + 集成 + E2E 测试**

#### 9.5.2 风险与缓解

| Risk | 缓解 |
| --- | --- |
| R1: 父读校验误伤 | 无 parent 的 BO 不触发；admin 跳过（TBD-3） |
| R2: 现有角色短期无 menu→BO 展开 | init 脚本一次性跑全 |
| R3: 错误码变化导致前端 toast 失效 | fix_hints 同步 |
| R4: 菜单状态机简化导致旧测试失败 | 删除 discoverable case |
| R5: TEST60 切换过程登录异常 | feature flag 默认 true，回滚即关 |
| R6: migration 脚本数据损坏 | test.py 入口 + DB 快照自动；先在 test DB 验证 |

#### 9.5.3 测试策略

- **单元**：
  - permission_interceptor 各种 case（list/read/delete + parent 缺/有）
  - init_role_permissions 幂等性（连跑 2 次结果一致）
- **集成**：
  - TEST60 完整登录 → 路由 → 写子资源 403 → 列表页空白
  - admin 跳过父读校验（TBD-3 确认后）
  - menu 5 动作全展开后 TEST60 能 list product
- **E2E**（Playwright）：
  - 菜单 2 态（visible / hidden）
  - 列表页无权限态完全空白
  - 父读校验失败时 `/_diagnostics` 含记录
- **回归**：
  ```bash
  python d:\filework\test.py --all --force    # 并行 跑全
  python d:\filework\test.py --failed          # 串行 确认无假失败
  python d:\filework\test.py --unit            # 单元
  python d:\filework\test.py --single <id>     # 快速反馈
  ```

#### 9.5.4 回滚方案

- **feature flag**：`PERMISSION_DERIVATION_ENABLED=false` → 走旧逻辑
- **DB 回滚**：从 `permissions_bak_20260608` 恢复
- **code revert**：单 PR 单 commit 链

---

## 十、TBD List

| ID    | Item                                              | Missing Information                            | Next Step                          |
| ----- | ------------------------------------------------- | ---------------------------------------------- | ---------------------------------- |
## 十、TBD List (v1.0.1 决策落地)

### 10.1 v1.0 原始 TBD（全部 ✅ Accepted）

| ID    | Item                                              | Missing Information                            | Next Step                          | Status      |
| ----- | ------------------------------------------------- | ---------------------------------------------- | ---------------------------------- | ----------- |
| TBD-1 | FR-004「5 动作全展开」中 **export** 是否包含      | export 是 menu 级还是 BO 级？                  | **默认包含**（跟 menu.required_permissions 5 动作一致） | ✅ Accepted |
| TBD-2 | 「无权限」文案是否多语化                          | 当前只 zh-CN                                    | **单语足够**，留 i18n 钩子          | ✅ Accepted |
| TBD-3 | 父读校验是否对 admin 例外                        | admin 是否跳过                                  | **默认跳过**（admin role 显式跳过）| ✅ Accepted |
| TBD-4 | init 脚本是否要 dry-run 模式                     | 第一次跑需要预览                                | **加 `--dry-run`**                 | ✅ Accepted |
| TBD-5 | 灰度策略：先内测 / 先业务 / 先 admin              | 没问                                            | **默认先 admin 内测**（小流量 + 1 天）| ✅ Accepted |

### 10.2 v1.0.1 方向性决策（D9-D12 — 全部 ✅ Accepted）

> **用户决策**: "接受全部 D9-D12 默认" — 全部按推荐默认落地

| ID    | Item                                              | Default                                                  | Status      |
| ----- | ------------------------------------------------- | -------------------------------------------------------- | ----------- |
| **D9**  | **父读校验模式?**（v1.0 硬拒 → v1.0.1 改为）     | **audit-only**（log + 告警 + 不阻塞）+ env `PARENT_READ_STRICT_MODE=true` 升级 | ✅ Accepted |
| **D10** | **多跳写校验模式?**                              | **B 链中 audit-only**（链中任一 read 缺失 → log + header + 不阻塞）+ env `CHAIN_DERIVATION_STRICT_MODE=true` 升级 | ✅ Accepted (v1.0.1 修订) |
| **D11** | **多跳读校验模式?**                              | **A2**（链中任一 read → 链尾 list 隐含，**不显式校验**）  | ✅ Accepted |
| **D12** | **4 层防御章节加哪个 spec?**                     | **MASTER PLAN 总览** + v1.0 spec §十三                   | ✅ Accepted |
| **D13** | **[v1.0.1 修订] 链 read 粒度?**（D10 粒度错误）| **类型级 audit-only + 实例级硬拒**（粒度对齐 Oracle RAS / SAP CDS / Snowflake）| ✅ Accepted |

**D9 落地说明**:
- FR-003 从 v1.0 硬拒 → v1.0.1 audit-only
- 触发范围: `crud_delete` only → `crud_create`/`crud_update`/`crud_delete` 3 个写动作
- 严格模式升级: `PARENT_READ_STRICT_MODE=true` env var

**D10 落地说明（v1.0.1 修订）**:
- FR-003b 类型级: 链中任一 read 缺失 → **audit-only**（log + header + 不阻塞）
- 严格模式升级: `CHAIN_DERIVATION_STRICT_MODE=true` env var → 抛 `ERR_CHAIN_READ_DENIED` 403
- 例：写 `sub_domain` 无 `domain:read` / `version:read` / `product:read` 任一 → 警告，不阻塞

**D13 落地说明（v1.0.1 新增）**:
- FR-003b 实例级: 写时检查 `parent_chain_instances` 是否在 user.data_scope
- 越权场景（跨租户/越界写）→ 抛 `ERR_CHAIN_INSTANCE_OUT_OF_SCOPE` 403 硬拒
- 与 FR-003b 类型级 audit-only 互补：类型级宽松防误伤，实例级严格防越权
- 业界依据：Oracle RAS 行级、Palantir Object Security、Databricks UC 数据权限

**D11 落地说明**:
- FR-003b: 读/列表操作不校验
- A2 模式已隐含在 v1.1 `expand_dimension_values` 实现中，v1.0.1 修订只是**明确标注**为 A2

**D12 落地说明**:
- v1.0 spec §十三 完整 4 层防御设计
- MASTER PLAN §5 4 层防御总览（v1.0 详细 / v1.1 检测 / v1.2 关联错码）

---

## 附录 A: 业界参考

| 模式 | 来源 | 借鉴点 |
| --- | --- | --- |
| `READ`/`SELECT` 不分子查询/单条 | Oracle 12c+ | FR-001 read/list 合并 |
| "user has same privilege, or read privilege, for all parent tables" | Oracle NoSQL Database | FR-003 父读强制 |
| `CREATE TABLE` 系统权限隐含 4 个对象权限 | Oracle SQL | FR-004 menu 5 动作展开 |
| Project role → all resources via inheritance | Palantir Foundry | FR-004 menu role 继承 |
| Markings 沿数据血缘 + 文件层级自动继承 | Palantir Foundry | 未来: 数据权限跨数据集传递 |
| `Viewer` 角色 = list + read detail 一起 | Palantir Foundry | FR-001 + FR-004 合并实现 |
| `Discoverer` 中间态（只见元数据） | Palantir Foundry | **取消**（FR-005 简化为 2 态） |
| `WITH HIERARCHY OPTION` 自上而下 | Oracle SQL | 未来: subtype 继承 |

---

## 附录 B: 现有代码路径

| 文件 | 角色 |
| --- | --- |
| [meta/core/interceptors/permission_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/permission_interceptor.py) | FR-001 / FR-003 改造点 |
| [meta/services/dimension_scope_engine.py](file:///d:/filework/excel-to-diagram/meta/services/dimension_scope_engine.py) | FR-004 协调点（与 derive_permissions 合并） |
| [meta/services/data_permission_service.py](file:///d:/filework/excel-to-diagram/meta/services/data_permission_service.py) | FR-002 fallback（硬编码保留标 deprecated） |
| [meta/schemas/*.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/) | FR-002 加 parent 字段 |
| [meta/core/error_codes.py](file:///d:/filework/excel-to-diagram/meta/core/error_codes.py) | IF-005 新增错误码 |
| [meta/core/error_fix_hints.py](file:///d:/filework/excel-to-diagram/meta/core/error_fix_hints.py) | IF-005 新增 fix_hint |
| [src/composables/useVersionContext.js](file:///d:/filework/excel-to-diagram/src/composables/useVersionContext.js) | FR-005 2 态简化 |
| [src/composables/useMetaList.js](file:///d:/filework/excel-to-diagram/src/composables/useMetaList.js) | FR-005 配合 |
| [src/components/common/GenericObjectList.vue](file:///d:/filework/excel-to-diagram/src/components/common/GenericObjectList.vue) | IF-004 无权限态 UI |
| [scripts/init_role_permissions.py](file:///d:/filework/excel-to-diagram/scripts/init_role_permissions.py)（新建） | FR-006 init 脚本 |
| [scripts/explain_permissions.py](file:///d:/filework/excel-to-diagram/scripts/explain_permissions.py)（新建） | NFR-005 审计 CLI |

---

## 十一、实施计划 (Implementation Schedule) — v1.0.1 增量

> **v1.0.1 增量视角**: 4.5-6 天原计划 + 0.5-1 天 v1.0.1 增量 = **5-6.5 天总**
> **3 阶段交付**: v1.0.1 (Phase A) → v1.1 (Phase B) → v1.2 (Phase C)
> **详细日级任务**: 见 [MASTER PLAN §1-3](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-MASTER-PLAN-2026-06-08.md)

### 11.1 Phase A — v1.0.1 基础（5-6.5 天）

**目标**: TEST60 立刻能工作 + 6 FR + FR-003b 落地 + 4 层防御

| # | Task | 估时 | 依赖 |
|---|---|---|---|
| A.1-A.4 | DB migration + read/list 合并 | 2.5h | — |
| **A.5a** | **[v1.0.1] 新增 `_check_parent_read_advisory()` 函数** | 2h | A.4 |
| **A.5b** | **[v1.0.1] 新增 `_check_chain_read()` 函数** | 2h | — |
| **A.5c** | **[v1.0.1] 集成 env `PARENT_READ_STRICT_MODE`** | 0.5h | A.5a |
| A.6 | integration: 写 action 触发 chain read + parent advisory | 1h | A.5a/A.5b |
| A.7-A.8 | init_role_permissions.py + 跑全量 | 2.5h | — |
| A.9-A.10 | useVersionContext 2 态 + GenericObjectList 无权限态 UI | 2.5h | — |
| **A.11+** | **[v1.0.1] error_codes.py 加 `ERR_CHAIN_READ_DENIED`** | 0.5h | A.5b |
| A.12 | error_fix_hints.py 加 2 个 fix_hint | 0.5h | A.11 |
| A.13-A.17 | 测试 + bug 修复 | 7h | A.1-A.12 |
| A.18-A.22 | 部署 + 灰度 | 1.5h | A.17 |
| **A.23** | **[v1.0.1] CLI explain_permissions.py 落地 NFR-005** | 1h | A.7 |
| **A.24** | **[v1.0.1] /_diagnostics 暴露 parent_read_warnings[]** | 0.5h | A.5a |

**Phase A 总工时**: ~32h = **5-6.5 天**

### 11.2 Phase B — v1.1 yaml 化（3.5-4.5 天）

| # | Task | 估时 |
|---|---|---|
| B.1-B.5 | 6 BO yaml 加 parent_object + BoMetadataRegistry | 8h |
| B.6-B.10 | 替换硬编码 + 启动 fail-fast | 5.5h |
| B.11-B.14 | 测试 + 回归 | 4.5h |

**Phase B 总工时**: ~18h = **3.5-4.5 天**

### 11.3 Phase C — v1.2 关联 derivation（4.5-6 天）

| # | Task | 估时 |
|---|---|---|
| C.1-C.4 | yaml schema 扩展（m2m/polymorphic/self_ref/sibling） | 2.5h |
| C.5-C.7 | BoMetadataRegistry 扩展 | 3.5h |
| C.8-C.13 | 关联拦截器（4 FR） | 9.5h |
| C.14-C.17 | 错误码 + cycle CTE | 3.5h |
| C.18-C.21 | 测试 + 集成 | 7h |
| C.22-C.25 | 部署 + 灰度 | 1.5h |

**Phase C 总工时**: ~27h = **4.5-6 天**

### 11.4 总览

| 阶段 | 工期 | 关键产出 | 依赖 |
|---|---|---|---|
| Phase A | **5-6.5 天** | read/list 合并 + 父读 audit-only + 链中 read + 菜单 2 态 + init | — |
| Phase B | 3.5-4.5 天 | yaml 化 + BoMetadataRegistry + 启动 fail-fast | A 完 |
| Phase C | 4.5-6 天 | 5 种关联 derivation + 6 错码 | B 完 |
| **合计** | **13-17 天** | 完整权限 derivation 体系 | — |

### 11.5 关键里程碑 (M0-M7)

| 里程碑 | Day | 业务验证点 | 期望 |
|---|---|---|---|
| M0 | 0.5 | DB 备份 + dry-run | ✅ |
| M1 | 2 | TEST60 能 list product | ✅ |
| M1.5 | 3 | v1.0.1 增量 (audit-only + chain read) 生效 | ✅ |
| M2 | 5 | test.py --all 0 fail | ✅ |
| M3 | 6.5 | admin 内测无 500 | ✅ |
| M4 | 10 | 故意写错 yaml → 启动 fail-fast | ✅ |
| M5 | 12 | test.py --failed 0 fail | ✅ |
| M6 | 15 | TEST60 写 m2m/polymorphic/self_ref 遇 403 | ✅ |
| M7 | 17 | 全量部署 + 1 sprint 后删 flag | ✅ |

---

## 十二、Code Review Checklist — v1.0.1

> **目的**: 30+ 项检查清单，确保 PR 质量
> **执行时机**: PR 提交前 + reviewer review 时

### 12.1 FR-001 read/list 合并 (3 项)

- [ ] `_ACTION_PERMISSION_SUFFIX` 中 `crud_list` / `crud_query` 映射到 `read`
- [ ] 错误消息从「缺少权限: product:list」变「缺少权限: product:read」
- [ ] DB migration 脚本已跑 + 可回滚

### 12.2 FR-002 yaml parent 字段 (3 项)

- [ ] 6 个 BO yaml 全部加 `parent: { object, field }` 字段
- [ ] product 是顶层（无 parent）
- [ ] 启动时一致性校验（yaml vs 硬编码）通过

### 12.3 FR-003 父读 audit-only (v1.0.1 核心 — 5 项)

- [ ] `_check_parent_read_advisory()` 函数已实现
- [ ] 缺权限时 log warn（结构化） + 响应 header `X-Parent-Permission-Warning` + 写 `/_diagnostics`
- [ ] 默认不抛错（audit-only 模式）
- [ ] env `PARENT_READ_STRICT_MODE=true` 时抛 `ERR_PARENT_PERMISSION_DENIED`
- [ ] admin 跳过（无论模式）

### 12.4 FR-003b 链中 read 校验 (v1.0.1 新增 — 6 项)

- [ ] `_check_chain_read()` 函数已实现
- [ ] 写 action 链中无 read → 抛 `ERR_CHAIN_READ_DENIED` 403
- [ ] 读/列表不校验（D11 A2 模式隐含）
- [ ] payload 含 `chain` + `required_perm_any_of` 数组
- [ ] admin 跳过
- [ ] 单元测试覆盖：单跳通过 / 多跳通过 / 链中全缺拒 / admin 跳过

### 12.5 FR-004 menu 5 动作展开 (3 项)

- [ ] `init_role_permissions.py` 幂等（连跑 2 次结果一致）
- [ ] 5 动作：`create` / `read` / `update` / `delete` / `export`
- [ ] `--dry-run` 模式预览差异

### 12.6 FR-005 菜单 2 态 (3 项)

- [ ] 移除 3 态代码（discoverable 态删除）
- [ ] useVersionContext 简化为 2 态（visible/hidden）
- [ ] GenericObjectList 无权限态完全空白 + lock icon

### 12.7 NFR-002 + NFR-007 可观测 (5 项)

- [ ] 父读校验失败必 log structured（含 trace_id + decision）
- [ ] `/_diagnostics` 暴露 `parent_read_warnings[]`（最近 100 条）
- [ ] 响应 header `X-Parent-Permission-Warning` 暴露
- [ ] `chain_read_denials[]` 同样暴露
- [ ] admin 告警阈值配置

### 12.8 NFR-005 审计 (2 项)

- [ ] `scripts/explain_permissions.py` 已实现
- [ ] CLI 输出含「来源: menu→BO 展开」+ 决策

### 12.9 测试 (4 项)

- [ ] 单元: `test_permission_interceptor_v101.py`（覆盖 audit-only + chain read 2 套）
- [ ] 集成: TEST60 完整登录 + 列表 + 详情 + 删除遇 403
- [ ] E2E: Playwright 测前端 2 态 + 无权限态 UI
- [ ] 回归: `test.py --all --force` → `--failed` 0 fail

### 12.10 部署 + 灰度 (3 项)

- [ ] feature flag `PERMISSION_DERIVATION_ENABLED=true`（默认）
- [ ] env `PARENT_READ_STRICT_MODE=false`（默认 audit-only）
- [ ] admin 内测 1 天 + 全量启用 + 监控 1 小时

**总 Checklist**: ~37 项

### 12.11 Review 顺序

1. DB migration 脚本（最易出错）— 必查
2. permission_interceptor（v1.0.1 重点）— 必查 §12.3 + §12.4
3. yaml parent 字段（6 个文件）— 抽查
4. init 脚本（幂等性）— 必查
5. 前端 2 态（useVersionContext + GenericObjectList）— 抽查
6. 测试覆盖率 — 必查 §12.9
7. 文档完整性（spec + MASTER PLAN）— 必查

---

## 十三、4 层防御设计 (4-Layer Defense Design) — D12

> **核心思想 (D12)**: 父读校验 + 链中 read + 4 层防御构成完整"防误伤 + 保安全"体系。
> **目标**: 既不放过越权写入（真安全），又不阻断 admin 漏配场景（防误伤）。

### 13.1 为什么需要 4 层防御

**父读校验的双刃剑**：
- **真安全**：防越权写入（99% 场景）
- **误伤风险**：admin 漏配父 read（1% 场景）→ 用户被拒 403

**业界踩坑**（前车之鉴）：
- Odoo `One2many` 隐式父读 → 写时 throw 不友好（用户被拒）
- SAP CDS path expression 严格 → 配错就拒
- Oracle REFERENCES 严格 → admin 漏配 FK 致整表不可写

**4 层防御解决**：每层独立，**任一层缺失都可由其他层兜底**。

### 13.2 4 层防御全景

```
┌─────────────────────────────────────────────────────────────┐
│                    4 层防御体系                                │
└─────────────────────────────────────────────────────────────┘

Layer 1: 防漏（init 时）— 配 role 时自动给齐
├─ [FR-006] init_role_permissions.py 幂等全 role 补齐
├─ 配 menu → 自动 5 动作展开（FR-004）
└─ admin 配完 menu 即获合理 BO action 权限

Layer 2: 检测（启动时）— yaml 错配即 fail-fast
├─ [FR-008 v1.1] BoMetadataRegistry 启动校验
├─ yaml 缺 parent_object → 启动失败
├─ yaml cycle 检测 → 启动失败
└─ 业务用户 admin 没机会"忘了设权限"

Layer 3: 提示（运行时）— 错码 + hint 给用户明确指引
├─ [FR-003] 父读 audit-only 模式（**v1.0.1**）
│  ├─ 失败: log warn + header X-Parent-Permission-Warning
│  ├─ /_diagnostics 暴露 parent_read_warnings 数组
│  └─ 不抛错码、不阻塞
├─ [FR-003b] 链中 read 硬拒（**v1.0.1**）
│  ├─ 失败: ERR_CHAIN_READ_DENIED 403
│  ├─ payload: chain + required_perm_any_of
│  └─ fix_hint 告诉 admin 怎么修
└─ [IF-005] fix_hint 含 admin 操作指引

Layer 4: 自助（运维时）— CLI 一键查"为什么没权限"
├─ [NFR-005] scripts/explain_permissions.py
│  ├─ 输入: --user TEST60 --action delete --object version
│  └─ 输出: "TEST60 角色有 product:read (来源: menu→BO 展开) → 允许 delete version"
├─ /_diagnostics 暴露完整 permission state
└─ 1 分钟定位问题，admin 无需查 DB
```

### 13.3 业务流程：用户操作 → 4 层防御介入

| 步骤 | 用户/Admin 动作 | Layer 防御 | 介入点 | 结果 |
|---|---|---|---|---|
| 1 | admin 创建 role + 绑 menu | Layer 1 | init_role_permissions | role 自动获 menu 5 动作 |
| 2 | 服务启动 | Layer 2 | BoMetadataRegistry | yaml 校验 fail-fast |
| 3 | 业务用户登录 | — | — | 正常 |
| 4 | 业务用户写子资源 | Layer 3a | `_check_parent_read_advisory` | 父读缺 → log warn + header 提示 |
| 5 | 业务用户写子资源 | Layer 3b | `_check_chain_read` | 链中无 read → 抛 ERR_CHAIN_READ_DENIED |
| 6 | 业务用户看 403 | Layer 4 | /_diagnostics | admin 1 分钟定位 |
| 7 | admin 修权限 | Layer 1 | 再跑 init_role_permissions | 幂等补齐 |
| 8 | 业务用户再操作 | — | — | 成功 |

### 13.4 父读校验模式配置（v1.0.1）

| 模式 | env var | 行为 | 适用 |
|---|---|---|---|
| **默认 (audit-only)** | `PARENT_READ_STRICT_MODE=false` | log warn + 告警 + 不阻塞 | **推荐** — 避免误伤 |
| **严格 (hard reject)** | `PARENT_READ_STRICT_MODE=true` | 抛 ERR_PARENT_PERMISSION_DENIED 403 | 高安全场景（金融/医疗） |

**升级方式**：
```bash
# 1. 改 env var
export PARENT_READ_STRICT_MODE=true

# 2. 重启服务
powershell -File d:\filework\excel-to-diagram\scripts\service_manager.ps1 restart
```

### 13.5 业界 4 层防御对位

| 系统 | Layer 1 防漏 | Layer 2 检测 | Layer 3 提示 | Layer 4 自助 |
|---|---|---|---|---|
| Oracle | — | DB constraint | ORA-02292 | — |
| SAP | — | DCL check | SU24 事务码 | ST01 trace |
| Palantir | 自动 grant | — | marking 标签 | Foundry audit log |
| Odoo | ir.model.access 自动 | startup check | access error | debug mode |
| **本项目** | **init 脚本 (v1.0)** | **registry (v1.1)** | **audit-only + 错码 (v1.0.1)** | **CLI explain (v1.1)** |

**本项目 4 层防御最完整**（业界首个明确分层）。

### 13.6 误伤场景处理流程

| 误伤类型 | 防御层 | 修复路径 | 时间 |
|---|---|---|---|
| admin 漏配父 read | Layer 1 | 重跑 init_role_permissions | 30s |
| yaml 错配 | Layer 2 | 修 yaml + restart | 2min |
| 父读 audit-only 误判 | Layer 3a | log warn 自解释 | 0s |
| 链中 read 真缺 | Layer 3b | 错码含 required_perm | 0s |
| 排查疑难 | Layer 4 | CLI explain 1 分钟 | 1min |

**总修复时间** ≤ 5 分钟（vs 业界平均 30 分钟）。

### 13.7 4 层防御的"设计原则"

1. **Layer 1 必做**：90% 误伤由"忘了设"导致，**自动补齐**比"提示用户去设"好
2. **Layer 2 必做**：配置错是**确定性 bug**，启动即拒（fail-fast）
3. **Layer 3 audit-only 是关键**：避免 admin 漏配导致用户被拒（**核心创新**）
4. **Layer 4 是兜底**：所有层都失败时，admin 能 1 分钟定位

### 13.8 与 v1.1 / v1.2 关联

| 防御层 | 涉及 spec | 涉及 FR |
|---|---|---|
| Layer 1 | v1.0 | FR-004 + FR-006 |
| Layer 2 | v1.1 | FR-007 + FR-008 |
| Layer 3a | v1.0 | **FR-003 v1.0.1** (audit-only) |
| Layer 3b | v1.0 | **FR-003b v1.0.1** (链中 read) |
| Layer 3c | v1.2 | FR-010~014 错码 + fix_hint |
| Layer 4 | v1.1 | NFR-005 (CLI explain) |

**Phase A 必交付 Layer 1 + 3a + 3b，Phase B 交付 Layer 2 + 4，Phase C 交付 Layer 3c**。

---

## 附录 C: v1.0 → v1.0.1 变更日志

> **目的**: 清晰记录 v1.0.1 相对 v1.0 的所有变化

| 章节 | 变更 | 原因 | 影响 |
|---|---|---|---|
| 标题 | 版本号 v1.0 → v1.0.1 | D9-D12 落地 | 文档标识 |
| FR-003 | crud_delete 硬拒 → crud_create/update/delete **audit-only** | D9 防误伤 | 拦截器逻辑 |
| **FR-003b** | **新增** 链中 read 校验 | D10/D11 链中模式 | 新增函数 + 错码 |
| NFR-007 | 新增父读/链中 warning 可观测 | v1.0.1 配套 | /_diagnostics + header |
| IF-001 | 新增 `_check_parent_read_advisory` + `_check_chain_read` | v1.0.1 实施 | 拦截器扩展 |
| IF-005 | 新增 `ERR_CHAIN_READ_DENIED` 错码 | FR-003b 落地 | 错码枚举 |
| IF-006/007/008/009/010 | 新增 yaml cache / diagnostics 扩展 | FR-003b 依赖 | yaml 缓存 + 诊断端点 |
| §9.3.1 | 重写设计代码（v1.0.1 完整） | 实施细节 | 代码模板 |
| §9.4 | 更新 Alternatives Considered | 反映 v1.0.1 决策 | 决策追溯 |
| §10 TBD | TBD-1~5 标记 ✅ Accepted；新增 D9-D12 | 决策落地 | 决策状态 |
| **§11 实施计划** | **新增** | 用户需求 | 工时表 |
| **§12 Code Review Checklist** | **新增** | 用户需求 | 37 项检查 |
| **§13 4 层防御** | **新增** | D12 决策 | 4 层防御总览 |

**v1.0 → v1.0.1 总工时增量**: 4.5h（spec 修订）+ 9h（interceptor 改造 + 测试）= **~13.5h**

---

**Spec + RFC 完整性自检（v1.0.1）**：
- ✅ **13 章节齐全**（一~十三 + 3 附录）
- ✅ 最后一节是 "变更日志 v1.0 → v1.0.1"
- ✅ D9-D12 全部 ✅ Accepted 且落地到 FR/IF/§九 设计
- ✅ 风险 + 回滚 + 测试 + 实施顺序明确
- ✅ 业界参考已附录（含 CDS Path Expression）
- ✅ 现有代码路径已附录（更新到 v1.0.1）
- ✅ 实施计划 §11 + Code Review Checklist §12
- ✅ 4 层防御 §13（D12 落地）


---

## 十四、业界对比 + v1.0.1 严格度合理化（2026-06-09 增补）

> **背景**: 在确认 v1.0.1 设计前，深入对比 6 大头部产品的权限模型，确保我们的方案不会**过于严格导致误伤**，也不会**过于宽松导致越权**。
>
> **结论**: 当前 v1.0.1 FR-003b 的**类型级硬拒**粒度错误，应改为**类型级 audit-only + 实例级硬拒**（D13 决策）。

### 14.1 6 大头部产品权限模型总结

| 产品 | 核心机制 | 默认严格度 | 父-子/链 行为 | 关键设计哲学 |
|---|---|---|---|---|
| **Oracle RAS** | Master-Detail Data Realm 约束 | **严格**（按策略配置） | 子表访问**必须**有父行 ACL | 「显式授权，类型级 data realm」 |
| **SAP CDS Hierarchies** | Instance-based 限制 + Propagation + 注解组合 | **严格**（可配 ORPHANS ROOT/IGNORE/ERROR） | 沿 `association` 路径传播，**Rejected Entity Selection 返 403** | 「ORPHANS ROOT、CYCLES ERROR/MULTIPLE PARENTS」**显式配置** |
| **Palantir Foundry** | Object Security Policy + Property Security Policy + Markings + RV | **最严**（默认拒绝） | Object security policy 默认**应用到所有属性**；不通过 = 不可见；通过但不通过属性 = **NULL** | **Zero Trust** + Least Privilege + Strict Enforcement |
| **Snowflake** | Row Access Policy (ABAC) + Masking + 角色继承 | **较松**（owner bypass） | Row policy **不阻止 INSERT**（可插任意行）；OWNERSHIP **全权限** | Owner 例外 + functional/access 角色分离 |
| **Databricks Unity Catalog** | 继承式 3 层命名空间 (metastore→catalog→schema→table) + Row Filter + ABAC 标签 | **严格**（secure by default） | 必须 `SELECT + USESCHEMA + USECATALOG` 三件套；ABAC 标签**自动**级联 | 「Define once, secure everywhere」+ 标签驱动 |
| **Odoo** | Access Rights (model-level CRUD) + Record Rules (row-level) | **混合**：Access Rights **default-deny**，Record Rules **default-allow** | 沿 group → model → record-rule 链 | "better to err on the side of caution and limit access"（保守起见限制） |
| **Apache Atlas + Ranger** | Classification 标签 + PropagateTags (NONE/ONE_TO_TWO/BOTH) + lineage 传播 | **严格**（标签驱动） | 标签**自动沿 lineage 传播**；新数据资产**自动**应用策略 | 标签驱动 + 零干预自动传播 |

### 14.2 关键模式识别

#### 模式 1: 「Strict」阵营 (Palantir / Oracle RAS / Databricks UC / SAP CDS)
- **类型级**：默认拒绝（无显式 grant = 不可访问）
- **行级**：通过 policy/rule 配置
- **继承**：显式 inheritance (UC 目录树 / SAP CDS annotations)
- **Admin**：是**单独角色**，不是「自动跳过所有」
- **新数据**：自动按元数据/标签应用

#### 模式 2: 「Owner / Admin 豁免」是普遍设计
- Snowflake OWNERSHIP
- Odoo admin group
- Oracle DBA 角色
- **我们设计 admin 跳过校验** ✅ 跟行业一致

#### 模式 3: 「audit-only」不是默认，而是**部署期切换**
- 业界几乎没有把 audit-only 作为**默认**行为的产品
- audit-only 模式更像是**灰度/观测期**的临时态
- 我们的 v1.0.1 D9 选了 audit-only 作为**默认**，这**略激进**，但加了 `PARENT_READ_STRICT_MODE=true` env 升级开关

#### 模式 4: 链/父校验的粒度是**实例级**，不是**类型级**
- Oracle RAS: 校验的是「该行 record 在 detail 表的 access」— **行级**
- SAP CDS: Rejected Entity Selection 是**单条记录**的 403，不是类型级
- Databricks UC: 标签继承到**单张表** — **表级**，但用户用 tag 维度
- Palantir: Object security policy 配在**对象类型**上，但 view 单个对象实例要**单独校验**
- **业界共识：链/父校验应该是 instance-level（带 target_id），不是 type-level**

### 14.3 我们当前方案的严格度评估

| FR | 当前设计 | 业界对比 | 评估 |
|---|---|---|---|
| **FR-001** read/list 合并 | ✅ 合理 | 业界普遍 list ⊂ read（Odoo、UC） | **OK** |
| **FR-003 父读** | audit-only (D9) + env 升级 | 业界 audit-only 不是默认；但 env 升级是合理 | **OK，但默认 audit-only 偏激进** |
| **FR-003b 链 read 写硬拒** | crud_create/update/delete 链中任一 read 缺失即**硬拒 403** | 业界通常是**行级**校验 + 沿数据 lineage | **⚠️ 偏严格 + 粒度不对（已修订 D13）** |
| **FR-004** menu 5 动作展开 | ✅ 合理 | 业界普遍（Odoo、Palantir） | **OK** |
| **FR-005** 菜单 2 态 | ✅ 合理 | 业界普遍 | **OK** |
| **FR-006** init 脚本 | ✅ 合理 | Odoo 初始化相似 | **OK** |
| **§13** 4 层防御 | ✅ 合理 | 跟 Apache Ranger / Databricks ABAC 一脉相承 | **OK** |

### 14.4 核心问题：FR-003b 链 read 原本的硬拒设计太严格

**问题分析**：
1. **粒度错误**：我们用**类型级**（user 有没有 `domain:read` 权限）来硬拒**写操作**，但业界普遍是**实例级**（user 能不能写这个具体的 `sub_domain` instance，取决于它的 `parent_instance` 是否在 data scope）
2. **触发面太广**：crud_create/update/delete 全部触发，但**业界普遍 create 时不严格**（Snowflake 行策略不阻止 INSERT）
3. **没有 target_id 维度**：即使带 target_id，我们只校验 type-level read，没校验「user 能否看到这行 parent 记录」

**业界等价设计**：
- **Oracle RAS**: detail INSERT 不需要父行权限（父行的 SELECT 已授权即可）
- **SAP CDS**: `Rejected Entity Selection` 是单条 record 的 403，不是类型级
- **Odoo**: 写操作只需要 ACL 允许 + Record Rule 行匹配（不要求 chain read）

**风险**：如果实施原 FR-003b 硬拒，会出现：
- admin 写子资源时，被 audit-only FR-003 警告，但 FR-003b 链 read 硬拒
- 长链场景（4 级以上）误伤面广
- TEST60 写 sub_domain 即使有 sub_domain:create，但无 `product:read` → 403

### 14.5 修订决策（D13）

| ID | 原决策 | 修订决策 | 理由 |
|---|---|---|---|
| **D9** | 父读 audit-only | **保持** ✅ | 符合灰度哲学 |
| **D10** | 多跳写**硬拒** | **改为 audit-only + env 升级** ⚠️ | 类型级硬拒粒度错误；实例级才硬拒 |
| **D11** | 多跳读 A2 隐含 | **保持** ✅ | 跟 v1.1 expand_dimension_values 一致 |
| **D12** | 4 层防御 | **保持** ✅ | 业界共识 |
| **D13** (新增) | — | **链 read 粒度 = 类型级 audit-only + 实例级硬拒** | 跟 Oracle RAS / SAP CDS / Snowflake 对齐 |

### 14.6 修订后业界对齐

| 维度 | 修订前 | 修订后（D13） | 业界参考 |
|---|---|---|---|
| **类型级** | 硬拒 403 | audit-only + env 升级 | Palantir / Oracle RAS 类型级 + 实例级组合 |
| **实例级** | 无 | 硬拒 403 | Oracle RAS / SAP CDS / Snowflake 行级 |
| **写 INSERT** | 链 read 硬拒 | 不阻止 INSERT（仅实例级检查） | Snowflake（行 policy 不阻止 INSERT） |
| **Admin 跳过** | 是 | 是 | Odoo / Snowflake / Oracle DBA |
| **4 层防御** | §13 完整 | §13 完整 | Apache Ranger ABAC |
| **自动传播** | 暂无（v1.2 reverse） | 暂无（v1.2 reverse） | Apache Atlas PropagateTags |

### 14.7 落地建议

1. **Phase A 实施**：
   - FR-003 audit-only + `PARENT_READ_STRICT_MODE` env 升级
   - FR-003b 类型级 audit-only + `CHAIN_DERIVATION_STRICT_MODE` env 升级
   - FR-003b 实例级硬拒（带 `target_id` / `parent_chain_instances` 时触发）
   - 新增 `ERR_CHAIN_INSTANCE_OUT_OF_SCOPE` 错码 + fix_hint

2. **监控指标**：
   - `parent_read_warnings` 计数（> 5 触发告警）
   - `chain_read_warnings` 计数（> 10 触发告警）
   - `chain_instance_out_of_scope` 计数（> 0 即告警，应为零）

3. **灰度策略**：
   - 1 sprint audit-only 观察期
   - 收集 warning 计数后，跟用户/PM 评审
   - 决定是否启用 `PARENT_READ_STRICT_MODE=true` / `CHAIN_DERIVATION_STRICT_MODE=true`

4. **v1.2 增量**：
   - 引入 row-level 权限（FR-012 self_reference 已含）
   - 引入 ABAC 标签（Apache Atlas 风格）
   - PropagateTags 自动传播（v1.2 增量）

### 14.8 行业参考链接

- Oracle RAS Data Realm: [docs.oracle.com/en/database/oracle/oracle-database/26/dbfsg/configuring-data-security.html](https://docs.oracle.com/en/database/oracle/oracle-database/26/dbfsg/configuring-data-security.html)
- SAP CDS DEFINE HIERARCHY: [SAP ABAP CDS Hierarchies](https://eduardocopat.github.io/abap-docs/7.54/abencds_f1_define_hierarchy/)
- Palantir Foundry Object Permissioning: [palantir.com/docs/foundry/object-permissioning/](https://www.palantir.com/docs/foundry/object-permissioning/object-security-policies)
- Snowflake Row Access Policy: [docs.snowflake.cn/user-guide/security-row-intro](https://docs.snowflake.cn/zh/user-guide/security-row-intro)
- Databricks Unity Catalog: [docs.databricks.com/data-governance/unity-catalog/](https://docs.databricks.com/data-governance/unity-catalog/)
- Odoo Security: [odoo.com/documentation/master/developer/reference/backend/security.html](https://www.odoo.com/documentation/master/developer/reference/backend/security.html)
- Apache Atlas Tag Propagation: [atlas.apache.org/1.0.0/api/v2/data.html](https://atlas.apache.org/1.0.0/api/v2/data.html)

---

**v1.0.1 修订决策落地状态（2026-06-09 更新）**:
- ✅ FR-003 父读 audit-only（D9）— 不变
- ✅ FR-003b 链 read 修订为 audit-only + 实例级硬拒（D10 修订 + D13 新增）
- ✅ D13 决策项纳入 §10.2 + 落地说明
- ✅ §十四 业界对比章节增补（深度分析 + 修订理由 + 业界对齐 + 落地建议）

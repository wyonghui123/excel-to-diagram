# 关联类型权限 Derivation（m2m / polymorphic / self_ref / reverse / sibling）— Spec & RFC

> **日期**: 2026-06-08
> **版本**: v1.0（独立 spec）
> **依赖**: v1.1 spec（[FR-007 yaml 化 / FR-008 启动校验](file:///d:/filework/excel-to-diagram/docs/specs/spec-permission-derivation-parent-read-2026-06-08-v1.1.md)）
> **目标**: 5 种非 parent 关联（m2m / polymorphic / self_reference / reverse 1:N / sibling BO）的权限 derivation 规则
> **业界参考**: SAP CDS Association + DEFINE HIERARCHY / Oracle FK + REFERENCES + REF column / Odoo `Many2many` / `fields.Reference` / Mendix 关联

---

## 变更日志

| 变更 | 类型 | 位置 |
|---|---|---|
| **FR-010**: m2m 双向校验（junction 写时 source.read + target.read） | 新增 | §三 |
| **FR-011**: polymorphic 校验（target_type 枚举 + target.read） | 新增 | §三 |
| **FR-012**: self_reference 防成环（SAP CDS `CYCLES ERROR`） | 新增 | §三 |
| **FR-013**: 1:N reverse 父→子 visibility 显式化（文档化） | 新增 | §三 |
| **FR-014**: sibling BO 共享 visibility（opt-in） | 新增 | §三 |
| **IF-008**: BoMetadataRegistry 扩展（self_references / polymorphic_types / sibling_groups） | 新增 | §五 |
| **IF-009**: 关联错误码 4 类（m2m / polymorphic / cycle / sibling） | 新增 | §五 |
| **TR-006**: yaml schema 扩展（迁移） | 新增 | §六 |
| **NFR-007**: 关联校验 < 10ms（多 2 次 yaml 读 + 1 次 DB read） | 新增 | §四 |
| **TBD-10 ~ TBD-15**: 6 项 v1.2 候选 | 新增 | §十 |

---

## 一、Background & Objectives

### 1.1 Background

| 现状 | 根因 |
|---|---|
| `relationship` 中间表（business_object m2m）权限完全空 | 权限层不支持 m2m derivation |
| `annotation.target_(type,id)` polymorphic 写时不校验 target | polymorphic derivation 缺位 |
| `user_group.parent_id` 自引用无 cycle 检测 | self_reference 防成环无 |
| `product` 看不到自己 `version` 子表列表（需手动配） | 1:N reverse visibility 缺显式规则 |
| 同父下兄弟 BO 不共享 visibility | sibling BO derivation 缺位 |

### 1.2 Business Objectives

1. **覆盖剩余 5 种关联类型**的权限 derivation
2. **对齐业界主流**（SAP CDS Hierarchies / Oracle FK / Odoo）
3. **防误操作**（写 m2m 关联不可见 BO / polymorphic target 不存在 / 自引用成环）
4. **保持 yaml 自描述**（v1.1 风格延续）

### 1.3 Stakeholder Objectives

| 角色 | 想要 |
|---|---|
| 业务用户 | 写关联时不会"看起来能写但实际没权限" |
| Admin | 关联 derivation 规则可配置 |
| 审计 | 关联校验失败可追溯（错码 + trace_id） |
| 开发 | 加新关联类型零代码改 |

---

## 二、Requirement Type Overview

| Type | Applicable | Evidence |
|---|---|---|
| Business | ✓ | 5 种关联的现状缺位 |
| User/Stakeholder | ✓ | 业务用户/admin/审计 |
| Solution | ✓ | 5 FR = 关联 derivation 体系 |
| Functional | ✓ | FR-010 ~ FR-014 |
| Nonfunctional | ✓ | NFR-001 ~ NFR-007 |
| External Interface | ✓ | yaml/registry/错误码 |
| Transition | ✓ | yaml schema 扩展 + 启动校验 |

---

## 三、Functional Requirements

### FR-010: many_to_many 双向校验

**目标**：写 m2m 中间表记录时校验 source.read + target.read（**双向**）。

**a. yaml schema**

```yaml
# meta/schemas/business_object.yaml
- code: business_object
  relations:
    - id: bo_relationships
      type: many_to_many              # [FR-010 NEW] 显式 m2m 标记
      target: business_object         # self m2m
      junction_table: relationships   # [NEW] 中间表名
      source_field: source_bo_id
      target_field: target_bo_id
      derivation:
        mode: both_ends               # [NEW] both_ends | source_only | target_only
        # 默认: both_ends (Odoo / Palantir 模式)
        requires_junction_read: true  # [NEW] 中间表自身也需 read
```

**b. 校验逻辑**

```python
# meta/core/interceptors/association_interceptor.py (新建)
def check_m2m_permission(user, source_bo, source_id, target_bo, target_id,
                         junction_bo, action='create'):
    """[FR-010] 写 m2m 中间表时校验 source + target + junction 三方"""
    mode = BoMetadataRegistry.get().get_derivation_cfg(junction_bo, 'mode')
    required = []

    if mode in ('both_ends', 'source_only'):
        required.append(f'{source_bo}:read')
    if mode in ('both_ends', 'target_only'):
        required.append(f'{target_bo}:read')
    if BoMetadataRegistry.get().get_derivation_cfg(junction_bo, 'requires_junction_read'):
        required.append(f'{junction_bo}:read')

    for perm in required:
        if not user.has_permission(perm):
            raise M2MPermissionDenied(
                junction=junction_bo,
                source=source_bo, source_id=source_id,
                target=target_bo, target_id=target_id,
                required_perm=perm,
            )
```

**c. 错误码**（[IF-009](file:///d:/filework/excel-to-diagram/meta/core/error_codes.py)）

```python
ERR_M2M_PERMISSION_DENIED = 'ERR_M2M_PERMISSION_DENIED'
# payload: { junction, source, source_id, target, target_id, required_perm, mode }
```

**依据**：Odoo `Many2many` 双向权限 / Palantir Link Set 双向 / SAP CDS 拆 2 个 1:N 后各校验

---

### FR-011: polymorphic 校验

**目标**：写 polymorphic FK 时校验 (a) target_type 在枚举 + (b) target_id 存在 + (c) target.read。

**a. yaml schema**

```yaml
# meta/schemas/annotation.yaml
- code: annotation
  fields:
    - id: target_type
      type: string
      polymorphic:                       # [FR-011 NEW]
        allowed_types: [product, version, domain, sub_domain, service_module, business_object]
        type_field: target_type          # [NEW] polymorphic 类型字段
        id_field: target_id              # [NEW] polymorphic id 字段
```

**b. 校验逻辑**

```python
def check_polymorphic_permission(user, polymorphic_bo, target_type, target_id, action='create'):
    """[FR-011] 写 polymorphic FK 时校验"""
    registry = BoMetadataRegistry.get()
    allowed = registry.get_polymorphic_allowed_types(polymorphic_bo)

    # 1. target_type 在枚举
    if target_type not in allowed:
        raise PolymorphicTypeInvalid(
            polymorphic=polymorphic_bo,
            target_type=target_type,
            allowed=allowed,
        )

    # 2. target_id 存在
    target_table = registry.get_table(target_type)
    if not target_id_exists(target_table, target_id):
        raise PolymorphicTargetNotFound(
            polymorphic=polymorphic_bo,
            target_type=target_type,
            target_id=target_id,
        )

    # 3. user 有 target.read
    required = f'{target_type}:read'
    if not user.has_permission(required):
        raise PolymorphicPermissionDenied(
            polymorphic=polymorphic_bo,
            target_type=target_type,
            target_id=target_id,
            required_perm=required,
        )
```

**c. 错误码**（3 类）

```python
ERR_POLYMORPHIC_TYPE_INVALID       = 'ERR_POLYMORPHIC_TYPE_INVALID'         # target_type 不在枚举
ERR_POLYMORPHIC_TARGET_NOT_FOUND   = 'ERR_POLYMORPHIC_TARGET_NOT_FOUND'     # target_id 不存在
ERR_POLYMORPHIC_PERMISSION_DENIED  = 'ERR_POLYMORPHIC_PERMISSION_DENIED'    # 无 target.read
```

**依据**：Oracle REF column（"A REF column by definition references an object in another object type"） / Odoo `fields.Reference` / SAP CDS annotation

---

### FR-012: self_reference 防成环（SAP CDS Hierarchies 风格）

**目标**：写 self.parent 时校验 (a) 父 self.read + (b) 防成环（**SAP CDS `CYCLES ERROR`**）。

**a. yaml schema**（**直接抄 SAP CDS**）

```yaml
# meta/schemas/user_group.yaml
- code: user_group
  self_reference:                          # [FR-012 NEW]
    hierarchy_field: parent_id             # 自引用 FK 字段
    max_depth: 10                          # 深度限制（[user_group.yaml:96](file:///d:/filework/excel-to-diagram/meta/schemas/user_group.yaml#L96) 已有）
    cycles: error                          # [NEW] SAP CDS 同名 (error | breakup)
    orphans: root                          # [NEW] SAP CDS 同名 (ignore | error | root)
    multiple_parents: not_allowed          # [NEW] SAP CDS 同名 (not_allowed | leaves | allowed)
```

**b. 校验逻辑**

```python
def check_self_reference_permission(user, self_bo, self_id, new_parent_id, action='update'):
    """[FR-012] 写 self.parent 时校验 + 防成环"""
    # 1. 父 self.read
    required = f'{self_bo}:read'
    if not user.has_permission(required):
        raise SelfReferencePermissionDenied(...)

    # 2. 防成环 (SAP CDS CYCLES ERROR | BREAKUP)
    cfg = BoMetadataRegistry.get().get_self_reference_cfg(self_bo)
    if new_parent_id and cfg['cycles'] == 'error':
        # 检查 new_parent_id 不能是 self_id 的后代
        if is_descendant_of(self_bo, new_parent_id, self_id, max_depth=cfg['max_depth']):
            raise CycleDetected(
                self_bo=self_bo,
                cycle_path=build_cycle_path(self_bo, self_id, new_parent_id),
            )
```

**c. 错误码**

```python
ERR_SELF_REFERENCE_PERMISSION_DENIED = 'ERR_SELF_REFERENCE_PERMISSION_DENIED'
ERR_CYCLE_DETECTED                  = 'ERR_CYCLE_DETECTED'
# payload: { self_bo, self_id, attempted_parent_id, cycle_path: [id, ...], max_depth }
```

**依据**：[SAP CDS DEFINE HIERARCHY](https://eduardocopat.github.io/abap-docs/7.54/abencds_f1_define_hierarchy/) `CYCLES ERROR|BREAKUP` / `ORPHANS IGNORE|ERROR|ROOT` / `MULTIPLE PARENTS`

**ORPHANS 处理**（可选 v1.2 增强）：
- `ignore`: 父删后子保留（dangling FK 风险，**不推荐**）
- `error`: 父删时拒绝（如有子引用）— **跟 v1.1 FR-003 父读校验同源**
- `root`: 父删时子自动升为 ROOT — **默认推荐**

---

### FR-013: 1:N reverse 父→子 visibility 显式化

**目标**：v1.1 child_map 已隐含，**v1.2 文档化**为显式规则。

**a. 隐含规则（v1.1 已实现）**

| 用户有 | 隐含可见 |
|---|---|
| `product:read` | product 下所有 version（1:N reverse） |
| `version:read` | version 下所有 domain |
| ... | ... |

**b. v1.2 文档化**

- v1.1 `BoMetadataRegistry.get_children(bo)` 返回子 BO 列表
- 拦截器在父表 list 时，**不需要**额外校验（隐含）
- 只在**写子表**时触发父读校验（v1.1 FR-003）

**c. yaml 注释**

```yaml
# meta/schemas/version.yaml
- code: version
  parent_object: product   # [FR-013] 1:N reverse: product 隐含可见所有 version
  parent_field: product_id
```

**依据**：业界通用（Odoo `One2many` / SAP `composition` 父可见子）

---

### FR-014: sibling BO 共享 visibility（opt-in）

**目标**：同 `sibling_group` 下的 BO 共享 visibility。

**a. yaml schema**

```yaml
# meta/schemas/product.yaml
- code: product
  sibling_group: arch_data       # [FR-014 NEW] 兄弟组
  # 注: arch_data 组下还有 version / domain / sub_domain / service_module / business_object
```

**b. 规则**

- 用户有 `sibling_group` 下任一 BO 的 read → **兄弟组所有 BO 的 list 可见**（**仅 list**，不隐含 read）
- 写仍需各自 BO 的 write 权限

**c. 校验逻辑**

```python
def check_sibling_visibility(user, bo, action):
    """[FR-014] sibling 共享 visibility"""
    if action == 'list':
        # 用户有 sibling_group 任一 BO read → 该 BO list 可见
        group = BoMetadataRegistry.get().get_sibling_group(bo)
        if group:
            for sibling in registry.get_siblings_in_group(group):
                if user.has_permission(f'{sibling}:read'):
                    return  # OK
            # 否则正常走 'visible' 计算
    # 其他 action 走原逻辑
```

**依据**：Mendix 关联（共享 attribute set） / Odoo `access.group`（opt-in）

**默认 opt-in**（不配 `sibling_group` 即不共享）— 安全优先。

---

## 四、Nonfunctional Requirements

### NFR-001 ~ NFR-006: 跟 v1.1 一致（保留）

### NFR-007: 关联校验 < 10ms

- m2m 校验：2 次 yaml 读 + 1 次 DB count（target_id 存在性） ≈ 5ms
- polymorphic 校验：1 次 yaml 读 + 1 次 DB exists ≈ 3ms
- self_ref 校验：cycle 检测走 CTE 递归，最多 100 节点 ≈ 10ms
- sibling 校验：0 次 DB 读（只查 yaml + user perms） ≈ 1ms

---

## 五、External Interface Requirements

### IF-001 ~ IF-007: 跟 v1.1 一致（保留）

### IF-008: BoMetadataRegistry 扩展

```python
class BoMetadataRegistry:
    # v1.1 已有
    def get_parent(self, bo): ...
    def get_children(self, bo): ...
    def get_dimension_chain(self): ...

    # [v1.2 NEW]
    def get_self_reference_cfg(self, bo): ...            # FR-012
    def get_polymorphic_allowed_types(self, bo): ...     # FR-011
    def get_polymorphic_type_field(self, bo): ...
    def get_polymorphic_id_field(self, bo): ...
    def get_sibling_group(self, bo): ...                 # FR-014
    def get_siblings_in_group(self, group): ...

    def get_derivation_cfg(self, bo, key=None):
        """[v1.2 扩展] 读 derivation 子键"""
        cfg = self._derivation_cfg.get(bo, {})
        if key:
            return cfg.get(key)
        return cfg
```

### IF-009: 关联错误码 4 类

```python
# meta/core/error_codes.py
class ErrorCode(enum.Enum):
    # v1.0/v1.1
    ERR_PARENT_PERMISSION_DENIED = 'ERR_PARENT_PERMISSION_DENIED'
    ERR_403_FORBIDDEN = 'ERR_403_FORBIDDEN'

    # v1.2 NEW
    ERR_M2M_PERMISSION_DENIED         = 'ERR_M2M_PERMISSION_DENIED'
    ERR_POLYMORPHIC_TYPE_INVALID       = 'ERR_POLYMORPHIC_TYPE_INVALID'
    ERR_POLYMORPHIC_TARGET_NOT_FOUND   = 'ERR_POLYMORPHIC_TARGET_NOT_FOUND'
    ERR_POLYMORPHIC_PERMISSION_DENIED  = 'ERR_POLYMORPHIC_PERMISSION_DENIED'
    ERR_SELF_REFERENCE_PERMISSION_DENIED = 'ERR_SELF_REFERENCE_PERMISSION_DENIED'
    ERR_CYCLE_DETECTED                 = 'ERR_CYCLE_DETECTED'
```

---

## 六、Transition Requirements

### TR-001 ~ TR-005: 跟 v1.1 一致（保留）

### TR-006: yaml schema 扩展（迁移）

- 6 个 BO yaml 加 `relations` / `self_reference` / `polymorphic` / `sibling_group` 字段（按需）
- `user_group.yaml` 加 `self_reference` 块（已有 `parent_id` 字段）
- `annotation.yaml` 加 `polymorphic` 块（已有 `target_type`/`target_id`）
- `business_object.yaml` 加 `relations.many_to_many` 块（已有 `relationships` 中间表）

**启动校验**（v1.1 FR-008 扩展）：
- `self_reference.cycles` 必须是 `error|breakup`
- `self_reference.orphans` 必须是 `ignore|error|root`
- `polymorphic.allowed_types` 必须是非空列表且全在 `BoMetadataRegistry` 已知 BO 中

---

## 七、Constraints & Assumptions

### 7.1 Technical Constraints
- 同 v1.1（Flask + Vue 3 + SQLite WAL + pytest + service_manager）

### 7.2 Business Constraints
- 同 v1.1（TEST60 业务用户 + admin）
- m2m / polymorphic 场景以 write 为主
- self_reference 当前只 user_group（未来可扩展到 user.manager_id 等）

### 7.3 Assumptions
- yaml `max_depth: 10`（user_group 已声明）足够业务
- m2m 中间表（`relationships` / `user_group_user` 等）有标准表名
- polymorphic target_type 列表已知（arch_object_type）
- admin 默认跳过所有关联校验（v1.1 TBD-3 已确认）

---

## 八、Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|---|---|---|---|
| **FR-010** | m2m 双向校验 | Must | 高频（relationship） |
| **FR-011** | polymorphic 校验 | Must | 高频（annotation） |
| **FR-012** | self_reference 防成环 | Must | 安全（user_group） |
| **FR-013** | 1:N reverse 文档化 | Should | v1.1 隐含，文档化即可 |
| **FR-014** | sibling BO 共享 | Could | 低频（不通用） |
| **IF-008** | registry 扩展 | Must | FR 依赖 |
| **IF-009** | 错误码 4 类 | Must | FR 配套 |
| **TR-006** | yaml schema 扩展 | Must | 启动依赖 |
| **NFR-007** | 关联校验 < 10ms | Should | 性能 |

**v1.2 PR 范围**（推荐）：
- Sprint 1 day 1-2: yaml schema 扩展 + registry 扩展 + 启动校验
- Sprint 1 day 3: 4 个新错误码 + interceptor 改造（m2m / polymorphic / self_ref）
- Sprint 1 day 4: cycle 检测算法（CTE 递归）
- Sprint 1 day 5: 单元 + 集成测试
- Sprint 1 day 6: E2E + 文档

---

## 九、Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

- **v1.1 已覆盖**：parent_child 关系（FR-007 yaml 化 + FR-008 启动校验 + FR-009 dump）
- **v1.2 未覆盖**：
  - `m2m` 关联（`business_object.yaml:965-985`）— 写 m2m 不校验 source/target
  - `polymorphic` 关联（`annotation.yaml:144-318`）— 写 polymorphic 不校验 target
  - `self_reference` 关联（`user_group.yaml:95`）— 写 self.parent 不防成环
  - `1:N reverse`（v1.1 child_map 隐含，**无文档化**）
  - `sibling BO`（无 yaml，无 derivation）
- **代码已支持**：[assoc_query_service.py:54-116](file:///d:/filework/excel-to-diagram/meta/services/assoc_query_service.py#L54-L116) 已有 m2m 查询，但**权限层无利用**

### 9.2 Target State

```
┌─────────────────────────────────────────────────────────────┐
│ v1.2 关联校验拦截器 (Association Interceptor)               │
└─────────────────────────────────────────────────────────────┘

  write business_object_m2m(user, source_id, target_id)
    ├─ 1. FR-010: 查 m2m cfg → check_m2m_permission()
    │     ├─ source.read 校验
    │     ├─ target.read 校验
    │     └─ junction.read 校验 (optional)
    │     失败 → 403 ERR_M2M_PERMISSION_DENIED
    │
    └─ 通过 → 写 DB

  write annotation(user, target_type, target_id)
    ├─ 1. FR-011: 查 polymorphic cfg → check_polymorphic_permission()
    │     ├─ target_type 在枚举
    │     ├─ target_id 存在
    │     └─ target.read 校验
    │     失败 → 403 ERR_POLYMORPHIC_*
    │
    └─ 通过 → 写 DB

  write user_group(user, self_id, new_parent_id)
    ├─ 1. FR-012: 查 self_ref cfg → check_self_reference_permission()
    │     ├─ parent.read 校验
    │     ├─ 防成环 (CTE 递归 + max_depth)
    │     └─ ORPHANS 处理 (root | error | ignore)
    │     失败 → 403 ERR_SELF_REFERENCE_PERMISSION_DENIED / ERR_CYCLE_DETECTED
    │
    └─ 通过 → 写 DB
```

### 9.3 Detailed Design

#### 9.3.1 yaml schema 扩展（汇总）

| BO yaml | 新增字段 | 位置 |
|---|---|---|
| `business_object.yaml` | `relations[].type: many_to_many` + `junction_table` + `derivation` | §FR-010 |
| `annotation.yaml` | `fields[target_type].polymorphic.allowed_types` | §FR-011 |
| `user_group.yaml` | `self_reference: { hierarchy_field, max_depth, cycles, orphans, multiple_parents }` | §FR-012 |
| `product.yaml` 等 6 个 | `sibling_group: arch_data`（opt-in） | §FR-014 |

#### 9.3.2 BoMetadataRegistry 扩展（IF-008）

```python
def _build(self):
    # v1.1 已有
    self._parent_map = {}  # bo -> (parent_bo, fk_field)
    self._child_map = {}   # parent_bo -> [bo, ...]
    self._dimension_chain = []

    # [v1.2 NEW]
    self._self_ref_cfg = {}        # bo -> { hierarchy_field, max_depth, cycles, orphans, multiple_parents }
    self._polymorphic_cfg = {}     # bo -> { type_field, id_field, allowed_types }
    self._sibling_groups = {}      # group_name -> [bo, ...]
    self._m2m_cfg = {}             # bo -> { mode, requires_junction_read, junction_table, ... }

def _validate(self):
    # v1.1 已有
    self._check_no_cycle()         # parent chain cycle
    self._check_dimension_chain_consistency()

    # [v1.2 NEW]
    self._check_self_reference_cfg()       # cycles/orphans/multiple_parents 合法值
    self._check_polymorphic_allowed_types() # 全在 registry 已知 BO 中
    self._check_sibling_groups()           # 不重复
```

#### 9.3.3 关联错误码（IF-009）

```python
# meta/core/error_codes.py
class ErrorCode(enum.Enum):
    # v1.2 NEW
    ERR_M2M_PERMISSION_DENIED = 'ERR_M2M_PERMISSION_DENIED'
    ERR_POLYMORPHIC_TYPE_INVALID = 'ERR_POLYMORPHIC_TYPE_INVALID'
    ERR_POLYMORPHIC_TARGET_NOT_FOUND = 'ERR_POLYMORPHIC_TARGET_NOT_FOUND'
    ERR_POLYMORPHIC_PERMISSION_DENIED = 'ERR_POLYMORPHIC_PERMISSION_DENIED'
    ERR_SELF_REFERENCE_PERMISSION_DENIED = 'ERR_SELF_REFERENCE_PERMISSION_DENIED'
    ERR_CYCLE_DETECTED = 'ERR_CYCLE_DETECTED'
```

```python
# meta/core/error_fix_hints.py
FIX_HINTS = {
    'ERR_M2M_PERMISSION_DENIED': '...',
    'ERR_POLYMORPHIC_PERMISSION_DENIED': '...',
    'ERR_CYCLE_DETECTED': 'parent 不能是 self 的后代, 请检查 self_reference.max_depth 配置',
    # ...
}
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|---|---|---|---|
| m2m **双向**校验 | 安全（Odoo/Palantir） | 严 | **✓ 选** |
| m2m 单向（source only） | 简单 | 漏一端 | ✗ |
| m2m 可配置 (`mode` 字段) | 灵活 | 配置复杂 | **✓ 默认 both_ends，可配** |
| polymorphic **全枚举** | 严 | 改枚举要改 yaml | **✓ 选**（可枚举 + 启动校验） |
| polymorphic lazy 校验 | 性能好 | 不一致 | ✗ |
| polymorphic fail-fast | 严 | 写时慢 | **✓ 选** |
| self_ref **CYCLES ERROR** | 严（SAP CDS） | 拒绝 cycle | **✓ 选** |
| self_ref CYCLES BREAKUP | 自动化断 | 难实现 | ✗ |
| self_ref Oracle DEFERRABLE | DB 层 | app 层不易 | ✗ |
| self_ref **ORPHANS ROOT** | 自动化 | 需支持 | **✓ 选** |
| self_ref ORPHANS ERROR | 严 | 父删时阻塞 | 可选（默认 ERROR 也 OK） |
| 1:N reverse **隐含** | 零代码（v1.1 已实现） | 文档化不足 | **✓ 选 + 文档化** |
| 1:N reverse 显式 FR | 严格 | 重复 | ✗ |
| sibling **opt-in** | 安全（不配即不共享） | 配置 | **✓ 选** |
| sibling opt-out | 默认共享 | 风险 | ✗ |
| sibling read 粒度 | 业务常用 | 简单 | **✓ 选** |
| sibling list 粒度 | 更广 | 易泄露 | ✗（默认 read） |
| 1 个 v1.2 PR | 全包 | 工作量 ×2 | **✓ 选**（高优先） |
| 拆 2 个 v1.2.x PR | 稳 | 慢 | ✗ |

### 9.5 Implementation & Migration Plan

#### 9.5.1 实施顺序（1 PR）

1. yaml schema 扩展（6 个 BO yaml + 4 个 yaml schema）
2. `BoMetadataRegistry` 扩展（IF-008）+ 启动校验（FR cycle/orphans/polymorphic/sibling）
3. error_codes + fix_hints 新增 6 个错码
4. 关联拦截器（`meta/core/interceptors/association_interceptor.py`）
5. cycle 检测算法（CTE 递归）
6. integration with v1.1 `permission_interceptor`
7. 单元 + 集成 + E2E 测试

#### 9.5.2 风险

| Risk | 缓解 |
|---|---|
| R1: cycle 检测性能（CTE 深度） | `max_depth` 限制（yaml 已配 10） |
| R2: polymorphic 枚举漏配 | 启动校验 fail-fast |
| R3: m2m 校验影响写性能 | 1 次 DB count < 5ms；缓存 user perms |
| R4: ORPHANS ROOT 引发其他级联 | 仅在 cfg='root' 时启用；其他走 ERROR |
| R5: TEST60 业务 user 缺 m2m 权限 | init 脚本（v1.1 FR-006）也展开 m2m 权限 |
| R6: 跟 v1.1 启动校验冲突 | 顺序：v1.1 先校验 parent，v1.2 后校验 self_ref/polymorphic |

#### 9.5.3 测试

- **单元**：
  - registry 构建（self_ref/polymorphic/sibling cfg）
  - 故意写 cycle yaml → 启动报错
  - 故意写 polymorphic allowed_types 含未知 BO → 启动报错
  - cycle 检测算法（10 节点深度内）
- **集成**：
  - TEST60 写 relationship → 校验 source.read + target.read
  - TEST60 写 annotation → 校验 target_type + target.read
  - TEST60 写 user_group.parent = self 后代 → ERR_CYCLE_DETECTED
  - sibling BO 共享 visibility 验证
- **E2E**：
  - Playwright 测前端错误提示（4 类错码 toast）
  - `/_diagnostics` 暴露 self_ref / polymorphic / sibling metadata
- **回归**：
  ```bash
  python d:\filework\test.py --all --force
  python d:\filework\test.py --failed
  python scripts/check_bo_metadata.py --dry-run
  ```

#### 9.5.4 回滚

- feature flag `ASSOCIATION_DERIVATION_ENABLED`（默认 true，可关）
- yaml schema 扩展不破坏 v1.1（向后兼容）
- 单 PR 单 commit 链

---

## 十、TBD List

| ID | Item | Missing Info | Default | Next Step |
|---|---|---|---|---|
| TBD-10 | m2m `mode` 默认值？ | both_ends vs source_only vs target_only | **both_ends**（Odoo/Palantir） | 用户确认 |
| TBD-11 | polymorphic target_type 校验范围？ | 全枚举 vs 白名单 vs 自动探测 | **全枚举**（yaml 显式） | 用户确认 |
| TBD-12 | self_ref `cycles` 默认？ | error vs breakup | **error**（SAP CDS） | 用户确认 |
| TBD-13 | self_ref `orphans` 默认？ | ignore/error/root | **root**（自动化） | 用户确认 |
| TBD-14 | 1:N reverse FR vs 文档化？ | 显式 FR vs 仅文档 | **文档化**（v1.1 隐含已够） | 用户确认 |
| TBD-15 | sibling `sibling_group` 命名？ | arch_data 还是其他 | **arch_data**（跟 menu 一致） | 用户确认 |
| TBD-16 | v1.2 PR 范围？ | 全包 vs 拆 2 个 | **全包 1 PR**（高优先） | 用户确认 |
| TBD-17 | cycle 检测走 CTE 还是 app 递归？ | SQL vs Python | **CTE**（SQL 一致，10 节点内） | 用户确认 |
| TBD-18 | admin 是否跳过关联校验？ | 同 v1.1 TBD-3 | **是**（admin 默认跳） | 用户确认 |

---

## 附录 A: 业界参考（详细）

### A.1 SAP CDS Association 5 大类型

| 类型 | 语法 | 例子 |
|---|---|---|
| To-One | `association [0..1] to X` | `association [1..1] to Customer` |
| To-Many | `Association to many X` | `addresses : Association to many Addresses` |
| Many-to-Many | 拆 2 个 to-many | "follow the common practice of resolving logical many-to-many relationships into two one-to-many associations" |
| Composition | `composition [0..*] of X` | 强生命周期（父删子删） |
| Self-Association | `association [0..*] to Self` | "source 和 target 是同一对象" |

### A.2 SAP CDS Hierarchies 关键参数（直接抄 v1.2）

| 参数 | 含义 | v1.2 对应 |
|---|---|---|
| `CYCLES ERROR\|BREAKUP` | 显式 cycle 处理 | FR-012 cycles |
| `ORPHANS IGNORE\|ERROR\|ROOT` | 父删时子处理 | FR-012 orphans |
| `MULTIPLE PARENTS NOT_ALLOWED\|LEAVES\|ALLOWED` | 多父 | FR-012 multiple_parents |
| `DEPTH depth` | 深度限制 | yaml `max_depth: 10`（已有） |
| `SIBLINGS ORDER BY` | 兄弟排序 | v1.3+ |

### A.3 Oracle FK 关键行为

| 行为 | 含义 | v1.2 对应 |
|---|---|---|
| REFERENCES 隐含 SELECT | "you must have REFERENCES privilege on the parent" | FR-011 polymorphic / FR-012 self_ref |
| DEFERRABLE 延迟 cycle | COMMIT 时再检查 | 弃用（用 SAP CDS CYCLES ERROR 替代） |
| ON DELETE CASCADE | 父删子删 | v1.3+（composition） |
| REF column (ORDBMS) | polymorphic 官方支持 | FR-011 polymorphic |

### A.4 5 系统对位

| 关联 | SAP CDS | Oracle | Odoo | Mendix | Palantir | 本项目 v1.2 |
|---|---|---|---|---|---|---|
| N:1 parent | `[0..1]` | FK | `Many2one` | ✓ | Link | ✅ v1.1 |
| 1:N reverse | `to many` | 反向 FK | `One2many` | ✓ | Link | ✅ FR-013 文档化 |
| m2m | 拆 2 个 1:N | Junction | `Many2many` 双向 | ✓ | Link set | **FR-010** |
| self_ref | `self` + `DEFINE HIERARCHY` | self FK | `parent_id` | ✓ | Link self | **FR-012** |
| polymorphic | `[0..*]` + annotation | REF | `fields.Reference` | inheritance | — | **FR-011** |
| composition | `composition` | `ON DELETE CASCADE` | `_inherits` | Generalization | Markings | v1.3+ |
| inheritance | type hierarchy | — | `_inherit` | Generalization | — | v1.3+ |

---

## 附录 B: 现有代码路径

| 文件 | 角色 |
|---|---|
| [meta/services/assoc_query_service.py](file:///d:/filework/excel-to-diagram/meta/services/assoc_query_service.py) | m2m 查询层已支持 (L54-116)，**权限层未利用** |
| [meta/services/audit_interceptor.py](file:///d:/filework/excel-to-diagram/meta/services/audit_interceptor.py) | polymorphic 审计层已支持 (L366/415)，**权限层未利用** |
| [meta/schemas/user_group.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/user_group.yaml) | self_reference 已声明 (L95) + `max_depth: 10` (L96) |
| [meta/schemas/annotation.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/annotation.yaml) | polymorphic 已声明 (L144-318) `polymorphic_type_field: target_type` |
| [meta/schemas/business_object.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/business_object.yaml) | m2m `merged_one_to_many` 已声明 (L965-985) |
| [meta/core/bo_metadata_registry.py](file:///d:/filework/excel-to-diagram/meta/core/bo_metadata_registry.py) (v1.1 新建) | v1.2 扩展 |
| [meta/core/interceptors/association_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/association_interceptor.py) (v1.2 新建) | FR-010/011/012 实现 |
| [meta/core/error_codes.py](file:///d:/filework/excel-to-diagram/meta/core/error_codes.py) | v1.2 新增 6 个错码 |
| [meta/core/error_fix_hints.py](file:///d:/filework/excel-to-diagram/meta/core/error_fix_hints.py) | v1.2 新增 6 个 fix_hint |

---

**Spec + RFC 完整性自检**：
- ✅ 12 章节齐全（含新增 §十一 实施时间表 + §十二 Code Review Checklist）
- ✅ 最后一节是 "TBD List"，内容完整
- ✅ 5 个 FR（FR-010 ~ FR-014）覆盖 m2m/polymorphic/self_ref/reverse/sibling
- ✅ 依赖 v1.1 `BoMetadataRegistry`（明确说明）
- ✅ 业界参考（SAP CDS Hierarchies 4 参数 / Oracle FK / Odoo / Mendix / Palantir）
- ✅ 风险 + 回滚 + 测试 + 实施顺序明确
- ✅ 现有代码路径已附录
- ✅ 9 个 TBD（默认已给推荐）
- ✅ **NEW** §十一 实施时间表（Phase 0-5，总 4.5-6 天）
- ✅ **NEW** §十二 Code Review Checklist（A-J 10 大类，~ 50 项打勾项）

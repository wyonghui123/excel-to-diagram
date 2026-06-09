## 目录

1. [1. Background & Objectives](#1-background-objectives)
2. [2. Requirement Type Overview](#2-requirement-type-overview)
3. [3. Functional Requirements](#3-functional-requirements)
4. [4. Nonfunctional Requirements](#4-nonfunctional-requirements)
5. [5. External Interface Requirements](#5-external-interface-requirements)
6. [6. Transition Requirements](#6-transition-requirements)
7. [7. Constraints & Assumptions](#7-constraints-assumptions)
8. [8. Priorities & Milestone Suggestions](#8-priorities-milestone-suggestions)
9. [9. Change / Design Proposal (RFC)](#9-change-design-proposal-(rfc))
10. [10. TBD List](#10-tbd-list)
11. [Appendix: 校验消息模板](#appendix-校验消息模板)

---
# Spec: YAML 元数据驱动校验增强方案

## 1. Background & Objectives

### 1.1 Background

当前系统采用 SAP One Model 风格的元数据驱动架构，YAML 作为单一事实源（SSOT）。但运行时 CRUD 操作和关联操作的校验逻辑分散在多处，缺乏统一覆盖，存在以下 gap：

- Update 操作缺少字段级运行时校验（required、唯一性、pattern 等）
- Delete 操作的引用完整性检查不完整（缺少反向 FK 检查和 `deletion_policy.restrict_on`）
- AssociationInterceptor 校验逻辑不完整（权限、readonly、business rules 均未阻止操作）
- ConstraintEngine 已实现但未集成到拦截器链
- addability 校验仅在 manage_service 层面，未下沉到 ActionExecutor
- 关联操作缺少 source/target 存在性校验
- 缺少 cardinality 基数约束校验（含 allow_reassign 配置）
- unassign 时缺少 FK required 校验

### 1.2 Business Objectives

- 基于 YAML 元数据声明，运行时自动执行完整校验，无需在每个 API 硬编码校验逻辑
- 所有校验消息统一通过 ValidationMessageRegistry 管理，支持 i18n
- 阻断式校验：校验失败时抛出异常而非静默放行

### 1.3 User / Stakeholder Objectives

- **开发人员**：只需在 YAML 中声明校验规则，运行时自动生效
- **业务人员**：校验失败时获得清晰的中文错误消息
- **运维/安全**：引用完整性得到保障，防止孤儿记录

---

## 2. Requirement Type Overview

| Type | Applicable | Evidence |
|---|---|---|
| Business | Yes | 系统架构设计决策：YAML SSOT |
| User/Stakeholder | Yes | 开发人员依赖声明式校验减少硬编码 |
| Solution | Yes | 元数据驱动校验引擎 |
| Functional | Yes | 20+ FR 条目覆盖 CRUD/关联操作 |
| Nonfunctional | Yes | 校验性能、i18n 可扩展性 |
| External Interface | Partial | API 错误响应格式已定义 |
| Transition | Yes | 新增校验需考虑存量数据兼容 |

---

## 3. Functional Requirements

### FR-001: 字段级必填校验（Create）

- **Description**: 创建记录时，系统必须基于 `required=true`、`semantics.mandatory=true`、`semantics.business_key=true` 三个维度校验字段是否为空
- **Acceptance Criteria**:
  - 任意一个必填字段为空时，返回错误 `VALIDATION_FAILED`，错误详情包含 field_id、field_name、rule、message
  - 错误消息从 ValidationMessageRegistry 获取（中文默认）
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: MetadataDrivenValidator._check_required() ✅

### FR-002: 字段级必填校验（Update）

- **Description**: 更新记录时，如果将 required/mandatory/business_key 字段设为空，系统必须报错
- **Acceptance Criteria**:
  - 在 data 中出现的字段（即使值为 null/空字符串）触发必填校验
  - 与 Create 使用同一套校验逻辑
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: MetadataDrivenValidator.validate_update() ✅

### FR-003: 单字段唯一性校验

- **Description**: 创建/更新时，字段 `unique=true` 的字段值不得与已有记录重复（更新时排除自身）
- **Acceptance Criteria**:
  - 重复值返回 `ValidationFailedError`，消息为 "{field_name} 已存在"
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: MetadataDrivenValidator._check_unique() ✅

### FR-004: 正则/枚举/长度校验

- **Description**: 字段值必须满足 `semantics.pattern` 正则、`enum_values` 枚举范围、`max_length` 长度限制
- **Acceptance Criteria**:
  - 任一校验失败返回对应消息模板（参数化替换）
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: MetadataDrivenValidator._check_pattern/_check_enum_values/_check_max_length() ✅

### FR-005: FK 存在性校验

- **Description**: 创建/更新时，FK 字段引用的目标记录必须存在
- **Acceptance Criteria**:
  - FK 字段通过 `semantics.resolve_to_object` 或命名约定（`_id` 后缀）推断目标实体
  - 目标记录不存在时返回 "引用的{target_name}不存在（ID: {value}）"
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: MetadataDrivenValidator._check_fk_existence() ✅

### FR-006: 复合唯一索引校验

- **Description**: 创建/更新时，复合唯一索引字段组合值不得重复（排除自身）
- **Acceptance Criteria**:
  - 索引定义来源：`meta_object.indexes` 中 `type=unique` 的条目
  - 冲突消息："唯一索引 {index_name} 冲突：{field_names} 组合值已存在"
  - 跳过纯 business_key 索引（已在 FR-001/002 中覆盖）
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: MetadataDrivenValidator._check_unique_indexes() ✅

### FR-007: 业务键组合唯一性校验

- **Description**: 组合业务键字段（多个 `semantics.business_key=true`）的值组合不得重复
- **Acceptance Criteria**:
  - 支持单字段和组合键两种场景
  - 消息："【业务关键字】{field_names} 组合值已存在：{values}"
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: MetadataDrivenValidator._check_business_key_composite() ✅

### FR-008: addability 条件校验

- **Description**: 创建记录前，系统必须评估 `addability.condition` 条件，条件不满足时阻止创建
- **Acceptance Criteria**:
  - 条件上下文包含 `self`（新记录数据）和 `parent`（父对象记录）
  - 失败消息使用 `addability.message` 或默认值
  - 在 ActionExecutor._do_create() 中调用
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: ActionExecutor._check_addability() ✅

### FR-009: deletion_policy.restrict_on 校验

- **Description**: 删除记录时，系统必须检查 `deletion_policy.restrict_on` 规则，阻止被引用的记录删除
- **Acceptance Criteria**:
  - 每个 restrict_on 规则指定 target_object 和 fk_field
  - 有关联记录时返回 "无法删除：{child_name} 的 {field_name} 引用了此记录（{count}条）"
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: ActionExecutor._check_deletion_policy_restrict() ✅

### FR-010: 反向 FK 引用完整性检查

- **Description**: 删除记录前，系统必须遍历所有其他实体的 FK 字段，检查是否有记录引用待删除记录（cascade_delete 除外）
- **Acceptance Criteria**:
  - FK 推断策略：显式 `resolve_to_object` > 命名约定（`_id` 后缀）+ `parent_key=true`
  - 关联记录存在时返回与 FR-009 相同格式的消息
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: ActionExecutor._check_reverse_fk_references() ✅

### FR-011: 关联操作 source/target 存在性校验

- **Description**: 执行关联操作（associate/assign）前，系统必须验证源记录和目标记录均存在于数据库
- **Acceptance Criteria**:
  - 源记录不存在返回："源记录不存在（{object_type} ID: {src_id}）"
  - 目标记录不存在返回："目标记录不存在（{object_type} ID: {tgt_id}）"
  - 适用于：M2M、reference、composition 三种关联类型
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: AssociationEngine._validate_source_target_existence() ✅

### FR-012: cardinality 基数约束校验

- **Description**: 执行关联操作前，系统必须检查当前关联数量是否超过 `max_cardinality` 上限
- **Acceptance Criteria**:
  - 支持 `allow_reassign=true`：当 `max_cardinality=1` 时，自动清除旧关联后再创建新关联
  - `allow_reassign=false` 或超出限制时返回："关联数量超出限制：{assoc_name} 最多允许 {cardinality} 个关联"
  - 适用于：M2M、reference、composition 三种关联类型
  - YAML 配置：`max_cardinality: N` 和 `allow_reassign: true/false`
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: AssociationEngine._check_cardinality_constraint() ✅

### FR-013: AssociationInterceptor 阻止式校验

- **Description**: AssociationInterceptor 必须对权限不足、readonly 关联、composition unassign 操作抛出 `ValidationFailedError` 异常
- **Acceptance Criteria**:
  - 权限不足：抛出 "没有权限执行此关联操作"
  - readonly 关联：抛出 "关联 '{assoc_name}' 为只读，不允许{operation}"
  - composition unassign：抛出 "组合关联不支持取消关联，请使用删除子对象"
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: AssociationInterceptor._validate_permission() + _validate_business_rules() ✅

### FR-014: 关联操作权限校验

- **Description**: assign/unassign 操作需检查 `actions.assign/unassign.permission` 配置
- **Acceptance Criteria**:
  - 调用 `permission_service.has_permission()` 进行校验
  - 无权限时抛出 ValidationFailedError
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: AssociationInterceptor._validate_permission() ✅

### FR-015: unassign FK required 校验

- **Description**: 取消 reference 类型关联时，如果 FK 字段为 required/mandatory/business_key，不得将 FK 置为 NULL
- **Acceptance Criteria**:
  - 返回："无法取消关联：{field_name} 为必填字段，不能为空"
  - 适用于：`_unassign_reference` 和 `_dissociate_reference`
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: AssociationEngine._check_fk_required_before_unassign() ✅

### FR-016: ConstraintEngine 集成到拦截器链

- **Description**: ConstraintEngine 必须集成到拦截器链，优先级 42（FieldPolicyInterceptor 之后）
- **Acceptance Criteria**:
  - `before_action` 中调用 `engine.validate(context)`
  - 校验失败时抛出 `ValidationFailedError`，由 `BOFramework` 捕获并转换为 ActionResult
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: ConstraintValidationInterceptor ✅

### FR-017: Delete 时 M2M 中间表清理

- **Description**: 删除记录时，系统必须自动清理该记录在 M2M 中间表中的关联行
- **Acceptance Criteria**:
  - 遍历实体的 `associations`，对 `through` 存在的 M2M 关联执行 DELETE
  - 失败仅记录 warning，不阻塞主删除流程
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: ActionExecutor._cleanup_m2m_tables() ✅

---

## 4. Nonfunctional Requirements

### NFR-001: i18n 消息框架

- **Description**: 所有校验消息通过 ValidationMessageRegistry 获取，支持 locale 切换
- **Measurement**: `ValidationMessageRegistry.set_locale()` 切换后消息语言变化
- **Priority**: Should
- **Source**: ValidationMessageRegistry 已实现 ✅，field_name 翻译待未来支持（TBD-4）

### NFR-002: 校验性能

- **Description**: 字段级校验应在 O(1) 范围内完成，不引入 N+1 查询
- **Measurement**: 单条记录校验 DB 查询不超过 10 次
- **Priority**: Should
- **Source**: 设计约束

### NFR-003: 错误响应格式

- **Description**: 校验失败时 ActionResult.errors 包含 `field_id`、`field_name`、`rule`、`message`、`i18n_key`、`params`
- **Measurement**: 响应 JSON schema 与 ValidationDetail.to_dict() 一致
- **Priority**: Must
- **Source**: ValidationDetail 数据类已定义 ✅

---

## 5. External Interface Requirements

### IF-001: CRUD API 校验响应

- **Type**: API Response
- **Schema**: ActionResult 包含 `success: bool`、`message: str`、`errors: List[ValidationDetail]`
- **Error Handling**: `error="VALIDATION_FAILED"`，`errors` 数组非空时表示校验失败
- **Source**: ActionExecutor、BOFramework

### IF-002: Association API 校验响应

- **Type**: API Response
- **Schema**: 同 IF-001
- **Error Handling**: 关联操作校验失败返回 `errors` 详情
- **Source**: AssociationEngine、AssociationInterceptor

---

## 6. Transition Requirements

### TR-001: 存量数据兼容

- **Description**: 新增校验规则（如 unique index 校验）对存量数据可能产生冲击
- **Strategy**: 校验在写入时触发，不影响已存在的不合规数据（由数据治理工具处理）
- **Rollback Plan**: 关闭新增校验需回滚代码，无数据迁移需求

---

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- SQLite 数据库（当前 datasource 实现）
- 拦截器链优先级已固定（参考已有 Interceptor 顺序）

### 7.2 Business Constraints

- FK 推断策略：显式 `resolve_to_object` > 命名约定 + `parent_key=true`（TBD-2 已确认）
- cardinality allow_reassign 配置：需要支持（TBD-1 已确认）
- field_name 翻译：未来需求，当前返回原始字段名（TBD-4）

### 7.3 Assumptions

- YAML 元数据加载器已正确解析 `max_cardinality` 和 `allow_reassign` 字段
- permission_service 已存在或可按需 mock

---

## 8. Priorities & Milestone Suggestions

| ID | Requirement | Priority | Reason |
|---|---|---|---|
| FR-001 ~ FR-007 | 字段级校验（Create/Update） | Must | 核心数据入口校验 |
| FR-016 | ConstraintEngine 集成 | Must | P0 已有但未集成 |
| FR-010 | 反向 FK 引用完整性 | Must | 引用完整性保障 |
| FR-009 | deletion_policy.restrict_on | Must | 同上 |
| FR-013 | AssociationInterceptor 阻止式 | Must | 关联操作安全保障 |
| FR-011 | source/target 存在性校验 | Must | 关联操作入口校验 |
| FR-008 | addability 下沉 | Should | 与 deletability 对称 |
| FR-012 | cardinality 基数约束 | Should | 业务规则保障 |
| FR-014 | 关联权限校验 | Should | 安全校验 |
| FR-015 | unassign FK required | Should | 数据一致性 |
| FR-017 | M2M 中间表清理 | Should | 垃圾数据清理 |

**已实现里程碑（Milestone 1 + 2）**：✅ 全部完成

- M1: FR-016 + FR-005 + FR-001 ~ FR-004（字段级校验 + ConstraintEngine 集成）
- M2: FR-010 + FR-009 + FR-011 + FR-013（引用完整性 + 关联拦截）

**进行中里程碑（Milestone 3）**：✅ 全部完成

- M3: FR-006 + FR-008 + FR-012 + FR-014 + FR-015 + FR-017

---

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

**当前架构**：

- `ActionExecutor` 负责 CRUD 执行，校验分散在 `_do_create/_do_update/_do_delete` 中
- `_validate_business_key_uniqueness` 仅在 Create 中调用，Update 中缺失
- `ConstraintEngine` 已实现但未注册到拦截器链
- `AssociationInterceptor` 为空壳，仅记录日志
- `AssociationEngine` 关联操作无存在性、基数、FK required 校验
- `ValidationMessageRegistry` 存在但未被广泛使用

**关键文件**：

- `meta/core/action_executor.py` — CRUD 执行器
- `meta/core/association_engine.py` — 关联操作引擎
- `meta/core/metadata_driven_validator.py` — 字段级校验器
- `meta/core/validation_messages.py` — i18n 消息注册表
- `meta/core/interceptors/association_interceptor.py` — 关联拦截器
- `meta/core/interceptors/constraint_validation_interceptor.py` — 约束拦截器

### 9.2 Target State

**Proposed Architecture**：

```
请求 → InterceptorChain
         ├── FieldPolicyInterceptor (30)
         ├── ConstraintValidationInterceptor (42)  ← 新增
         ├── AssociationInterceptor (35)
         │     ├── _validate_permission() ← 权限检查
         │     ├── _validate_business_rules() ← readonly/composition/存在性/基数
         │     └── → AssociationEngine
         │           ├── _validate_source_target_existence() ← 新增
         │           ├── _check_cardinality_constraint() ← 新增
         │           └── _check_fk_required_before_unassign() ← 新增
         └── ActionExecutor
               ├── _check_addability() ← 新增
               ├── _validate_before_create() → MetadataDrivenValidator
               ├── _validate_before_update() → MetadataDrivenValidator
               ├── _check_reverse_fk_references() ← 新增
               ├── _check_deletion_policy_restrict() ← 新增
               └── _cleanup_m2m_tables() ← 新增
```

### 9.3 Detailed Design

#### 9.3.1 ValidationMessageRegistry（i18n 消息框架）

```python
class ValidationMessageRegistry:
    _messages: Dict[str, Dict[str, str]] = {"zh_CN": _ZH_CN_MESSAGES.copy()}
    _locale: str = "zh_CN"

    @classmethod
    def get(cls, key: str, **params) -> str:
        template = cls._messages.get(cls._locale, {}).get(key, key)
        return template.format(**params)
```

消息 key 格式：`validation.{category}.{rule}`，如 `validation.field.required`

#### 9.3.2 MetadataDrivenValidator（字段级校验器）

覆盖方法：`validate_create()`、`validate_update()`

内部校验方法：

- `_check_required()` — required + mandatory + business_key
- `_check_unique()` — 单字段唯一性
- `_check_pattern()` — 正则校验
- `_check_max_length()` — 长度校验
- `_check_enum_values()` — 枚举校验
- `_check_fk_existence()` — FK 存在性
- `_check_business_key_composite()` — 组合业务键
- `_check_unique_indexes()` — 复合唯一索引

#### 9.3.3 AssociationEngine（关联操作增强）

新增方法：

- `_validate_source_target_existence()` — 源/目标记录存在性校验
- `_check_cardinality_constraint()` — 基数约束校验
- `_get_current_association_count()` — 获取当前关联数量
- `_reassign_existing()` — allow_reassign 时清除旧关联
- `_check_fk_required_before_unassign()` — unassign FK required 校验

YAML 新增字段（`AssociationDefinition`）：

```python
@dataclass
class AssociationDefinition:
    # ... 已有字段 ...
    max_cardinality: Optional[int] = None   # 最大关联数量
    allow_reassign: bool = False             # 是否允许重新分配
```

#### 9.3.4 ActionExecutor（CRUD 增强）

新增方法：

- `_check_addability()` — addability 条件校验
- `_resolve_parent_context_for_addability()` — 解析父对象上下文

已增强方法：

- `_do_create()` — 添加 `_check_addability()` 调用
- `_do_update()` — 添加 `_validate_before_update()` 调用
- `_do_delete()` — 添加 `_check_reverse_fk_references()`、`_check_deletion_policy_restrict()`、`_cleanup_m2m_tables()` 调用

#### 9.3.5 AssociationInterceptor（阻止式拦截器）

`_validate_permission()`：从 `actions.assign/unassign.permission` 读取权限配置，调用 `permission_service.has_permission()`

`_validate_business_rules()`：

- `readonly=true` → 抛出异常
- `type=composition` + unassign → 抛出异常
- `type=reference` + assign（已有引用）→ 记录日志（不阻止）

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
|---|---|---|---|
| 校验分散在各 API | 灵活 | 重复代码、易遗漏 | Rejected |
| 统一 MetadataDrivenValidator | 单一事实源、YAML 驱动 | 初期工作量较大 | Selected |
| 拦截器链校验 | 声明式、优先级可控 | 增加调用链路复杂度 | Selected |

### 9.5 Implementation & Migration Plan

**Implementation Order**（已完成）：

1. ✅ ValidationMessageRegistry（基础设施）
2. ✅ MetadataDrivenValidator（字段级校验）
3. ✅ ActionExecutor 集成（_validate_before_create/update）
4. ✅ ConstraintValidationInterceptor（拦截器链注册）
5. ✅ AssociationInterceptor 修复（阻止式）
6. ✅ ActionExecutor Delete 增强（反向 FK + restrict_on + M2M cleanup）
7. ✅ AssociationEngine source/target 存在性校验
8. ✅ AssociationEngine cardinality 基数约束
9. ✅ ActionExecutor addability 下沉
10. ✅ AssociationEngine unassign FK required 校验

**Testing Strategy**：

- Unit tests: 各校验方法独立测试
- Integration tests: CRUD API + 关联操作端到端测试
- 关键场景：FK 不存在创建、唯一性冲突、cardinality 超限、readonly 关联修改

**Rollback Plan**：

- 代码级回滚（git revert）
- 新增校验为非破坏性（仅影响新增/修改操作，不影响存量数据）

---

## 10. TBD List

| ID | Item | Missing Information | Next Step |
|---|---|---|---|
| TBD-1 | cardinality allow_reassign | ✅ 已确认：需要支持 | 关闭 |
| TBD-2 | FK 字段推断策略 | ✅ 已确认：命名约定 + semantics 标注可接受 | 关闭 |
| TBD-4 | field_name 翻译支持 | ✅ 已确认：未来考虑，当前返回原始字段名 | 关闭 |

---

## Appendix: 校验消息模板

所有消息通过 `ValidationMessageRegistry.get(key, **params)` 获取，默认 locale 为 `zh_CN`：

| Key | 消息模板 |
|---|---|
| `validation.field.required` | {field_name} 不能为空 |
| `validation.field.mandatory` | {field_name} 是业务必填字段 |
| `validation.field.business_key_required` | {field_name} 是业务关键字，不能为空 |
| `validation.field.unique` | {field_name} 已存在 |
| `validation.field.pattern_mismatch` | {field_name} 格式不正确，要求匹配 {pattern} |
| `validation.field.max_length_exceeded` | {field_name} 长度不能超过 {max_length} 个字符 |
| `validation.field.enum_value_invalid` | {field_name} 的值 '{value}' 不在有效选项中 |
| `validation.field.immutable` | {field_name} 创建后不可修改 |
| `validation.field.fk_not_found` | 引用的{target_name}不存在（ID: {value}） |
| `validation.object.business_key_composite` | 【业务关键字】{field_names} 组合值已存在：{values} |
| `validation.object.index_unique` | 唯一索引 {index_name} 冲突：{field_names} 组合值已存在 |
| `validation.object.addability_denied` | {message} |
| `validation.object.deletability_denied` | {message} |
| `validation.object.restrict_on_delete` | 无法删除：{child_name} 的 {field_name} 引用了此记录（{count}条） |
| `validation.object.has_children` | 无法删除：存在 {count} 个子元素 |
| `validation.object.parent_field_immutable` | 父元素字段 [{field_name}] 不允许修改 |
| `validation.association.source_not_found` | 源记录不存在（{object_type} ID: {src_id}） |
| `validation.association.target_not_found` | 目标记录不存在（{object_type} ID: {tgt_id}） |
| `validation.association.readonly` | 关联 '{assoc_name}' 为只读，不允许{operation} |
| `validation.association.composition_unassign` | 组合关联不支持取消关联，请使用删除子对象 |
| `validation.association.cardinality_exceeded` | 关联数量超出限制：{assoc_name} 最多允许 {cardinality} 个关联 |
| `validation.association.fk_required` | 无法取消关联：{field_name} 为必填字段，不能为空 |
| `validation.association.permission_denied` | 没有权限执行此关联操作 |
| `validation.association.already_exists` | 关联已存在 |

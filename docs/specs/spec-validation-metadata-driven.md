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

### 9.5 Implementation & Migration Plan（severity 见 §9.6，未实现）

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

### 9.6 校验严重性（severity）二层模型（增量提案，2026-11-10）

> **状态**：设计结论，**未实现**。本文只固化语义边界与落地代价，不改变 §1–§9.5 已完成的“一律阻断”行为。
> **动机**：SAP 的运行时消息类型（`A/E/W/I/S`）包含“刚性/柔性”语义，但直接照搬会把“判定结果”和“执行行为”焊死，导致同一条规则无法在不同操作场景下表现不同。

#### 9.6.1 先分清 SAP 的两个 "message"

| 概念 | 是什么 | 组成 | 本项目归属 |
|---|---|---|---|
| **ABAP Message Type** | 运行时消息严重性 | `A` 终止 / `E` 错误 / `W` 警告 / `I` 信息 / `S` 成功 | **校验域（本节）** |
| **Message Control（MM/SD）** | 输出控制：谁在什么时点收到什么单据 | 消息类型 `NEU/ÄND/MAHN` + 输出类型 + 媒介（打印/EDI/邮件）+ 时点 `V1/V2/V3` | **通知域**（`change_subscription` / 统一消息中心） |

二者在 SAP 中本就是两套独立机制。这也反证了 `spec-notification-task-alert.md` 的收敛结论：**校验严重性属于校验域，不属于消息中心。**

#### 9.6.2 结论：引入二值 severity，拒绝五类

| 类型 | 决策 | 理由 |
|---|---|---|
| `error` | 引入（显式化现有语义） | 刚性，阻断 |
| `warning` | **引入** | 柔性，放行但必须 ack |
| `info` | 拒绝 | 提示不属于“违规”；一旦进入 `errors` 数组，`ok` 判据即失效 |
| `success` | 拒绝 | 是 UI 反馈，不是校验结果 |
| `abort` | 拒绝 | 技术故障走异常通道，不属于业务校验 |
| `tech_debt` | 拒绝 | 元模型自检（`metadata_validator.py`）专用，业务数据无此概念 |

即 **severity 是二值枚举 `{"error", "warning"}`**。SAP 的五类是“消息”的等级，本项目只需要“违规”的等级。

#### 9.6.3 三层拆分：判定 / 分级 / 处置

```
① 判定 Detection        规则命中 → finding {rule, severity}
                        所有者：规则元数据（YAML）
                        纯函数，不关心是否阻断
        │
② 分级 Classification   severity ∈ {error, warning}
                        所有者：规则元数据声明
                        禁止写在 Python 代码里
        │
③ 处置 Enforcement      在某操作上下文中：error → 阻断；warning → 放行 + ack
                        所有者：操作上下文策略（operation × rule）
                        唯一允许知道“保存 vs 过账”差异的层
```

**severity 属于 ②，是否阻断属于 ③。** SAP 把两者合并（“类型即行为”），因此无法表达：

> 同一条校验规则，保存草稿时应为 `W`（可继续），过账时必须为 `E`（阻断）。

这正是企业系统柔性校验的主要需求，因此本项目**学其分级语义、拒绝其类型即行为的耦合**。

#### 9.6.4 现状证据：两个校验域的严重性支持不对称

| 校验域 | 结果类型 | 分级 |
|---|---|---|
| 元模型自检（校验 YAML 自身） | [metadata_validator.py](../../meta/core/metadata_validator.py#L44-L50) `ValidationLevel` | 4 级：`ERROR / WARNING / TECH_DEBT / INFO` |
| 业务数据校验（校验用户输入） | [validation_messages.py](../../meta/core/validation_messages.py#L13-L21) `ValidationDetail` | **0 级，无 severity 字段，一律视为 error** |

元模型自检敢用 `WARNING`，因为它“只报告不阻断”；业务数据校验不敢用，因为“一有结果就阻断”。这不是设计取舍，而是缺口。

#### 9.6.5 最小落地改动（不新增表）

1. `ValidationDetail` 增加字段 `severity: Literal["error", "warning"] = "error"`
   —— **默认必须是 `error`**，否则存量规则行为会静默改变（破坏 §6 TR-001 存量兼容约束）。
2. 聚合层把结果拆成 `errors` / `warnings`，通过判据改为 `ok = not errors`。
3. 规则 YAML 允许声明 `validation.severity: warning`；未声明即 `error`（元数据驱动，禁止在拦截器里按 rule 名硬编码）。
4. 柔性放行必须记录 ack：落 `audit_log`，payload 记 `{rule, object_id, values_hash, actor, at}`。
5. 若某 warning 必须由**他人**复核才能放行 → 复用 `tasks` 表生成 `type=validation_review` 的待办，不新建实体。

**不新增任何表**：severity 是规则属性（YAML），ack 是审计事实（`audit_log` 已有），复核是待办（`tasks` 已有）。

#### 9.6.6 三条红线

1. **柔性 ≠ 不校验**：`warning` 必须显式确认（acknowledge）并落痕；禁止新建 `validation_acknowledgement` 表——ack 的所有者是 `audit_log`。
2. **severity 不可由调用方/前端降级**：降级只能来自配置或 RBAC 授权，否则刚性校验失效。
3. **severity 不做 per-record 快照**：只存在于规则元数据。若把某条记录的 severity 写入数据行，规则升级后会产生永久漂移（与“`ValidationDetail` 不落库”同一条红线）。

#### 9.6.7 与 Event / Task / 通知中心的关系（引入 warning 后仍不需要新实体）

| 场景 | 归属 | 说明 |
|---|---|---|
| `error` | 同步返回 `ValidationDetail[]`，事务回滚 | **不产生 Event**（什么都没发生），不产生 Task |
| `warning` 由当前操作者确认 | `audit_log` | 审计事实；如需事后可查可订阅，可另发 `change_event` |
| `warning` 需他人复核 | `tasks`（`type=validation_review`） + 复核后 `audit_log` | 复用待办，不新建机制 |
| 异步/批量校验失败（无请求方可同步告知） | 编排层转 `task.fail_reason` 或 `change_event` | validator 仍只返回结构化结果，不自行投递 |

一句话：**warning 的“确认”要么是审计记录、要么是待办任务，从来不是一条“消息”。** 因此 `ValidationDetail` 依然不落库、不进消息中心，只是多了 `severity` 字段与 ack 落点。

#### 9.6.8 验收标准

| 编号 | 验收项 | 判据 |
|---|---|---|
| S-1 | 存量兼容 | 未声明 severity 的规则行为与现状完全一致（仍阻断） |
| S-2 | 柔性放行 | 声明 `warning` 的规则失败时写入成功，且 `audit_log` 存在对应 ack 记录 |
| S-3 | 刚性阻断 | `error` 规则失败时写入被拒，且无 ack 记录 |
| S-4 | 场景化处置 | 同一规则在「保存」上下文为 `warning`、在「过账」上下文为 `error`，无需改规则本身 |
| S-5 | 判据正确 | `info`（若未来引入）不计入 `errors`，`ok` 判据不受影响 |

### 9.7 审批触发条件与校验正交（增量提案，2026-11-10）

> **状态**：设计结论，**审批侧已实现，校验侧未变**。本文只固化边界，不新增表、不改状态机。
> **动机**：业务上常把「金额 > 100 万」「价格偏差 > 5%」当作「校验」，但两者的失败语义相反——校验失败要求**改数据**，金额超限要求**找人点头**。混为一谈会让合法数据被判为错误，或让审批人去做数据修补。

#### 9.7.1 三者不是同一个问题

| 问题 | 回答者 | 输出 | 条件不成立意味着 | 事实源 |
|---|---|---|---|---|
| 这张单能否保存 / 过门 | validation rule | `pass` / `warning` / `error` | **数据不合格**，必须改数据 | `audit_log(action=validate)` + 行缓存 `validation_status` |
| 这张单要不要人点头 | approval policy 条件 | `required` / `not_required` | **不是错误**，只是不能自动放行 | `approval_policies` + `approval_policy_conditions` + resolve 快照 |
| 人点了没有、点了什么 | approval task | `pending` / `approved` / `rejected` | 决策未完成 / 被否 | `tasks(type=approval)`；`approval_status` 只是只读缓存 |

判别只需一问：**条件不成立时，是"改数据"还是"找人"？** 前者属校验域，后者属审批域。

因此金额档、偏差档是**路由谓词（routing predicate）**，与 BPMN gateway condition、Oracle AME approval rule、SAP Release Strategy 特征组合同族——这三家都把它归在 release/approval，**没有一家把金额档写成 error message**。

#### 9.7.2 唯一的真实重叠：容差（tolerance）

同一度量可以有两种用途，但这是**配置差异，不是模型合并**：

| 用法 | 语义 | 后果 | 归属 |
|---|---|---|---|
| 硬容差 | 偏差是数据错误 | 阻断提交 | validation rule（`error`） |
| 软容差 | 偏差是需要判断的风险 | 放行到人审 | approval policy 条件（+ 可选 `warning`） |

正确处理是**抽出派生度量，两处消费**：

```
computed: price_deviation_rate        ← 一处计算
    ├─ validation rule 引用      → 判 warning / error
    └─ approval policy 条件引用  → 判 required
```

否则两个模块各算一遍偏差率，会产生 4.9% / 5.1% 的口径漂移（同 §9.6.6 红线 3 的「判定真源多处」问题）。

#### 9.7.3 现状证据：审批侧已经是这个模型

| 能力 | 现有实现 | 语义 |
|---|---|---|
| 是否需要审批 | [document_approval_service.py](../../meta/services/document_approval_service.py) `resolve()` → `{required, policy_code, steps, snapshot}` | R4：无命中策略 = 免审批（`not_required`），不产生错误 |
| 条件求值 | 同文件 `_condition_matches()`，支持 `= / in / between / >= / <= / is_null`，载体 `value_number / value_text / value_json` | 纯路由判定，无 severity |
| 金额分段 | 步骤上的 `min_amount / max_amount`（R5） | 金额档不是多条策略，而是同一策略的步骤切分 |
| 决策落库 | [document_approval_decision.py](../../meta/services/document_approval_decision.py) | 只写 `status` + `approval_status`，不写校验结论 |

结论：**审批条件与 validation 在代码里本就分开，不需要为这次讨论改实现**，只需把边界写进 spec 防止后续被"合并"。

#### 9.7.4 复用边界

| 层 | 是否复用 | 理由 |
|---|---|---|
| 表达式 / 条件求值器 | **复用** | 避免 `>=` 在两处含义不同 |
| 派生度量（偏差率、可用额度） | **复用** | 一处计算，两处消费 |
| 实体与结果（finding / policy） | **不复用** | 语义不同：数据不合格 vs 需要人点头 |
| severity 与展示通道 | **绝对不复用** | 审批条件不进 warning 列表、不进待办复核通道 |

#### 9.7.5 与 §9.6 severity 的关系

`§9.6` 的 `severity` 只描述**违规的等级**；审批条件**不产生违规**，因此：

- 审批条件命中的结果**不得**塞进 `ValidationDetail[]`（否则 `ok = not errors` 判据被污染）；
- 审批条件**不得**声明 `severity`（它没有"违规"可言）；
- 软容差若同时产生 `warning`，是两个独立结论，分别落 `audit_log`（ack）与 `tasks(type=approval)`（决策），互不覆盖。

#### 9.7.6 三条红线

1. **金额阈值不得写成 validation rule + `severity=error`**：否则 120 万的合法单据被判「数据错误」，用户无法保存——刚性校验被用来表达业务授权，等于把自己锁死。
2. **validation error 不得写成 approval policy**：缺必填项时进审批，审批人无权限改数据，责任错位（数据问题被当成判断问题）。
3. **审批条件不得进 `tasks(type=validation_review)` 通道**：复核是「请你看数据对不对」，审批是「请你决定放不放行」，混入会产生语义错误的待办。

一句话：**校验管「能不能过门」，审批策略管「要不要人点头」；共享求值器与派生度量，不共享实体、结果与展示。**

#### 9.7.7 验收标准

| 编号 | 验收项 | 判据 |
|---|---|---|
| A-1 | 正交性 | 金额超限但校验全过时，单据可保存，且 `approval_status='pending'`、`validation_status='validated'` |
| A-2 | 免审批 | 无命中策略时 `approval_status='not_required'`，不生成 `tasks(type=approval)`，不产生任何 `ValidationDetail` |
| A-3 | 度量单点 | 偏差率在 validation 与 approval 两处取值一致（同值同精度），共用同一派生字段 |
| A-4 | 通道隔离 | 审批条件命中不写入 `errors` / `warnings`；`validation_review` 待办只由 warning 触发 |
| A-5 | 责任归位 | validation `error` 的修复指引指向"修改字段"，审批任务的动作只有 approve / reject |

---

## 10. TBD List

| ID | Item | Missing Information | Next Step |
|---|---|---|---|
| TBD-1 | cardinality allow_reassign | ✅ 已确认：需要支持 | 关闭 |
| TBD-2 | FK 字段推断策略 | ✅ 已确认：命名约定 + semantics 标注可接受 | 关闭 |
| TBD-4 | field_name 翻译支持 | ✅ 已确认：未来考虑，当前返回原始字段名 | 关闭 |
| TBD-5 | severity 处置策略（§9.6 ③ 层） | 处置动作词表与 `rule_type × action` 白名单已由 [spec-rule-model-2026-11-10.md](./spec-rule-model-2026-11-10.md) §9.5 确定；仅剩声明位置未定（`inputs_schema` / `acceptance` / 新增 operation 配置项，建议 `operation.enforcement`） | 按新 spec §9.5.3 矩阵实现，禁止硬编码在拦截器 |

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

# Spec: Phase 3 — CascadeSelect 统一化 + KeyTemplate Number Range 增强

> **版本**: v1.0
> **日期**: 2026-05-26
> **状态**: 📝 草案
> **依赖**: KeyTemplate 引擎（已就绪）、ValueHelp 三层架构（已就绪）

---

## 1. 概述

### 1.1 背景

当前系统存在两套并行的级联配置机制，以及 KeyTemplate 序列引擎缺少 Number Range 管理能力：

| 问题域 | 现状 | 影响 |
|--------|------|------|
| **CascadeSelect** | BO 级 `cascade_select`（原始 dict 列表）与字段级 `parameter_bindings` 两套并行系统 | 配置重复、语义不一致、维护成本高 |
| **KeyTemplate Number Range** | 序列引擎仅支持单调递增，无重置策略、无起始值配置、无 scope 声明式配置 | 无法支持"按月重置编号"等企业级编码需求 |

### 1.2 目标

1. **CascadeSelect 统一化** — 引入 `CascadeSelectConfig` 数据类，加载时自动展开为 `parameter_bindings`，保留 YAML 语法糖，增加后端校验
2. **KeyTemplate Number Range 增强** — 增加序列重置策略（daily/monthly/yearly/never）、起始值配置、scope 声明式配置

---

## 2. 头部产品参考

### 2.1 Cascade / Dependent Picklist

| 产品 | 机制 | 特点 |
|------|------|------|
| **Salesforce** | Dependent Picklist (Field Dependencies) | Controlling Field → Dependent Field，基于 `ValidToContainer` 编码 |
| **SAP S/4HANA** | Value Help with Parameter Binding | `SHLP` 定义参数绑定，父字段值作为过滤参数传递 |
| **ServiceNow** | Dependent Choice | `dependent_value` 属性，choice 表中按父值过滤 |
| **Dynamics 365** | Dependent OptionSet | 父 OptionSet → 子 OptionSet 映射 |

**共同模式**: 父字段值作为子字段的过滤参数，本质是 `parameter_bindings` 语义。

### 2.2 Number Range

| 产品 | 机制 | 特点 |
|------|------|------|
| **SAP S/4HANA** | Number Range Object (SNRO) | 独立对象，支持内部/外部编号、按年重置、分组范围 |
| **Salesforce** | Auto Number | `{PREFIX}-{00000}` 格式，起始值可配 |
| **Odoo** | `ir.sequence` | 支持前缀/后缀/填充/按年重置 |
| **ServiceNow** | Number Maintenance | `sys_number` 表，支持多租户独立编号 |

**共同模式**: 序列号 + 重置策略 + 起始值 + 分组隔离。

---

## 3. 现状分析

### 3.1 CascadeSelect 现状

#### 3.1.1 数据模型

[models.py:1715](file:///d:/filework/excel-to-diagram/meta/core/models.py#L1715) — `MetaObject.cascade_select`:

```python
cascade_select: Optional[List[Dict[str, Any]]] = None
```

原始 `Dict[str, Any]` 列表，无专用数据类，无校验。

#### 3.1.2 YAML 格式

[relationship.yaml:76-108](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml#L76-L108):

```yaml
cascade_select:
  - field: source_domain_id
    parent_object: domain
    parent_display_field: name
    filter_by: version_id
  - field: source_sub_domain_id
    parent_object: sub_domain
    parent_display_field: name
    filter_by: source_domain_id
  - field: source_bo_id
    parent_object: business_object
    parent_display_field: name
    filter_by: source_service_module_id
```

当前使用 `cascade_select` 的对象：

| 对象 | cascade_select 条目数 | 层级深度 |
|------|----------------------|---------|
| business_object | 3 | domain → sub_domain → service_module |
| relationship | 8 | source 4级 + target 4级 |
| domain | 1 | sub_domain |
| sub_domain | 1 | service_module |
| service_module | 1 | business_object |

#### 3.1.3 解析逻辑

[yaml_loader.py:1030-1037](file:///d:/filework/excel-to-diagram/meta/core/yaml_loader.py#L1030-L1037):

```python
def parse_cascade_select(data: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
    """解析级联选择配置"""
    cascade = data.get('cascade_select')
    if cascade is None:
        return None
    if isinstance(cascade, list):
        return cascade
    return None
```

纯透传，无校验、无转换。

#### 3.1.4 前端消费

[useCascadeSelect.js](file:///d:/filework/excel-to-diagram/src/composables/useCascadeSelect.js):

```javascript
const cascadeConfig = computed(() => {
  if (!metaObject.value) return []
  return metaObject.value.cascade_select || []
})

const cascadeChain = computed(() => {
  const chain = {}
  cascadeConfig.value.forEach(function(config) {
    chain[config.field] = {
      field: config.field,
      parentField: config.filter_by,
      parentObject: config.parent_object,
      displayField: config.parent_display_field || 'name'
    }
  })
  return chain
})
```

前端直接消费 `cascade_select` 原始 dict，映射 `filter_by` → `parentField`。

#### 3.1.5 ValueHelp Parameter Bindings

[models.py:482-517](file:///d:/filework/excel-to-diagram/meta/core/models.py#L482-L517):

```python
@dataclass
class ValueHelpParameterBinding:
    local_field: str = ""
    target_field: str = ""
    required: bool = False
    constant: str = ""

@dataclass
class ValueHelpBehavior:
    binding_strength: str = "strict"
    validation: bool = True
    search_fields: List[str] = field(default_factory=list)
    min_search_length: int = 0
    debounce_ms: int = 300
    multiple: bool = False
    parameter_bindings: List[ValueHelpParameterBinding] = field(default_factory=list)
    enabled_condition: str = ""
```

字段级 `parameter_bindings` 提供细粒度的过滤参数绑定，前端通过 `useValueHelp` 消费。

#### 3.1.6 问题：两套并行系统

```
cascade_select (BO 级)                    parameter_bindings (字段级)
─────────────────────                    ──────────────────────────
• 全局级联策略声明                         • 字段级过滤参数绑定
• 声明式：field + filter_by + parent      • 命令式：local_field + target_field
• 前端：useCascadeSelect                  • 前端：useValueHelp
• 无校验                                  • 有校验
• 原始 dict 列表                          • 类型化 dataclass

问题：
1. 语义重叠 — cascade_select 的 filter_by 本质就是 parameter_binding
2. 配置重复 — 同一个过滤关系在两处各写一遍
3. 维护成本 — 改一处忘改另一处
4. 无校验 — cascade_select 无后端校验，YAML 写错无提示
```

### 3.2 KeyTemplate Number Range 现状

#### 3.2.1 KeyTemplateConfig

[key_template_engine.py:19-43](file:///d:/filework/excel-to-diagram/meta/core/key_template_engine.py#L19-L43):

```python
@dataclass
class KeyTemplateConfig:
    object_id: str
    enabled: bool = False
    auto_suggest: bool = True
    pattern: str = ""
    separator: str = "_"
    segments: List[Dict[str, Any]] = field(default_factory=list)
    preview: str = ""
    scope: Optional[str] = None
```

缺少：`sequence` 子配置（start、reset、padding、scope）。

#### 3.2.2 SequenceEngine

[key_template_engine.py:46-134](file:///d:/filework/excel-to-diagram/meta/core/key_template_engine.py#L46-L134):

```python
class SequenceEngine:
    def __init__(self, data_source):
        self._data_source = data_source
        self._lock = threading.Lock()

    def next_value(self, sequence_name: str, start: int = 1) -> int: ...
    def peek_value(self, sequence_name: str, start: int = 1) -> int: ...
    def auto_detect_start(self, ...) -> int: ...
    def reset_sequence(self, sequence_name: str): ...
```

`_sequences` 表结构：

```sql
CREATE TABLE IF NOT EXISTS _sequences (
    sequence_name TEXT PRIMARY KEY,
    current_value INTEGER NOT NULL DEFAULT 0
)
```

缺少：
- 重置策略（reset policy）
- 重置时间戳追踪
- 起始值持久化

#### 3.2.3 当前 YAML 配置

[business_object.yaml:99-116](file:///d:/filework/excel-to-diagram/meta/schemas/business_object.yaml#L99-L116):

```yaml
key_template:
  enabled: true
  auto_suggest: true
  pattern: "{service_module_code}_{SEQ:4}"
  separator: "_"
  segments:
    - type: parent_field
      source: service_module_code
      transform: upper
    - type: separator
      value: "_"
    - type: sequence
      name: bo_code_seq
      scope: service_module_code
      auto_detect: true
      padding: 4
      start: 1
  preview: "ORDER_SVC_0001"
```

序列配置散落在 `segments` 中，缺少顶层 `sequence` 配置块。

#### 3.2.4 KeyTemplateInterceptor

[key_template_interceptor.py](file:///d:/filework/excel-to-diagram/meta/core/interceptors/key_template_interceptor.py):

- 优先级 45，`before_action`，仅 CREATE
- 检查 `key_template.enabled` 和 `auto_suggest`
- 用户已提供 code 则跳过
- 从 DB 解析父字段值
- 调用 `engine.generate_code()`

---

## 4. 功能需求

### FR-301: CascadeSelectConfig 数据类

- **Description**: 系统 MUST 引入 `CascadeSelectConfig` 数据类替代原始 `Dict[str, Any]`，提供类型安全和校验能力。
- **Acceptance Criteria**:
  - AC-001: `CascadeSelectConfig` 包含 `field`、`filter_by`、`parent_object`、`parent_display_field`、`group`、`level`、`condition` 属性
  - AC-002: `MetaObject.cascade_select` 类型从 `Optional[List[Dict[str, Any]]]` 变更为 `Optional[List[CascadeSelectConfig]]`
  - AC-003: `parse_cascade_select()` 返回 `Optional[List[CascadeSelectConfig]]`
  - AC-004: 解析时校验 `field` 必须存在于 `MetaObject.fields` 中
  - AC-005: 解析时校验 `filter_by` 引用的字段必须存在
  - AC-006: 解析时校验 `parent_object` 引用的对象必须存在
  - AC-007: 校验失败时记录 WARNING 日志并跳过该条目（不中断加载）
- **Priority**: Must
- **Type Mapping**: Solution / Functional

### FR-302: CascadeSelect 自动展开为 Parameter Bindings

- **Description**: 系统 MUST 在加载时自动将 `cascade_select` 展开为对应字段的 `parameter_bindings`，消除两套系统的配置重复。
- **Acceptance Criteria**:
  - AC-001: 对每个 `CascadeSelectConfig`，自动在 `filter_by` 字段的 `value_help.behavior.parameter_bindings` 中追加绑定
  - AC-002: 展开规则：`local_field = filter_by`，`target_field = "id"`，`required = True`
  - AC-003: 如果字段已有 `parameter_bindings`，追加而非覆盖
  - AC-004: 展开后的 `parameter_bindings` 与手写的 `parameter_bindings` 行为一致
  - AC-005: 前端 `useValueHelp` 无需修改即可消费展开后的绑定
- **Priority**: Must
- **Type Mapping**: Solution / Functional

### FR-303: CascadeSelect 保留为 YAML 语法糖

- **Description**: `cascade_select` 在 YAML 中保留为声明式语法糖，运行时统一由 `parameter_bindings` 驱动。
- **Acceptance Criteria**:
  - AC-001: YAML 中 `cascade_select` 语法不变
  - AC-002: 前端 `useCascadeSelect` 继续消费 `cascade_select` 配置（用于级联链构建）
  - AC-003: 前端 `useValueHelp` 消费展开后的 `parameter_bindings`（用于值帮助过滤）
  - AC-004: 两套前端消费路径并存，各司其职
- **Priority**: Must
- **Type Mapping**: Solution / Functional

### FR-304: CascadeSelect 后端校验

- **Description**: 系统 MUST 在加载时校验 `cascade_select` 配置的一致性。
- **Acceptance Criteria**:
  - AC-001: 校验 `filter_by` 引用的字段在 `cascade_select` 链中存在（或为 `context` 字段）
  - AC-002: 校验级联链无循环依赖
  - AC-003: 校验同一 `group` 内的 `level` 连续且唯一
  - AC-004: 校验 `parent_object` 与字段的 `value_help.source.target_bo` 一致（如果两者都配置了）
  - AC-005: 校验结果以 WARNING 日志输出，不阻断加载
- **Priority**: Should
- **Type Mapping**: Solution / Functional

### FR-305: KeyTemplate Sequence 配置增强

- **Description**: 系统 MUST 在 `KeyTemplateConfig` 中增加 `sequence` 子配置，支持起始值、重置策略和 scope 声明。
- **Acceptance Criteria**:
  - AC-001: `KeyTemplateConfig` 新增 `sequence: Optional[SequenceConfig]` 字段
  - AC-002: `SequenceConfig` 包含 `start: int`（默认 1）、`reset: str`（"never"|"daily"|"monthly"|"yearly"）、`padding: int`（默认从 `SEQ:N` 推导）、`scope: str`（"global"|"per_parent"|自定义字段名）
  - AC-003: YAML 配置支持 `key_template.sequence` 配置块
  - AC-004: 向后兼容：无 `sequence` 配置时，从 `segments` 中提取序列参数（现有行为）
  - AC-005: `sequence` 配置优先于 `segments` 中的序列参数
- **Priority**: Must
- **Type Mapping**: Solution / Functional

### FR-306: SequenceEngine 重置策略

- **Description**: 系统 MUST 支持序列号按时间周期重置。
- **Acceptance Criteria**:
  - AC-001: `SequenceEngine.next_value()` 支持根据 `reset` 策略判断是否需要重置
  - AC-002: `_sequences` 表新增 `last_reset_at TEXT` 列，记录上次重置时间
  - AC-003: `daily` 重置：跨日时自动重置 `current_value` 为 `start - 1`
  - AC-004: `monthly` 重置：跨月时自动重置
  - AC-005: `yearly` 重置：跨年时自动重置
  - AC-006: `never` 重置：永不重置（当前行为）
  - AC-007: 重置时保留 `last_reset_at` 时间戳
  - AC-008: 重置后序列名包含周期标识（如 `bo_code_seq:ORDER_SVC:2026-05`）
  - AC-009: 并发安全：重置操作在 `threading.Lock` 保护下执行
- **Priority**: Must
- **Type Mapping**: Solution / Functional

### FR-307: KeyTemplate YAML Sequence 配置

- **Description**: YAML 配置支持声明式 `sequence` 配置块。
- **Acceptance Criteria**:
  - AC-001: 支持 `key_template.sequence` 顶层配置块
  - AC-002: `sequence` 配置块包含 `start`、`reset`、`padding`、`scope` 属性
  - AC-003: 现有 `segments` 中的序列配置继续有效（向后兼容）
  - AC-004: `sequence` 配置与 `segments` 序列配置冲突时，`sequence` 优先
- **Priority**: Must
- **Type Mapping**: Solution / Functional

---

## 5. 非功能需求

### NFR-301: 向后兼容

- **Description**: 所有变更必须向后兼容，现有 YAML 配置无需修改。
- **Measurement**: 现有 5 个对象的 `cascade_select` 和 3 个对象的 `key_template` 配置无需任何修改即可正常运行。
- **Priority**: Must

### NFR-302: 性能

- **Description**: 序列重置检查不应显著影响编码生成性能。
- **Measurement**: `next_value()` 增加重置检查后，单次调用耗时增加 < 1ms。
- **Priority**: Should

### NFR-303: 并发安全

- **Description**: 序列重置操作必须与序列递增操作在同一个锁范围内。
- **Measurement**: 并发场景下无序列号冲突。
- **Priority**: Must

### NFR-304: 可测试性

- **Description**: 所有新功能必须有单元测试覆盖。
- **Measurement**: 新增代码测试覆盖率 > 80%。
- **Priority**: Must

---

## 6. 外部接口需求

### IF-301: CascadeSelectConfig API

- **Type**: 内部模型
- **变更**: `GET /api/v2/meta/<object_type>` 返回的 `cascade_select` 从 `List[Dict]` 变为 `List[CascadeSelectConfig]` 的序列化格式
- **兼容性**: 序列化后的 JSON 结构与现有 dict 格式一致，前端无需修改

### IF-302: KeyTemplate Config API

- **Type**: API
- **Endpoint**: `GET /api/v2/key-template/config/<object_type>`
- **变更**: 返回结果新增 `sequence` 配置块
- **Response 示例**:

```json
{
  "object_id": "business_object",
  "enabled": true,
  "auto_suggest": true,
  "pattern": "{service_module_code}_{SEQ:4}",
  "sequence": {
    "start": 1,
    "reset": "never",
    "padding": 4,
    "scope": "service_module_code"
  },
  "preview": "ORDER_SVC_0001"
}
```

### IF-303: YAML 配置扩展

**CascadeSelect 扩展属性**（可选，增强校验）:

```yaml
cascade_select:
  - field: source_domain_id
    parent_object: domain
    parent_display_field: name
    filter_by: version_id
    group: source          # 新增：分组标识
    level: 1               # 新增：层级序号
  - field: source_sub_domain_id
    parent_object: sub_domain
    parent_display_field: name
    filter_by: source_domain_id
    group: source
    level: 2
    condition:             # 新增：条件过滤
      field: source_domain_id
      operator: not_empty
```

**KeyTemplate Sequence 配置**:

```yaml
key_template:
  enabled: true
  auto_suggest: true
  pattern: "{service_module_code}_{SEQ:4}"
  separator: "_"
  sequence:                 # 新增：序列配置块
    start: 1
    reset: never            # never | daily | monthly | yearly
    padding: 4              # 0 填充位数
    scope: service_module_code  # global | per_parent | 字段名
  segments: [...]           # 保留，向后兼容
  preview: "ORDER_SVC_0001"
```

---

## 7. 迁移需求

### TR-301: CascadeSelect 类型迁移

- **Description**: `MetaObject.cascade_select` 类型从 `Optional[List[Dict[str, Any]]]` 变更为 `Optional[List[CascadeSelectConfig]]`
- **Strategy**:
  - `CascadeSelectConfig` 实现序列化方法 `to_dict()`，确保 JSON 输出与现有格式一致
  - 前端 `useCascadeSelect` 消费的属性名（`field`、`filter_by`、`parent_object`、`parent_display_field`）保持不变
  - 新增属性（`group`、`level`、`condition`）为可选，默认值不影响现有行为
- **Rollback Plan**: 恢复 `cascade_select` 类型为 `Optional[List[Dict[str, Any]]]`

### TR-302: _sequences 表结构变更

- **Description**: `_sequences` 表新增 `last_reset_at TEXT` 列
- **Strategy**:
  - 使用 `ALTER TABLE _sequences ADD COLUMN last_reset_at TEXT` 增量迁移
  - 现有记录 `last_reset_at = NULL`，视为"永不重置"
  - `SequenceEngine._ensure_table()` 更新建表 SQL
- **Rollback Plan**: 忽略新增列

### TR-303: KeyTemplateConfig 字段扩展

- **Description**: `KeyTemplateConfig` 新增 `sequence: Optional[SequenceConfig]` 字段
- **Strategy**:
  - `SequenceConfig` 默认为 `None`
  - `from_dict()` 优先读取 `sequence` 配置块，回退到 `segments` 中提取
  - 现有 YAML 无 `sequence` 配置块时，行为不变
- **Rollback Plan**: 移除 `sequence` 字段

---

## 8. 优先级与里程碑

| ID | 需求 | 优先级 | 理由 |
|----|------|--------|------|
| FR-301 | CascadeSelectConfig 数据类 | Must | 类型安全基础 |
| FR-302 | 自动展开为 Parameter Bindings | Must | 消除配置重复 |
| FR-303 | 保留 YAML 语法糖 | Must | 向后兼容 |
| FR-304 | 后端校验 | Should | 提升配置质量 |
| FR-305 | Sequence 配置增强 | Must | Number Range 基础 |
| FR-306 | SequenceEngine 重置策略 | Must | 企业级编码需求 |
| FR-307 | YAML Sequence 配置 | Must | 声明式配置 |

**建议里程碑**:

- **Milestone 1**（3天）：FR-301 + FR-302 + FR-303 — CascadeSelect 统一化
- **Milestone 2**（3天）：FR-305 + FR-306 + FR-307 — KeyTemplate Number Range
- **Milestone 3**（1天）：FR-304 — 后端校验增强

---

## 9. 设计方案 (RFC)

### 9.1 As-Is 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     CascadeSelect 现状                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  YAML (relationship.yaml)                                       │
│  ┌──────────────────────────────┐                               │
│  │ cascade_select:               │                               │
│  │   - field: source_domain_id   │    字段级 value_help:         │
│  │     filter_by: version_id     │    ┌────────────────────┐    │
│  │     parent_object: domain     │    │ parameter_bindings: │    │
│  │   - field: source_sub_dom_id  │    │   - local_field: .. │    │
│  │     filter_by: source_dom_id  │    │     target_field: ..│    │
│  └──────────┬───────────────────┘    └────────────────────┘    │
│             │                              │                     │
│             ▼                              ▼                     │
│  parse_cascade_select()          ValueHelpBehavior               │
│  (透传，无校验)                   .parameter_bindings             │
│             │                              │                     │
│             ▼                              ▼                     │
│  MetaObject.cascade_select      前端 useValueHelp               │
│  = List[Dict[str, Any]]         (字段级过滤)                    │
│             │                                                    │
│             ▼                                                    │
│  前端 useCascadeSelect                                           │
│  (级联链构建)                                                    │
│                                                                  │
│  ❌ 两套系统，配置重复，无校验                                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     KeyTemplate Number Range 现状                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  KeyTemplateConfig          SequenceEngine                      │
│  ┌──────────────────┐      ┌──────────────────────┐            │
│  │ object_id         │      │ _sequences 表         │            │
│  │ enabled           │      │  sequence_name (PK)   │            │
│  │ auto_suggest      │      │  current_value        │            │
│  │ pattern           │─────▶│                       │            │
│  │ segments [...]    │      │ ❌ 无 last_reset_at    │            │
│  │ preview           │      │ ❌ 无重置策略          │            │
│  │ ❌ 无 sequence    │      │ ❌ 无起始值持久化      │            │
│  └──────────────────┘      └──────────────────────┘            │
│                                                                 │
│  YAML: 序列配置散落在 segments 中                                │
│  ❌ 无声明式 sequence 配置块                                     │
│  ❌ 无重置策略 (daily/monthly/yearly)                            │
│  ❌ 无 scope 声明式配置                                         │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 Target 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     CascadeSelect 统一化                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  YAML (relationship.yaml) — 语法糖，不变                        │
│  ┌──────────────────────────────┐                               │
│  │ cascade_select:               │                               │
│  │   - field: source_domain_id   │                               │
│  │     filter_by: version_id     │                               │
│  │     parent_object: domain     │                               │
│  │     group: source             │                               │
│  │     level: 1                  │                               │
│  └──────────┬───────────────────┘                               │
│             │                                                    │
│             ▼                                                    │
│  parse_cascade_select() — 类型化 + 校验                         │
│  → List[CascadeSelectConfig]                                    │
│             │                                                    │
│             ├──────────────────────────────┐                     │
│             ▼                              ▼                     │
│  MetaObject.cascade_select     自动展开为                       │
│  = List[CascadeSelectConfig]   parameter_bindings               │
│             │                              │                     │
│             ▼                              ▼                     │
│  前端 useCascadeSelect         前端 useValueHelp                │
│  (级联链构建)                  (字段级过滤)                     │
│                                                                  │
│  ✅ 单一配置源，自动展开，有校验                                 │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     KeyTemplate Number Range 增强                │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  KeyTemplateConfig              SequenceEngine                  │
│  ┌──────────────────────┐      ┌──────────────────────┐        │
│  │ object_id             │      │ _sequences 表         │        │
│  │ enabled               │      │  sequence_name (PK)   │        │
│  │ auto_suggest          │      │  current_value        │        │
│  │ pattern               │      │  last_reset_at ✨NEW  │        │
│  │ sequence ✨NEW ────────│─────▶│                       │        │
│  │   start: 1            │      │ ✅ 重置策略检查        │        │
│  │   reset: never        │      │ ✅ 周期性序列名        │        │
│  │   padding: 4          │      │ ✅ 起始值持久化        │        │
│  │   scope: per_parent   │      └──────────────────────┘        │
│  │ segments [...]        │                                      │
│  │ preview               │      YAML:                           │
│  └──────────────────────┘      ┌──────────────────────┐        │
│                                │ key_template:         │        │
│                                │   sequence: ✨NEW     │        │
│                                │     start: 1          │        │
│                                │     reset: monthly    │        │
│                                │     padding: 4        │        │
│                                │     scope: per_parent │        │
│                                └──────────────────────┘        │
└─────────────────────────────────────────────────────────────────┘
```

### 9.3 详细设计

#### 9.3.1 CascadeSelectConfig 数据类

**文件**: `meta/core/models.py`

```python
@dataclass
class CascadeSelectCondition:
    field: str = ""
    operator: str = ""       # not_empty | is_empty | eq | neq
    value: Any = None

@dataclass
class CascadeSelectConfig:
    field: str = ""
    filter_by: str = ""
    parent_object: str = ""
    parent_display_field: str = "name"
    group: str = ""
    level: int = 0
    condition: Optional[CascadeSelectCondition] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "field": self.field,
            "filter_by": self.filter_by,
            "parent_object": self.parent_object,
            "parent_display_field": self.parent_display_field,
        }
        if self.group:
            result["group"] = self.group
        if self.level:
            result["level"] = self.level
        if self.condition:
            result["condition"] = {
                "field": self.condition.field,
                "operator": self.condition.operator,
                "value": self.condition.value,
            }
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CascadeSelectConfig":
        condition = None
        cond_data = data.get("condition")
        if cond_data and isinstance(cond_data, dict):
            condition = CascadeSelectCondition(
                field=cond_data.get("field", ""),
                operator=cond_data.get("operator", ""),
                value=cond_data.get("value"),
            )
        return cls(
            field=data.get("field", ""),
            filter_by=data.get("filter_by", ""),
            parent_object=data.get("parent_object", ""),
            parent_display_field=data.get("parent_display_field", "name"),
            group=data.get("group", ""),
            level=data.get("level", 0),
            condition=condition,
        )
```

**MetaObject 变更**:

```python
# models.py L1715 — 变更前
cascade_select: Optional[List[Dict[str, Any]]] = None

# models.py L1715 — 变更后
cascade_select: Optional[List[CascadeSelectConfig]] = None
```

#### 9.3.2 parse_cascade_select 增强

**文件**: `meta/core/yaml_loader.py`

```python
def parse_cascade_select(data: Dict[str, Any]) -> Optional[List[CascadeSelectConfig]]:
    """解析级联选择配置，返回类型化列表"""
    cascade = data.get('cascade_select')
    if cascade is None:
        return None
    if not isinstance(cascade, list):
        return None

    result = []
    for item in cascade:
        if not isinstance(item, dict):
            logger.warning(f"[parse_cascade_select] 跳过非 dict 条目: {item}")
            continue
        config = CascadeSelectConfig.from_dict(item)
        if not config.field:
            logger.warning(f"[parse_cascade_select] 跳过无 field 的条目: {item}")
            continue
        if not config.filter_by:
            logger.warning(f"[parse_cascade_select] 跳过无 filter_by 的条目: {item}")
            continue
        result.append(config)
    return result if result else None
```

#### 9.3.3 CascadeSelect 自动展开为 Parameter Bindings

**文件**: `meta/core/yaml_loader.py` — 在 `_build_meta_object()` 中增加展开逻辑

```python
def _expand_cascade_to_parameter_bindings(meta_obj: MetaObject) -> None:
    """将 cascade_select 自动展开为对应字段的 parameter_bindings"""
    if not meta_obj.cascade_select:
        return

    for cascade in meta_obj.cascade_select:
        target_field_id = cascade.field
        parent_field_id = cascade.filter_by

        field_meta = None
        for f in meta_obj.fields:
            if f.id == target_field_id:
                field_meta = f
                break

        if not field_meta:
            logger.warning(
                f"[cascade_expand] 字段 '{target_field_id}' 不存在于 "
                f"'{meta_obj.object_id}'，跳过展开"
            )
            continue

        if not field_meta.value_help:
            continue

        if not field_meta.value_help.behavior:
            continue

        binding = ValueHelpParameterBinding(
            local_field=parent_field_id,
            target_field="id",
            required=True,
        )

        existing = field_meta.value_help.behavior.parameter_bindings
        already_exists = any(
            b.local_field == parent_field_id and b.target_field == "id"
            for b in existing
        )
        if not already_exists:
            existing.append(binding)
```

**调用时机**: 在 `_build_meta_object()` 中，`parse_cascade_select()` 之后、返回 `meta_obj` 之前调用。

#### 9.3.4 CascadeSelect 校验

**文件**: `meta/core/yaml_loader.py`

```python
def _validate_cascade_select(meta_obj: MetaObject) -> None:
    """校验 cascade_select 配置一致性"""
    if not meta_obj.cascade_select:
        return

    field_ids = {f.id for f in meta_obj.fields}
    cascade_fields = {c.field for c in meta_obj.cascade_select}
    context_field = None
    if meta_obj.context:
        context_field = meta_obj.context.get("field")

    for cascade in meta_obj.cascade_select:
        if cascade.field not in field_ids:
            logger.warning(
                f"[cascade_validate] '{meta_obj.object_id}': "
                f"cascade field '{cascade.field}' 不存在于字段列表"
            )

        if cascade.filter_by not in field_ids and cascade.filter_by != context_field:
            if cascade.filter_by not in cascade_fields:
                logger.warning(
                    f"[cascade_validate] '{meta_obj.object_id}': "
                    f"filter_by '{cascade.filter_by}' 既不是字段也不是级联字段"
                )

        if cascade.parent_object:
            from meta.core.yaml_loader import _meta_registry
            if _meta_registry and cascade.parent_object not in _meta_registry:
                logger.warning(
                    f"[cascade_validate] '{meta_obj.object_id}': "
                    f"parent_object '{cascade.parent_object}' 未注册"
                )

    groups = {}
    for cascade in meta_obj.cascade_select:
        if cascade.group:
            groups.setdefault(cascade.group, []).append(cascade)

    for group_name, items in groups.items():
        levels = [c.level for c in items if c.level > 0]
        if levels and len(levels) != len(set(levels)):
            logger.warning(
                f"[cascade_validate] '{meta_obj.object_id}': "
                f"group '{group_name}' 存在重复 level"
            )

    visited = set()
    for cascade in meta_obj.cascade_select:
        path = []
        current = cascade
        while current and current.filter_by:
            if current.field in path:
                logger.warning(
                    f"[cascade_validate] '{meta_obj.object_id}': "
                    f"级联链存在循环依赖: {' → '.join(path)} → {current.field}"
                )
                break
            path.append(current.field)
            parent = next(
                (c for c in meta_obj.cascade_select if c.field == current.filter_by),
                None
            )
            current = parent
```

#### 9.3.5 SequenceConfig 数据类

**文件**: `meta/core/key_template_engine.py`

```python
@dataclass
class SequenceConfig:
    start: int = 1
    reset: str = "never"         # never | daily | monthly | yearly
    padding: int = 0             # 0 表示从 SEQ:N 推导
    scope: str = "global"        # global | per_parent | 字段名

    RESET_POLICIES = frozenset({"never", "daily", "monthly", "yearly"})

    def __post_init__(self):
        if self.reset not in self.RESET_POLICIES:
            raise ValueError(
                f"Invalid reset policy: {self.reset}. "
                f"Must be one of {self.RESET_POLICIES}"
            )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SequenceConfig":
        if not data:
            return cls()
        return cls(
            start=data.get("start", 1),
            reset=data.get("reset", "never"),
            padding=data.get("padding", 0),
            scope=data.get("scope", "global"),
        )

    @classmethod
    def from_segments(cls, segments: List[Dict[str, Any]]) -> "SequenceConfig":
        """从 segments 中提取序列配置（向后兼容）"""
        for seg in segments:
            if seg.get("type") == "sequence":
                return cls(
                    start=seg.get("start", 1),
                    reset="never",
                    padding=seg.get("padding", 0),
                    scope=seg.get("scope", "global"),
                )
        return cls()
```

**KeyTemplateConfig 变更**:

```python
@dataclass
class KeyTemplateConfig:
    object_id: str
    enabled: bool = False
    auto_suggest: bool = True
    pattern: str = ""
    separator: str = "_"
    segments: List[Dict[str, Any]] = field(default_factory=list)
    preview: str = ""
    scope: Optional[str] = None
    sequence: Optional[SequenceConfig] = None       # ✨ NEW

    @classmethod
    def from_dict(cls, object_id: str, data: Dict[str, Any]) -> "KeyTemplateConfig":
        if not data:
            return cls(object_id=object_id, enabled=False)

        sequence = None
        seq_data = data.get("sequence")
        if seq_data and isinstance(seq_data, dict):
            sequence = SequenceConfig.from_dict(seq_data)
        elif data.get("segments"):
            sequence = SequenceConfig.from_segments(data.get("segments", []))

        return cls(
            object_id=object_id,
            enabled=data.get("enabled", False),
            auto_suggest=data.get("auto_suggest", True),
            pattern=data.get("pattern", ""),
            separator=data.get("separator", "_"),
            segments=data.get("segments", []),
            preview=data.get("preview", ""),
            scope=data.get("scope"),
            sequence=sequence,
        )
```

#### 9.3.6 _sequences 表结构变更

```sql
-- 变更前
CREATE TABLE IF NOT EXISTS _sequences (
    sequence_name TEXT PRIMARY KEY,
    current_value INTEGER NOT NULL DEFAULT 0
);

-- 变更后
CREATE TABLE IF NOT EXISTS _sequences (
    sequence_name TEXT PRIMARY KEY,
    current_value INTEGER NOT NULL DEFAULT 0,
    last_reset_at TEXT DEFAULT NULL
);
```

**迁移 SQL**:

```sql
ALTER TABLE _sequences ADD COLUMN last_reset_at TEXT DEFAULT NULL;
```

#### 9.3.7 SequenceEngine 重置策略

**文件**: `meta/core/key_template_engine.py`

```python
class SequenceEngine:

    def __init__(self, data_source):
        self._data_source = data_source
        self._lock = threading.Lock()
        self._ensure_table()

    def _ensure_table(self):
        try:
            self._data_source.execute(_CREATE_TABLE_SQL)
            self._data_source.commit()
            try:
                self._data_source.execute(
                    "ALTER TABLE _sequences ADD COLUMN last_reset_at TEXT DEFAULT NULL"
                )
                self._data_source.commit()
            except Exception:
                pass
        except Exception as e:
            logger.debug(f"[SequenceEngine] Table ensure: {e}")

    def _should_reset(self, sequence_name: str, reset_policy: str) -> bool:
        """检查序列是否需要按策略重置"""
        if reset_policy == "never":
            return False

        cursor = self._data_source.execute(
            f"SELECT last_reset_at FROM {_SEQUENCES_TABLE} WHERE sequence_name = ?",
            (sequence_name,)
        )
        row = cursor.fetchone()
        if not row:
            return False

        last_reset = row[0] if not isinstance(row, dict) else row.get("last_reset_at")
        if not last_reset:
            return False

        from datetime import datetime
        try:
            last_dt = datetime.fromisoformat(last_reset)
            now = datetime.now()
            if reset_policy == "daily":
                return last_dt.date() < now.date()
            elif reset_policy == "monthly":
                return (last_dt.year, last_dt.month) < (now.year, now.month)
            elif reset_policy == "yearly":
                return last_dt.year < now.year
        except (ValueError, TypeError):
            pass
        return False

    def _do_reset(self, sequence_name: str, start: int = 1) -> None:
        """执行序列重置"""
        from datetime import datetime
        now_str = datetime.now().isoformat()
        self._data_source.execute(
            f"UPDATE {_SEQUENCES_TABLE} SET current_value = ?, last_reset_at = ? "
            f"WHERE sequence_name = ?",
            (start - 1, now_str, sequence_name)
        )
        self._data_source.commit()

    def next_value(self, sequence_name: str, start: int = 1,
                   reset_policy: str = "never") -> int:
        with self._lock:
            try:
                self._data_source.execute(
                    f"INSERT OR IGNORE INTO {_SEQUENCES_TABLE} "
                    f"(sequence_name, current_value) VALUES (?, ?)",
                    (sequence_name, start - 1)
                )
                self._data_source.commit()

                if self._should_reset(sequence_name, reset_policy):
                    self._do_reset(sequence_name, start)

                self._data_source.execute(
                    f"UPDATE {_SEQUENCES_TABLE} SET current_value = current_value + 1 "
                    f"WHERE sequence_name = ?",
                    (sequence_name,)
                )
                self._data_source.commit()
                cursor = self._data_source.execute(
                    f"SELECT current_value FROM {_SEQUENCES_TABLE} WHERE sequence_name = ?",
                    (sequence_name,)
                )
                row = cursor.fetchone()
                if row:
                    if isinstance(row, dict):
                        return row["current_value"]
                    return row[0]
                return start
            except Exception as e:
                logger.error(f"[SequenceEngine] next_value failed: {e}")
                raise

    def build_periodic_sequence_name(self, base_name: str,
                                      scope_key: str,
                                      reset_policy: str) -> str:
        """构建包含周期标识的序列名"""
        if reset_policy == "never":
            return f"{base_name}:{scope_key}"

        from datetime import datetime
        now = datetime.now()
        if reset_policy == "daily":
            period = now.strftime("%Y-%m-%d")
        elif reset_policy == "monthly":
            period = now.strftime("%Y-%m")
        elif reset_policy == "yearly":
            period = now.strftime("%Y")
        else:
            period = "default"

        return f"{base_name}:{scope_key}:{period}"
```

#### 9.3.8 KeyTemplateEngine 集成

**文件**: `meta/core/key_template_engine.py`

```python
class KeyTemplateEngine:

    def generate_code(self, config: KeyTemplateConfig, field_values: Dict[str, Any],
                      object_type: str = "") -> Optional[str]:
        if not config.enabled or not config.pattern:
            return None

        tokens = self._parser.parse(config.pattern)
        segments = config.segments

        seq_config = config.sequence or SequenceConfig.from_segments(segments)

        scope_key = config.object_id
        if seq_config and seq_config.scope != "global":
            scope_vals = self._parser.build_scope_key(
                segments, field_values, "default"
            )
            scope_key = scope_vals

        sequence_name = f"{config.object_id}_seq"
        for seg in segments:
            if seg.get("type") == "sequence":
                sequence_name = seg.get("name", f"{config.object_id}_seq")
                break

        full_seq_name = self._sequence_engine.build_periodic_sequence_name(
            sequence_name, scope_key, seq_config.reset
        )

        auto_detect = any(
            seg.get("type") == "sequence" and seg.get("auto_detect", False)
            for seg in segments
        )
        seq_start = seq_config.start if seq_config else 1
        table_name = config.object_id

        if auto_detect and self._data_source:
            try:
                detected = self._sequence_engine.auto_detect_start(
                    full_seq_name, table_name, "code"
                )
                if detected > seq_start:
                    seq_start = detected
            except Exception:
                pass

        reset_policy = seq_config.reset if seq_config else "never"
        seq_value = self._sequence_engine.next_value(
            full_seq_name, start=seq_start, reset_policy=reset_policy
        )

        padding = seq_config.padding if seq_config and seq_config.padding > 0 else 0
        code = self._parser.resolve(tokens, field_values, seq_value)

        return code
```

### 9.4 备选方案

| 选项 | 优点 | 缺点 | 决策 |
|------|------|------|------|
| CascadeSelect: 保留两套系统 | 无迁移成本 | 配置重复、维护成本高 | ❌ 拒绝 |
| CascadeSelect: 移除 cascade_select，统一用 parameter_bindings | 单一配置源 | YAML 可读性差，前端需大改 | ❌ 拒绝 |
| **CascadeSelect: 保留语法糖 + 自动展开** | **兼顾可读性和单一来源** | **展开逻辑需维护** | ✅ 采纳 |
| Number Range: 基于定时任务重置 | 精确控制 | 复杂度高，需调度器 | ❌ 拒绝 |
| **Number Range: 基于序列名包含周期标识** | **简单、无状态、并发安全** | **旧周期序列记录不自动清理** | ✅ 采纳 |
| Number Range: 单独 Number Range 表 | 独立管理 | 过度设计 | ❌ 拒绝 |

### 9.5 实施计划

**实施顺序**:

1. **Day 1-2**: CascadeSelect 统一化
   - 新增 `CascadeSelectConfig`、`CascadeSelectCondition` 数据类
   - 修改 `MetaObject.cascade_select` 类型
   - 增强 `parse_cascade_select()`
   - 实现 `_expand_cascade_to_parameter_bindings()`
   - 实现 `_validate_cascade_select()`
   - 单元测试

2. **Day 3-4**: KeyTemplate Number Range
   - 新增 `SequenceConfig` 数据类
   - 修改 `KeyTemplateConfig` 增加 `sequence` 字段
   - 修改 `_sequences` 表结构
   - 增强 `SequenceEngine` 重置策略
   - 修改 `KeyTemplateEngine.generate_code()` 集成
   - 单元测试

3. **Day 5**: 集成验证 + YAML 更新
   - 现有 5 个对象 `cascade_select` 兼容性验证
   - 现有 3 个对象 `key_template` 兼容性验证
   - 可选：为 relationship.yaml 添加 `group`/`level` 属性
   - 可选：为 business_object.yaml 添加 `sequence` 配置块

**风险缓解**:

| 风险 | 缓解措施 |
|------|---------|
| `cascade_select` 类型变更导致前端不兼容 | `CascadeSelectConfig.to_dict()` 输出与现有 dict 格式一致 |
| `_sequences` 表结构变更导致存量数据丢失 | `ALTER TABLE ADD COLUMN` 增量迁移，新列允许 NULL |
| 序列重置并发冲突 | 重置检查和递增操作在同一 `threading.Lock` 范围内 |
| `sequence` 配置与 `segments` 冲突 | `sequence` 优先，`segments` 作为回退 |

**测试策略**:

- **单元测试**:
  - `CascadeSelectConfig.from_dict()` / `to_dict()` 往返测试
  - `_expand_cascade_to_parameter_bindings()` 展开逻辑测试
  - `_validate_cascade_select()` 校验规则测试
  - `SequenceConfig.from_dict()` / `from_segments()` 测试
  - `SequenceEngine._should_reset()` 各策略测试
  - `SequenceEngine.build_periodic_sequence_name()` 周期序列名测试
  - `KeyTemplateEngine.generate_code()` 集成测试

- **集成测试**:
  - 现有 5 个对象 `cascade_select` 加载无报错
  - 现有 3 个对象 `key_template` 编码生成无变化
  - `parameter_bindings` 展开后前端 `useValueHelp` 正常过滤
  - 重置策略跨日/跨月/跨年场景验证

**回滚计划**:

- 移除 `CascadeSelectConfig`，恢复 `cascade_select` 为 `Optional[List[Dict[str, Any]]]`
- 移除 `SequenceConfig`，恢复 `KeyTemplateConfig` 原始字段
- 忽略 `_sequences.last_reset_at` 列

---

## 10. 待定事项

| ID | 事项 | 缺失信息 | 下一步 |
|----|------|----------|--------|
| TBD-301 | 旧周期序列记录清理策略 | 是否需要自动清理过期的周期序列记录？ | 确认后实现清理逻辑 |
| TBD-302 | cascade_select condition 语义 | `condition.operator` 的完整操作符列表 | 与前端确认支持范围 |
| TBD-303 | sequence.scope = "per_parent" 的精确语义 | "per_parent" 是否等同于引用第一个 `parent_field` segment？ | 实施时确认 |
| TBD-304 | 重置策略对 auto_detect 的影响 | 重置后 auto_detect 是否应从 1 开始而非扫描存量？ | 重置后从 start 开始，不扫描 |
| TBD-305 | 前端 cascade_select 新属性消费 | `group`/`level`/`condition` 是否需要前端支持？ | 与前端确认优先级 |

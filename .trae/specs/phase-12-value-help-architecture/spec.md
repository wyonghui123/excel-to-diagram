# Spec: Phase 12 - Value Help / Search Help 模型驱动架构

## 1. Background & Objectives

### 1.1 Background

当前系统中 Value Help（值帮助 / 搜索帮助）相关配置散布在多个位置，缺乏统一抽象：

- `ValueHelpConfig`（models.py:427）仅4个字段（validation, distinct, label, enabled_condition），无法描述数据源、搜索行为、展示列等
- `DimensionReference.search_help` 是 `Dict[str, Any]`，无类型约束
- `UIAnnotation.widget` 硬编码字符串（select / lookup / select_with_search），语义模糊
- `SemanticAnnotation.search_help_for` 仅表示"为谁提供搜索帮助"，不描述搜索帮助本身

前端组件同样碎片化：
- `EnumSearchHelp.vue` 硬编码 `/api/v1/enum-types/{type}/values`
- `ValueHelpSelector.vue` 仅用于条件规则，不与元数据模型集成
- `AssociationSelector.vue` 只处理 Association，不处理字段级 Value Help
- `DynamicForm.vue` 中 `search_help_for` 逻辑硬编码

行业对标：SAP `@Consumption.valueHelpDefinition` 提供了成熟的 Value Help 模型，支持 entity+element 数据源、additionalBinding 参数绑定、PresentationVariant 展示变体。Salesforce Lookup Field 支持 Search Layout 分场景配置和 Lookup Filter。Microsoft Dynamics 365 支持多态 Lookup 和 Custom Lookup Form。

### 1.2 Business Objectives

- 统一 Value Help 数据模型，消除配置碎片化
- **YAML 单一事实**：`value_help` 是 YAML 中 Value Help 的唯一配置入口，消除 `enum_reference` / `dimension_reference.search_help` / `UIAnnotation.value_help` 的重复定义
- 实现"一次配置，全场景覆盖"：枚举下拉、BO维度弹窗、层级树形选择、自定义查询
- **数据权限集成**：Value Help 查询 MUST 遵循现有 `DataPermissionInterceptor` + `ScopeFilter` 机制，确保用户只能看到有权限的数据
- 前端组件统一：一个 `ValueHelpField` 替代 EnumSearchHelp / ValueHelpSelector / AssociationSelector 的碎片化，与 `MetaForm` / `MetaTable` 组件库深度集成
- 向后兼容：旧 YAML 自动迁移，不破坏现有功能
- **分批适配**：先适配核心系统对象（user / role / user_group / enum / log），再适配架构管理对象，最后适配业务对象

### 1.3 User / Stakeholder Objectives

- **YAML 配置者**：通过统一的 `value_help` 块配置所有类型的值帮助，无需记忆多种配置方式
- **前端开发者**：使用 `ValueHelpField` 组件 + `useValueHelp` Composable，无需关心数据源差异
- **最终用户**：获得一致的搜索帮助交互体验（下拉 / 弹窗 / 树形），支持级联过滤、模糊搜索

## 2. Requirement Type Overview

| Type                    | Applicable | Evidence (Source)        |
| ----------------------- | ---------- | ------------------------ |
| Business                | Yes        | 统一模型消除碎片化       |
| User/Stakeholder        | Yes        | YAML配置者/前端开发者/最终用户 |
| Solution                | Yes        | 三层抽象模型设计          |
| Functional              | Yes        | FR-001 ~ FR-012          |
| Nonfunctional           | Yes        | NFR-001 ~ NFR-004        |
| External Interface      | Yes        | Value Help API           |
| Transition              | Yes        | 旧模型迁移/兼容层        |

## 3. Functional Requirements

### FR-001: 统一 Value Help 数据模型

- **Description**: 系统 MUST 提供统一的 `ValueHelpConfig` 数据模型，包含三层结构：Source（数据源）、Behavior（行为）、Presentation（展示），替代现有的 `ValueHelpConfig`（4字段）、`DimensionReference.search_help`（Dict）、`UIAnnotation.value_help`（旧版）。
- **Acceptance Criteria**:
  - `ValueHelpSource` 支持 enum / bo / custom 三种数据源类型
  - `ValueHelpBehavior` 支持 binding_strength / validation / search_fields / parameter_bindings / enabled_condition
  - `ValueHelpPresentation` 支持 result_type / display_mode / display_columns / sort_by / page_size / display_format / color_mapping
  - 新模型能完整表达现有 enum_reference 和 dimension_reference.search_help 的所有语义
- **Priority**: Must
- **Type Mapping**: Solution / Functional
- **Source**: 代码分析 + SAP @Consumption.valueHelpDefinition 对标

### FR-002: YAML Schema 支持 value_help 块（单一事实源）

- **Description**: 系统 MUST 在 YAML 元数据中支持字段级的 `value_help` 配置块，作为 Value Help 的**唯一配置入口**（单一事实源）。`enum_reference` / `dimension_reference.search_help` / `UIAnnotation.value_help` 标记为 deprecated，不再作为 Value Help 的配置来源。
- **Acceptance Criteria**:
  - 字段定义中可声明 `value_help` 块，包含 source / behavior / presentation 三层
  - `value_help.source.type = enum` 时，必须指定 `enum_type_id`
  - `value_help.source.type = bo` 时，必须指定 `target_bo` / `value_field` / `display_field`
  - `value_help.source.type = custom` 时，必须指定 `endpoint`
  - YAML Loader 能正确解析 `value_help` 块并生成 `ValueHelpConfig` 实例
  - **单一事实规则**：当字段同时存在 `value_help` 和 `enum_reference` / `dimension_reference` 时，`value_help` 优先，旧字段被忽略并输出 deprecation warning
  - YAML Schema 校验：`value_help` 与 `enum_reference` / `dimension_reference` 互斥，同时存在时报 warning
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 需求分析 + YAML 单一事实原则

### FR-003: Enum Source Provider（基于 enum_value BO 查询）

- **Description**: 系统 MUST 实现 Enum Value Help Provider，从枚举元数据提供值帮助数据。由于 enum_type / enum_value 本身是 BO 模型（有完整 YAML Schema），Enum Source Provider MUST 基于 enum_value BO 查询实现，而非独立的 enum API。
- **Acceptance Criteria**:
  - 支持 `enum_type_id` 指定枚举类型
  - 支持 `filter_by_dimension` 条件过滤（根据其他字段值动态过滤枚举选项）
  - 支持 `value_filter` 额外过滤条件（如 `is_active: true`）
  - 支持 `sort_by` 排序
  - 支持 `i18n_join_fields` 多语言 JOIN
  - 支持 `default_value_code` 默认值
  - **Enum 是 BO 模型**：Enum Source Provider 内部通过 `BoValueHelpProvider` 实现，预配置 `target_bo = enum_value`，自动注入 `enum_type_id` 过滤条件
  - **不走独立 enum API**：废弃 `/api/v1/enum-types/{type}/values`，统一走 Value Help API
  - **维度过滤**：`filter_by_dimension` 映射为 enum_value 的 dimensions 字段查询
  - **枚举模型决定 Value Help 行为**：enum_type.yaml 中的 `dimension_schema`、`mutability`、`i18n` 配置自动影响 Value Help 的搜索和展示行为
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 现有 enum_reference 功能迁移 + enum_value 是 BO 模型的事实

### FR-004: BO Source Provider（含数据权限）

- **Description**: 系统 MUST 实现 BO Value Help Provider，从业务对象数据提供值帮助数据，且 MUST 遵循现有数据权限机制。
- **Acceptance Criteria**:
  - 支持 `target_bo` 指定目标 BO
  - 支持 `value_field` / `display_field` / `code_field` 字段映射
  - 支持 `hierarchy` 层级配置（parent_field / path_field / expand_level）
  - 支持 `parameter_bindings` 级联过滤（依赖其他字段值动态过滤）
  - 支持分页查询（page / page_size）
  - 支持模糊搜索（search / search_fields）
  - 支持排序（sort_by）
  - **数据权限**：`apply_target_permissions = true` 时，Provider MUST 通过 `DataPermissionInterceptor` 注入权限过滤条件，非管理员只能看到有权限的目标 BO 记录
  - **Scope 过滤**：Provider MUST 通过 `ScopeFilter` 注入 scope 过滤条件（如 `$user` 变量替换）
  - `apply_target_permissions` 字段从 `DimensionReference` 迁移到 `ValueHelpSource`
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 现有 dimension_reference.search_help 功能迁移 + SAP additionalBinding 对标 + 数据权限需求

### FR-005: Custom Source Provider

- **Description**: 系统 MUST 实现 Custom Value Help Provider，从自定义 API 端点提供值帮助数据。
- **Acceptance Criteria**:
  - 支持 `endpoint` 指定自定义 API 路径
  - 支持 `params` 传递参数
  - 返回数据格式与统一 Value Help API 响应格式一致
- **Priority**: Should
- **Type Mapping**: Functional
- **Source**: 扩展性需求

### FR-006: Parameter Binding 级联过滤

- **Description**: 系统 MUST 支持 Value Help 的参数绑定机制，实现字段间的级联过滤。
- **Acceptance Criteria**:
  - `parameter_bindings` 中每个绑定指定 `local_field` / `target_field` / `required` / `constant`
  - 当 `local_field` 的值变化时，自动重新加载 Value Help 选项
  - `required: true` 的绑定，当本地字段无值时，Value Help 不加载选项
  - `constant` 支持常量绑定（不依赖字段值）
  - 支持多个 parameter_bindings 组合过滤（AND 逻辑）
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: SAP @Consumption.valueHelpDefinition.additionalBinding 对标

### FR-006a: 多值 Value Help（多选）

- **Description**: 系统 MUST 支持多值 Value Help，允许用户一次选择多个值。
- **Acceptance Criteria**:
  - `ValueHelpBehavior` 新增 `multiple: bool = False` 字段
  - `multiple = True` 时，`ValueHelpField` 渲染为多选下拉 / 多选弹窗
  - v-model 绑定值为数组（`[value1, value2, ...]`）
  - `displayValue` 为多个 display 的拼接（如 "选项A, 选项B"）
  - 多选弹窗支持全选 / 反选 / 清空操作
  - 多选下拉支持 tag 展示已选项
  - 过滤场景（FilterBar / DynamicFilters）天然支持多选
  - 表单场景（MetaForm）根据 `multiple` 字段自动切换单选/多选
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 用户需求确认

### FR-007: 统一 Value Help API

- **Description**: 系统 MUST 提供统一的 Value Help API 端点，根据 source type 自动路由到对应的 Provider。
- **Acceptance Criteria**:
  - API 路径: `GET /api/v2/value-help/{source_type}/{source_id}`
  - 支持 `search` / `search_fields` / `page` / `pageSize` / `sort` / `filters` 查询参数
  - 响应格式统一: `{ data: [{ value, display, code, extra }], total, has_more }`
  - source_type = enum 时，source_id 为 enum_type_id
  - source_type = bo 时，source_id 为 target_bo
  - source_type = custom 时，source_id 为 endpoint 标识
  - filters 参数用于传递 parameter_bindings 的值
- **Priority**: Must
- **Type Mapping**: Functional / External Interface
- **Source**: 需求分析

### FR-008: 前端 useValueHelp Composable

- **Description**: 系统 MUST 提供 `useValueHelp` Vue Composable，封装 Value Help 的数据加载、搜索、展示名解析、输入验证逻辑。
- **Acceptance Criteria**:
  - 接收 `valueHelpConfig` 参数，自动识别 source type
  - 提供 `loadOptions(search, params)` 方法，调用统一 Value Help API
  - 提供 `resolveDisplay(value)` 方法，根据 value 获取 display name
  - 提供 `validateInput(value)` 方法，根据 binding_strength 验证输入
  - 支持 `debounce` 防抖搜索
  - 支持 `minSearchLength` 最小搜索长度
  - 返回 `options` / `loading` / `error` 响应式状态
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 需求分析

### FR-009: 前端 ValueHelpField 统一组件（与 MetaForm/MetaTable 组件库集成）

- **Description**: 系统 MUST 提供 `ValueHelpField` Vue 组件，根据 `value_help.presentation.result_type` 自动选择 UI 形态，且 MUST 与现有组件库全场景深度集成。
- **Acceptance Criteria**:
  - `result_type = dropdown` 时，渲染为 ElSelect + 远程搜索
  - `result_type = dialog` 时，渲染为输入框 + 搜索帮助弹窗
  - `result_type = inline` 时，渲染为内联自动完成
  - `display_mode = tree` 时，弹窗中渲染树形结构
  - 支持 `display_columns` 配置弹窗中的列布局
  - 支持 `display_format` 配置选中后的显示格式
  - 支持 `color_mapping` 配置条件颜色
  - 支持 `parameter_bindings` 级联过滤（监听本地字段变化，重新加载选项）
  - 支持 v-model 双向绑定（value + displayValue）
  - **MetaForm 集成**：`MetaForm` 自动识别字段的 `value_help` 配置，渲染 `ValueHelpField` 替代硬编码的 select/lookup
  - **MetaTable 集成**：`MetaTable` 列渲染时，`value_help` 字段自动显示 displayValue 而非 raw value
  - **MetaDialog 集成**：随 MetaForm 自动适配
  - **MetaListPage 集成**：随子组件自动适配
  - **FilterBar 集成**：`FilterBar` 中 `field.type === 'value_help'` 的过滤字段渲染为 `ValueHelpField`（dropdown 模式），替代当前 `foreign_key` 类型的纯文本输入
  - **TableHeaderFilter 集成**：`TableHeaderFilter` 中 `filterType === 'value_help'` 的列头过滤渲染为 `ValueHelpField`
  - **DynamicFilters 集成**：`DynamicFilters` 中 `field.type === 'foreign_key'` 的过滤字段改用 `ValueHelpField`，替代当前的 `AppInput`
  - **InlineEditCell 集成**：`InlineEditCell` 中 `fieldConfig.type === 'value_help'` 的内联编辑渲染为 `ValueHelpField`（dropdown 模式），替代当前的静态 `ElSelect`
  - **AssociationSelector 统一**：`widget: association_selector` 场景通过 `value_help.source.type = bo` + `presentation.result_type = dialog` 统一处理
  - **Association 与 Value Help 协作**（SAP 模式）：Association 定义关系语义（谁和谁关联、基数、生命周期），Value Help 定义字段级选择行为（如何选择、搜索、展示、验证）。当字段有 Association 时，Value Help 的 source 自动从 Association 推导（`source.type = bo`, `source.target_bo = association.target_bo`）
  - 组件注册到 `src/components/common/index.js`，全局可用
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 需求分析 + 组件库集成需求

### FR-010: 旧模型自动迁移

- **Description**: 系统 MUST 在 YAML Loader 中实现旧模型到新 Value Help 模型的自动迁移。
- **Acceptance Criteria**:
  - `enum_reference` 自动转换为 `value_help.source.type = enum`
  - `dimension_reference.search_help` 自动转换为 `value_help.source.type = bo` + behavior/presentation
  - `UIAnnotation.value_help`（旧版4字段）自动合并到新 `ValueHelpConfig.behavior`
  - `UIAnnotation.widget = select` 自动映射为 `result_type = dropdown`
  - `UIAnnotation.widget = lookup` 自动映射为 `result_type = dialog`
  - `UIAnnotation.widget = select_with_search` 自动映射为 `result_type = dropdown` + search
  - 迁移过程无数据丢失，日志记录迁移详情
- **Priority**: Must
- **Type Mapping**: Transition
- **Source**: 代码分析

### FR-011: DynamicForm 集成 ValueHelpField

- **Description**: 系统 MUST 在 DynamicForm 中集成 ValueHelpField 组件，替代现有的硬编码 search_help_for 逻辑。
- **Acceptance Criteria**:
  - DynamicForm 读取字段的 `value_help` 配置
  - 根据 `value_help.presentation.result_type` 渲染对应的 ValueHelpField
  - 级联过滤自动生效（parameter_bindings）
  - search_help_for 语义通过 parameter_bindings 实现
  - immutable 字段的 Value Help 在编辑模式下只读
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: 代码分析（DynamicForm.vue:473-491）

### FR-012: Value Help 元数据 API

- **Description**: 系统 MUST 在 BO 元数据 API 中返回字段的 `value_help` 配置，供前端动态渲染。
- **Acceptance Criteria**:
  - `GET /api/v2/bo/{entity}/$metadata` 响应中包含字段的 `value_help` 配置
  - `value_help` 配置包含完整的 source / behavior / presentation
  - parameter_bindings 中的 local_field 引用同 BO 的其他字段
  - 前端可根据 `value_help` 配置自动渲染 ValueHelpField
- **Priority**: Must
- **Type Mapping**: Functional / External Interface
- **Source**: 需求分析

### FR-013: Value Help 数据权限集成

- **Description**: 系统 MUST 在 Value Help 查询中集成现有的 `DataPermissionInterceptor` + `ScopeFilter` 机制，确保用户只能看到有权限的数据。
- **Acceptance Criteria**:
  - `BoValueHelpProvider.search()` MUST 在查询前注入 `DataPermissionInterceptor` 的权限过滤条件
  - `BoValueHelpProvider.search()` MUST 在查询前注入 `ScopeFilter` 的 scope 过滤条件
  - `apply_target_permissions = true`（默认）时，非管理员只能看到有权限的目标 BO 记录
  - `apply_target_permissions = false` 时，跳过数据权限过滤（适用于公开数据如枚举）
  - Value Help API MUST 传递当前用户上下文（user_id / roles / is_admin）
  - `EnumValueHelpProvider` 默认不应用数据权限（枚举是公共配置数据）
- **Priority**: Must
- **Type Mapping**: Functional / Security
- **Source**: 代码分析（DataPermissionInterceptor, ScopeFilter）

### FR-014: 分批适配 BO 对象

- **Description**: 系统 MUST 按优先级分批将现有 BO 的 YAML 迁移到 `value_help` 配置，先适配核心系统对象，再适配架构管理对象，最后适配业务对象。
- **Acceptance Criteria**:
  - **第一批（核心系统对象）**：user / role / user_group / enum_type / enum_value / log
    - user: `status` (enum), `groups` (association→bo), `roles` (association→bo)
    - role: `permissions` (association→bo), `users` (association→bo)
    - user_group: `parent_id` (bo+hierarchy), `manager_id` (bo)
    - enum_type: `category` (enum)
    - enum_value: `enum_type_id` (bo), `is_active` (enum)
  - **第二批（架构管理对象）**：domain / sub_domain / service_module / business_object / version / product
    - 这些对象大量使用 `widget: select` 引用层级对象
  - **第三批（业务对象）**：relationship / annotation / filter_variant / 其他
  - 每批迁移完成后，对应的旧字段（enum_reference / dimension_reference / widget:select）从 YAML 中移除
  - 迁移过程有回归测试保障
- **Priority**: Must
- **Type Mapping**: Transition
- **Source**: 风险控制 + 渐进式迁移策略

### FR-015: Value Help 与 Validation Rule 的协作

- **Description**: 系统 MUST 明确 Value Help 验证与现有 Validation Rule 的关系，两者是互补而非替代。
- **Acceptance Criteria**:
  - **前置预防性验证**（Value Help 层）：`behavior.validation = true` 时，Value Help 限制用户只能从选项列表中选择，等同于 SAP `useForValidation: true` 和 Salesforce Lookup Filter，是**预防性**的（在输入时限制可选项）
  - **后置纠正性验证**（Validation Rule 层）：现有 `MetaValidation` / `MetaConstraint` 规则在 `BEFORE_SAVE` 时执行，是**纠正性**的（保存时检查合法性）
  - **两者协作规则**：
    - `behavior.validation = true` + `behavior.binding_strength = strict`：前置验证，用户只能选择 VH 列表中的值，后置 Validation Rule 可省略
    - `behavior.validation = true` + `behavior.binding_strength = loose`：前置建议（用户可自由输入），后置 Validation Rule 检查输入是否合法
    - `behavior.validation = false`：无前置验证，完全依赖后置 Validation Rule
  - **Value Help 验证不等同于 Validation Rule**：VH 验证只检查"值是否在选项列表中"，Validation Rule 可以检查更复杂的业务逻辑（如跨字段校验、条件校验）
  - **Value Help 自动生成 Validation Rule**：当 `behavior.validation = true` 且 `behavior.binding_strength = strict` 时，系统可自动生成一条 `MetaValidation` 规则（`rule: value IN value_help_options`），作为双重保障
- **Priority**: Must
- **Type Mapping**: Functional
- **Source**: SAP useForValidation + Salesforce Lookup Filter vs Validation Rule 对比分析

## 4. Nonfunctional Requirements

### NFR-001: 搜索性能

- **Description**: Value Help API 搜索响应时间 MUST < 500ms（1000条以内数据），< 2s（10000条以内数据）。
- **Measurement**: API 响应时间监控，P95 延迟
- **Priority**: Must
- **Source**: 用户体验要求

### NFR-002: 向后兼容性

- **Description**: 新模型 MUST 100% 向后兼容旧 YAML 配置，不破坏现有功能。
- **Measurement**: 所有现有 E2E 测试通过，无回归
- **Priority**: Must
- **Source**: 系统稳定性要求

### NFR-003: 前端组件可测试性

- **Description**: ValueHelpField 组件 MUST 支持单元测试，可 mock Value Help API。
- **Measurement**: 组件测试覆盖率 > 80%
- **Priority**: Should
- **Source**: 质量要求

### NFR-004: API 可扩展性

- **Description**: Value Help API 设计 MUST 支持未来扩展新的 source type，无需修改 API 路由结构。
- **Measurement**: 新增 source type 只需实现 Provider 接口，无需修改 API 层
- **Priority**: Should
- **Source**: 架构可持续性

## 5. External Interface Requirements

### IF-001: Value Help 搜索 API

- **Type**: API
- **Endpoint**: `GET /api/v2/value-help/{source_type}/{source_id}`
- **Request**:
  - `search` (string, optional): 搜索关键词
  - `search_fields` (string, optional): 搜索字段列表，逗号分隔
  - `page` (int, optional): 页码，默认1
  - `pageSize` (int, optional): 每页条数，默认50
  - `sort` (string, optional): 排序，格式 `field:direction`，逗号分隔
  - `filters` (object, optional): 过滤条件，key=value 格式，用于 parameter_bindings
- **Response**:
  ```json
  {
    "success": true,
    "data": {
      "data": [
        {
          "value": 123,
          "display": "C001 - 张三公司",
          "code": "C001",
          "extra": {"region": "华东", "level": "VIP"}
        }
      ],
      "total": 156,
      "has_more": true
    }
  }
  ```
- **Error Handling**:
  - 400: source_type 不支持 / source_id 缺失
  - 404: source_id 对应的资源不存在
  - 500: Provider 内部错误
- **Source**: 需求分析

### IF-002: Value Help 显示名解析 API

- **Type**: API
- **Endpoint**: `GET /api/v2/value-help/{source_type}/{source_id}/resolve`
- **Request**:
  - `value` (string, required): 要解析的值
- **Response**:
  ```json
  {
    "success": true,
    "data": {
      "value": 123,
      "display": "C001 - 张三公司",
      "code": "C001"
    }
  }
  ```
- **Error Handling**:
  - 404: 值对应的记录不存在
- **Source**: 需求分析

### IF-003: Value Help 元数据 API（扩展）

- **Type**: API
- **Endpoint**: `GET /api/v2/bo/{entity}/$metadata`（扩展现有端点）
- **Request**: 无额外参数
- **Response**: 字段定义中增加 `value_help` 配置块
  ```json
  {
    "fields": [{
      "id": "customer_id",
      "name": "客户",
      "value_help": {
        "source": { "type": "bo", "target_bo": "customer", ... },
        "behavior": { "binding_strength": "strict", ... },
        "presentation": { "result_type": "dialog", ... }
      }
    }]
  }
  ```
- **Source**: 需求分析

## 6. Transition Requirements

### TR-001: 旧 YAML 模型迁移

- **Description**: 现有 YAML 中使用 `enum_reference` / `dimension_reference.search_help` / `UIAnnotation.value_help` 的字段，需自动迁移到新的 `value_help` 块。
- **Strategy**: YAML Loader 中实现 `migrate_to_unified_value_help()` 函数，加载时自动转换。旧 YAML 语法继续支持（兼容层），新 YAML 推荐使用 `value_help` 块。
- **Rollback Plan**: 旧模型字段保留，迁移函数可禁用。前端同时支持新旧两种配置。
- **Source**: 代码分析

### TR-002: 前端组件迁移

- **Description**: 现有 EnumSearchHelp / ValueHelpSelector / AssociationSelector（字段级场景）逐步迁移到 ValueHelpField。
- **Strategy**: 新组件 ValueHelpField 与旧组件并存，DynamicForm 优先使用新组件。旧组件标记为 deprecated 但不删除。
- **Rollback Plan**: DynamicForm 可通过 feature flag 切回旧组件。
- **Source**: 需求分析

### TR-003: 旧 API 兼容

- **Description**: 现有 `/api/v1/enum-types/{type}/values` API 继续可用，不删除。
- **Strategy**: 新 Value Help API 是 v2，旧 API 保持不变。前端新组件使用 v2 API。
- **Rollback Plan**: 无需回滚，旧 API 不受影响。
- **Source**: 系统稳定性要求

## 7. Constraints & Assumptions

### 7.1 Technical Constraints

- 后端使用 Python + Flask，模型使用 dataclass
- 前端使用 Vue 3 + Element Plus + YonDesign
- YAML 元数据通过 yaml_loader.py 解析
- 现有 BO Framework v2 API 路由结构不可破坏

### 7.2 Business Constraints

- 必须向后兼容，现有 YAML 配置不能 break
- 前端组件迁移不能影响现有页面功能
- 新 API 遵循现有 v2 API 规范（响应格式、错误处理）

### 7.3 Assumptions

- Value Help 数据量通常在 10000 条以内，超过此范围需要分页 – Source: Assumed
- 枚举类型数据量通常在 500 条以内，不需要分页 – Source: Assumed
- 层级数据深度通常不超过 5 层 – Source: Assumed
- 前端搜索防抖 300ms 是合理默认值 – Source: SAP/D365 实践

## 8. Priorities & Milestone Suggestions

| ID      | Requirement                          | Priority | Reason                     |
| ------- | ------------------------------------ | -------- | -------------------------- |
| FR-001  | 统一 Value Help 数据模型              | Must     | 核心基础，其他功能依赖      |
| FR-002  | YAML Schema 支持 value_help 块       | Must     | 配置入口，依赖 FR-001       |
| FR-003  | Enum Source Provider                 | Must     | 替代现有 enum_reference     |
| FR-004  | BO Source Provider                   | Must     | 替代现有 dimension_reference |
| FR-005  | Custom Source Provider               | Should   | 扩展性，可后续迭代          |
| FR-006  | Parameter Binding 级联过滤           | Must     | 核心交互需求               |
| FR-006a | 多值 Value Help（多选）             | Must     | 用户需求确认               |
| FR-007  | 统一 Value Help API                  | Must     | 前后端桥梁                 |
| FR-008  | 前端 useValueHelp Composable         | Must     | 前端核心逻辑               |
| FR-009  | 前端 ValueHelpField 统一组件         | Must     | 前端统一入口               |
| FR-010  | 旧模型自动迁移                       | Must     | 兼容性保障                 |
| FR-011  | DynamicForm 集成 ValueHelpField      | Must     | 端到端验证                 |
| FR-012  | Value Help 元数据 API                | Must     | 前端动态渲染依赖           |
| FR-013  | Value Help 数据权限集成               | Must     | 安全性，防止越权访问       |
| FR-014  | 分批适配 BO 对象                      | Must     | 风险控制，渐进式迁移       |
| FR-015  | Value Help 与 Validation Rule 协作    | Must     | 前置预防 + 后置纠正互补    |

**Suggested Milestones**:

- **Milestone 12.1 (Week 1)**: 统一数据模型 + YAML Schema + 旧模型迁移 + 数据权限
  - FR-001, FR-002, FR-010, FR-013
  - 交付: ValueHelpSource / ValueHelpBehavior / ValueHelpPresentation 数据模型, YAML 解析, 迁移函数, 数据权限集成

- **Milestone 12.2 (Week 1-2)**: 后端 Provider + API
  - FR-003, FR-004, FR-005, FR-006, FR-007, FR-012
  - 交付: EnumValueHelpProvider, BoValueHelpProvider, CustomValueHelpProvider, Value Help API

- **Milestone 12.3 (Week 2-3)**: 前端 Composable + 组件 + 组件库全场景适配
  - FR-008, FR-009
  - 交付: useValueHelp.js, ValueHelpField.vue, SearchHelpDialog.vue
  - 交付: MetaForm / MetaTable / MetaDialog 集成（P0）
  - 交付: FilterBar / DynamicFilters 集成（P1）
  - 交付: InlineEditCell / TableHeaderFilter 集成（P2）

- **Milestone 12.4 (Week 3)**: 第一批核心对象适配 + DynamicForm 集成
  - FR-011, FR-014 (第一批)
  - 交付: user / role / user_group / enum_type / enum_value / log 的 YAML 迁移到 value_help, DynamicForm 集成, E2E 测试

- **Milestone 12.5 (Week 4)**: 第二批架构管理对象适配
  - FR-014 (第二批)
  - 交付: domain / sub_domain / service_module / business_object / version / product 的 YAML 迁移

- **Milestone 12.6 (Week 5)**: 第三批业务对象适配 + 旧字段清理
  - FR-014 (第三批)
  - 交付: relationship / annotation / filter_variant / 其他对象的 YAML 迁移, 旧字段（enum_reference / dimension_reference / widget:select）从 YAML 中移除, 全量回归测试

## 9. Change / Design Proposal (RFC)

### 9.1 As-Is Analysis

- **Current Architecture**: Value Help 配置散布在3处：
  1. `ValueHelpConfig`（4字段，挂在 UIAnnotation 上）
  2. `DimensionReference.search_help`（Dict，嵌套在 dimension_reference 内）
  3. `UIAnnotation.widget`（字符串，隐式决定 UI 形态）

- **Current Issues**:
  1. 模型碎片化：同一概念在3处定义，语义重叠
  2. 无统一数据源抽象：枚举、维度、自定义查询没有统一的 Provider 模型
  3. 前端组件不通用：EnumSearchHelp / ValueHelpSelector / AssociationSelector 各自为政
  4. 缺少搜索行为配置：无法声明搜索字段、展示列、排序策略
  5. 缺少参数化过滤：不支持依赖其他字段值的动态过滤
  6. 缺少展示变体：无法定义弹窗中的列布局、排序、分组

- **Relevant Code Paths**:
  - `meta/core/models.py` - ValueHelpConfig (L427), DimensionReference (L257), UIAnnotation (L457)
  - `meta/core/yaml_loader.py` - parse_value_help (L387), parse_ui_annotation (L402)
  - `src/components/common/EnumSearchHelp.vue` - 枚举搜索帮助
  - `src/components/common/ConditionRuleEditor/ValueHelpSelector.vue` - 条件规则值选择器
  - `src/components/bo/AssociationSelector.vue` - 关联对象选择器
  - `src/views/ArchDataManageApp/components/DynamicForm.vue` - 动态表单 (L473-491)

### 9.2 Target State

- **Proposed Architecture**: 三层抽象模型 + Provider 模式 + 统一 API + 统一前端组件

```
┌─────────────────────────────────────────────────────┐
│              Value Help 统一架构                      │
├─────────────────────────────────────────────────────┤
│                                                       │
│  YAML Layer: value_help 块（统一配置入口）             │
│  ┌───────────────────────────────────────────────┐   │
│  │ source: { type, enum_type_id / target_bo / endpoint } │
│  │ behavior: { binding_strength, search_fields, parameter_bindings } │
│  │ presentation: { result_type, display_columns, sort_by } │
│  └───────────────────────────────────────────────┘   │
│                                                       │
│  Backend Layer: Provider 模式                         │
│  ┌─────────────┐ ┌──────────────┐ ┌────────────┐   │
│  │ EnumVH      │ │ BoVH         │ │ CustomVH   │   │
│  │ Provider    │ │ Provider     │ │ Provider   │   │
│  └──────┬──────┘ └──────┬───────┘ └──────┬─────┘   │
│         └───────────────┼────────────────┘          │
│                         ▼                            │
│              Value Help API (统一)                    │
│              GET /api/v2/value-help/{type}/{id}      │
│                                                       │
│  Frontend Layer: 统一组件                              │
│  ┌───────────────────────────────────────────────┐   │
│  │ useValueHelp (Composable)                     │   │
│  │   ├── loadOptions(search, params)             │   │
│  │   ├── resolveDisplay(value)                   │   │
│  │   └── validateInput(value)                    │   │
│  ├───────────────────────────────────────────────┤   │
│  │ ValueHelpField (统一组件)                      │   │
│  │   ├── dropdown → ElSelect + 远程搜索           │   │
│  │   ├── dialog → SearchHelpDialog               │   │
│  │   └── inline → InlineAutocomplete             │   │
│  └───────────────────────────────────────────────┘   │
│                                                       │
└─────────────────────────────────────────────────────┘
```

- **Key Changes**:
  1. 新增 `ValueHelpSource` / `ValueHelpBehavior` / `ValueHelpPresentation` 三个 dataclass
  2. 重构 `ValueHelpConfig` 为三层组合结构
  3. 新增 `ValueHelpProvider` 基类 + 三个实现
  4. 新增 Value Help API 路由
  5. 新增 `useValueHelp` Composable
  6. 新增 `ValueHelpField` 组件
  7. YAML Loader 新增 `value_help` 解析 + 旧模型迁移

### 9.3 Detailed Design

#### 9.3.1 数据模型设计

```python
@dataclass
class ValueHelpParameterBinding:
    local_field: str = ""
    target_field: str = ""
    required: bool = False
    constant: str = ""

@dataclass
class ValueHelpSource:
    type: str = "enum"
    # Enum Source
    enum_type_id: str = ""
    filter_by_dimension: Dict[str, Any] = field(default_factory=dict)
    value_filter: Dict[str, Any] = field(default_factory=dict)
    sort_by: str = ""
    i18n_join_fields: List[str] = field(default_factory=list)
    default_value_code: str = ""
    # BO Source
    target_bo: str = ""
    value_field: str = "id"
    display_field: str = "name"
    code_field: str = "code"
    hierarchy: Dict[str, Any] = field(default_factory=dict)
    apply_target_permissions: bool = True    # 数据权限：是否应用目标BO的数据权限过滤
    # Custom Source
    endpoint: str = ""
    params: Dict[str, Any] = field(default_factory=dict)

@dataclass
class ValueHelpBehavior:
    binding_strength: str = "strict"
    validation: bool = True
    search_fields: List[str] = field(default_factory=list)
    min_search_length: int = 0
    debounce_ms: int = 300
    multiple: bool = False                    # 多值选择：允许一次选择多个值
    parameter_bindings: List[ValueHelpParameterBinding] = field(default_factory=list)
    enabled_condition: str = ""

@dataclass
class ValueHelpDisplayColumn:
    field: str = ""
    label: str = ""
    width: int = 0
    sortable: bool = True

@dataclass
class ValueHelpPresentation:
    result_type: str = "dropdown"
    display_mode: str = "flat"
    display_columns: List[ValueHelpDisplayColumn] = field(default_factory=list)
    sort_by: List[Dict[str, str]] = field(default_factory=list)
    page_size: int = 50
    display_format: str = ""
    color_mapping: Dict[str, str] = field(default_factory=dict)

@dataclass
class ValueHelpConfig:
    source: ValueHelpSource = field(default_factory=ValueHelpSource)
    behavior: ValueHelpBehavior = field(default_factory=ValueHelpBehavior)
    presentation: ValueHelpPresentation = field(default_factory=ValueHelpPresentation)
```

#### 9.3.2 Provider 模式设计

```python
class ValueHelpProvider(ABC):
    @abstractmethod
    def search(self, query: str, search_fields: List[str],
               filters: Dict[str, Any], page: int, page_size: int,
               sort: List[Dict[str, str]]) -> Dict[str, Any]:
        pass

    @abstractmethod
    def resolve(self, value: Any) -> Optional[Dict[str, Any]]:
        pass

class EnumValueHelpProvider(ValueHelpProvider):
    """枚举 Value Help Provider
    
    设计决策：enum_type / enum_value 是 BO 模型，因此 EnumValueHelpProvider 
    内部通过 BoValueHelpProvider 实现，预配置 target_bo=enum_value。
    这意味着：
    1. 枚举查询走 v2 BO API，不走独立的 /api/v1/enum-types/{type}/values
    2. 枚举模型（dimension_schema, mutability, i18n）自动决定 Value Help 行为
    3. 未来如果 enum 迁移到标准 BO Association，Value Help 无需改动
    """
    def __init__(self, source: ValueHelpSource):
        self.enum_type_id = source.enum_type_id
        self.filter_by_dimension = source.filter_by_dimension
        self.value_filter = source.value_filter
        self.sort_by = source.sort_by
        # 内部委托给 BoValueHelpProvider
        self._bo_provider = BoValueHelpProvider(ValueHelpSource(
            type="bo",
            target_bo="enum_value",
            value_field="code",
            display_field="name",
            code_field="code",
            apply_target_permissions=False,  # 枚举是公共配置数据
        ))

    def search(self, query, search_fields, filters, page, page_size, sort, user_context=None):
        # 注入 enum_type_id 过滤条件
        filters = {**filters, "enum_type_id": self.enum_type_id}
        # 注入 dimension 过滤条件
        if self.filter_by_dimension:
            for dim_field, dim_values in self.filter_by_dimension.get("mapping", {}).items():
                if dim_field in filters:
                    filters["dimensions__" + dim_field] = filters[dim_field]
        # 注入 value_filter
        if self.value_filter:
            filters.update(self.value_filter)
        return self._bo_provider.search(query, search_fields, filters, page, page_size, sort, user_context)

    def resolve(self, value, user_context=None):
        return self._bo_provider.resolve(value, user_context)

class BoValueHelpProvider(ValueHelpProvider):
    def __init__(self, source: ValueHelpSource):
        self.target_bo = source.target_bo
        self.value_field = source.value_field
        self.display_field = source.display_field
        self.code_field = source.code_field
        self.hierarchy = source.hierarchy
        self.apply_target_permissions = source.apply_target_permissions

    def search(self, query, search_fields, filters, page, page_size, sort, user_context=None):
        # 1. 构建基础查询
        # 2. 如果 apply_target_permissions 且 user_context 非 admin:
        #    注入 DataPermissionInterceptor 的权限过滤条件
        #    注入 ScopeFilter 的 scope 过滤条件
        # 3. 应用 filters (parameter_bindings) + search + pagination
        pass

    def resolve(self, value, user_context=None):
        # 根据 value 查询目标 BO 的 display name
        # 同样需要检查数据权限
        pass

class CustomValueHelpProvider(ValueHelpProvider):
    def __init__(self, source: ValueHelpSource):
        self.endpoint = source.endpoint
        self.params = source.params

    def search(self, query, search_fields, filters, page, page_size, sort):
        # 调用自定义 API 端点
        pass

    def resolve(self, value):
        # 调用自定义 API 端点解析
        pass
```

#### 9.3.3 API 路由设计

```python
# meta/api/value_help_api.py

@value_help_bp.route("/api/v2/value-help/<source_type>/<source_id>", methods=["GET"])
def search_value_help(source_type, source_id):
    source = ValueHelpSource(type=source_type)
    if source_type == "enum":
        source.enum_type_id = source_id
    elif source_type == "bo":
        source.target_bo = source_id
    elif source_type == "custom":
        source.endpoint = source_id

    provider = get_provider(source)
    result = provider.search(
        query=request.args.get("search", ""),
        search_fields=request.args.get("search_fields", "").split(","),
        filters=request.args.get("filters", {}),
        page=int(request.args.get("page", 1)),
        page_size=int(request.args.get("pageSize", 50)),
        sort=parse_sort(request.args.get("sort", ""))
    )
    return jsonify({"success": True, "data": result})

@value_help_bp.route("/api/v2/value-help/<source_type>/<source_id>/resolve", methods=["GET"])
def resolve_value_help(source_type, source_id):
    value = request.args.get("value")
    source = ValueHelpSource(type=source_type, ...)
    provider = get_provider(source)
    result = provider.resolve(value)
    return jsonify({"success": True, "data": result})
```

#### 9.3.4 前端 Composable 设计

```javascript
// src/composables/useValueHelp.js

export function useValueHelp(valueHelpConfig, options = {}) {
  const options = ref([])
  const loading = ref(false)
  const error = ref(null)
  const displayValue = ref('')

  const { source, behavior, presentation } = valueHelpConfig

  async function loadOptions(search = '', params = {}) {
    if (behavior.min_search_length > 0 && search.length < behavior.min_search_length) {
      return
    }
    loading.value = true
    error.value = null
    try {
      const response = await boService.searchValueHelp(
        source.type,
        source.type === 'enum' ? source.enum_type_id :
          source.type === 'bo' ? source.target_bo : source.endpoint,
        { search, search_fields: behavior.search_fields.join(','), ...params }
      )
      options.value = response.data.data
    } catch (e) {
      error.value = e.message
    } finally {
      loading.value = false
    }
  }

  async function resolveDisplay(value) {
    if (!value) { displayValue.value = ''; return }
    try {
      const response = await boService.resolveValueHelp(
        source.type,
        source.type === 'enum' ? source.enum_type_id :
          source.type === 'bo' ? source.target_bo : source.endpoint,
        value
      )
      displayValue.value = response.data.display
    } catch (e) {
      displayValue.value = String(value)
    }
  }

  function validateInput(value) {
    if (!behavior.validation) return true
    if (behavior.binding_strength === 'loose') return true
    return options.value.some(opt => String(opt.value) === String(value))
  }

  return {
    options, loading, error, displayValue,
    loadOptions, resolveDisplay, validateInput
  }
}
```

#### 9.3.5 前端组件设计

```
ValueHelpField.vue
├── Props: modelValue, displayValue, valueHelpConfig, disabled, placeholder
├── Emits: update:modelValue, update:displayValue, change
├── 内部根据 presentation.result_type 选择渲染:
│   ├── "dropdown" → ElSelect + remote-search
│   │   ├── 支持 filterable + remote + remote-method
│   │   ├── 支持 multiple (behavior.multiple === true)
│   │   │   ├── 多选时 v-model 绑定数组 [value1, value2, ...]
│   │   │   ├── 多选时展示 tag 标签
│   │   │   └── 多选时 collapse-tags 超过3个折叠显示
│   │   └── 单选时 v-model 绑定单值
│   ├── "dialog" → ElInput + SearchHelpDialog
│   │   ├── 输入框显示 displayValue
│   │   ├── 点击搜索图标打开弹窗
│   │   └── SearchHelpDialog:
│   │       ├── 搜索框 (debounce)
│   │       ├── 结果表格 (display_columns 配置列)
│   │       ├── 分页 (page_size)
│   │       ├── 树形模式 (display_mode === 'tree')
│   │       └── 多选模式 (behavior.multiple === true)
│   │           ├── 表格支持 checkbox 多选
│   │           ├── 全选 / 反选 / 清空按钮
│   │           └── 已选区域展示已选项 tag
│   └── "inline" → ElAutocomplete
│       ├── suggestions 从 loadOptions 获取
│       └── trigger-on-focus 根据 min_search_length 决定
└── Parameter Bindings:
    ├── 监听 local_field 对应的表单值变化
    ├── 变化时清空当前选项，重新 loadOptions
    └── required binding 无值时禁用组件
```

**组件库全场景适配映射**:

| 现有组件 | 现有处理方式 | Value Help 适配方式 |
|----------|-------------|-------------------|
| `MetaForm.vue` | `field.type === 'select'` → `AppSelect`（静态 options） | 新增 `field.value_help` 判断 → 渲染 `ValueHelpField` |
| `MetaTable.vue` | 列渲染只显示 raw value | `value_help` 字段 → 调用 `resolveDisplay()` 显示 displayValue |
| `MetaDialog.vue` | 依赖 MetaForm | 随 MetaForm 自动适配 |
| `MetaListPage.vue` | 依赖 FilterBar + MetaTable | 随子组件自动适配 |
| `FilterBar.vue` | `field.type === 'select'` → 原生 `<select>` | 新增 `field.type === 'value_help'` → `ValueHelpField`（dropdown） |
| `TableHeaderFilter.vue` | `filterType === 'select'` → `ElSelect` | 新增 `filterType === 'value_help'` → `ValueHelpField` |
| `DynamicFilters.vue` | `field.type === 'foreign_key'` → `AppInput` | `foreign_key` + `value_help` → `ValueHelpField` |
| `InlineEditCell.vue` | `type === 'select'` → `ElSelect`（静态） | 新增 `type === 'value_help'` → `ValueHelpField`（dropdown） |
| `EnumSelect.vue` | 硬编码 `EnumService` | deprecated → 被 `ValueHelpField` 替代 |
| `EnumSearchHelp.vue` | 硬编码 `/api/v1/enum-types/{type}/values` | deprecated → 被 `ValueHelpField` 替代 |
| `ValueHelpSelector.vue` | 仅用于条件规则 | deprecated → 被 `ValueHelpField` 替代 |
| `AssociationSelector.vue` | 仅处理 Association | **保留**（Association 操作场景：assign/unassign），字段级选择被 `ValueHelpField` 替代 |

**Association 与 Value Help 边界设计（SAP 协作模式）**:

基于 SAP CDS 的设计哲学，Association 和 Value Help 是**协作关系**而非互斥关系：

| 维度 | Association | Value Help |
|------|-------------|------------|
| **定义** | 关系语义（谁和谁关联、基数、生命周期） | 字段级选择行为（如何选择、搜索、展示、验证） |
| **SAP 对标** | `association [1..1] to I_Customer` | `@Consumption.valueHelpDefinition` |
| **Salesforce 对标** | Lookup / Master-Detail Relationship | Lookup Filter + Search Layout |
| **数据层** | 定义 JOIN 路径、导航属性 | 定义 F4 帮助的数据源和搜索行为 |
| **UI 层** | 详情页的关联面板（AssociationPanel） | 表单字段的值选择器（ValueHelpField） |
| **操作** | assign / unassign / 导航到详情 | select / search / validate |

**协作规则**:
1. **字段级选择**（如选择客户、选择上级组织）→ `ValueHelpField`（source 从 Association 推导）
2. **关联对象管理**（如为角色分配用户、为用户组添加成员）→ `AssociationSelector` + v2 Association API
3. **SAP 模式**：当字段有 `association [1..1]`（单值关联），SAP 自动生成 Value Help。我们的系统同样：当字段有 Association 且 `cardinality = 1`，自动推导 `value_help.source.type = bo, target_bo = association.target_bo`
4. **多对多关联**（如 role.users, user_group.members）→ 这是 Association 操作场景，用 `AssociationSelector`，不走 `ValueHelpField`

**自动推导示例**:
```yaml
# user_group.yaml 中 parent_id 字段
fields:
  - id: parent_id
    name: 上级组织
    type: integer
    associations:
      - name: parent
        target_bo: organization_region
        cardinality: "1"              # 单值关联 → 自动推导 Value Help
    value_help:                        # 可显式声明，也可从 association 自动推导
      source:
        type: bo
        target_bo: organization_region  # ← 从 association.parent.target_bo 推导
        value_field: id
        display_field: region_name
        hierarchy:
          enabled: true
          parent_field: parent_id
```

**适配优先级**:
1. **P0**: MetaForm / MetaTable / MetaDialog（表单和列表核心场景）
2. **P1**: FilterBar / DynamicFilters（过滤场景）
3. **P2**: InlineEditCell / TableHeaderFilter（内联编辑和列头过滤场景）

#### 9.3.5a Value Help 与 Validation Rule 协作设计

**行业对标**：

| 产品 | 前置预防（Value Help 层） | 后置纠正（Validation 层） |
|------|--------------------------|--------------------------|
| **SAP** | `useForValidation: true` 限制输入 | Behavior Definition `validation` on save |
| **Salesforce** | Lookup Filter 限制可选项 | Validation Rule 保存时检查 |
| **D365** | Lookup Filter 前置过滤 | Business Rule / Plugin 后置验证 |

**协作矩阵**：

| `behavior.validation` | `behavior.binding_strength` | 前置行为 | 后置行为 | 典型场景 |
|-----------------------|----------------------------|----------|----------|----------|
| `true` | `strict` | 只能从 VH 列表选择 | 可自动生成 VH Validation Rule（双重保障） | 订单状态、用户类型 |
| `true` | `loose` | VH 建议选项，用户可自由输入 | 需要 Validation Rule 检查合法性 | 自由文本+建议 |
| `false` | - | 无前置验证 | 完全依赖 Validation Rule | 复杂业务校验 |

**自动生成 Validation Rule**：
```python
def generate_value_help_validation_rule(field: EnhancedMetaField, vh_config: ValueHelpConfig) -> Optional[MetaValidation]:
    if vh_config.behavior.validation and vh_config.behavior.binding_strength == "strict":
        return MetaValidation(
            id=f"vh_validate_{field.id}",
            name=f"Value Help 验证: {field.name}",
            scope=RuleScope.FIELD,
            triggers=[RuleTrigger.BEFORE_SAVE],
            condition="",
            action=f"value_help_validate('{field.id}', '{vh_config.source.type}', '{vh_config.source.enum_type_id or vh_config.source.target_bo}')",
            message=f"{field.name} 的值不在有效选项列表中",
            severity=ValidationSeverity.ERROR,
        )
    return None
```

#### 9.3.6 YAML 迁移函数设计

```python
def migrate_to_unified_value_help(field: EnhancedMetaField) -> Optional[ValueHelpConfig]:
    if hasattr(field, '_value_help_migrated'):
        return field._value_help_migrated

    source = None
    behavior = ValueHelpBehavior()
    presentation = ValueHelpPresentation()

    # 1. 从 enum_reference 迁移
    if field.enum_reference:
        er = field.enum_reference
        source = ValueHelpSource(
            type="enum",
            enum_type_id=er.enum_type_id,
            filter_by_dimension=er.filter_by_dimension if hasattr(er, 'filter_by_dimension') else {},
            value_filter=er.value_filter if hasattr(er, 'value_filter') else {},
            sort_by=er.sort_by if hasattr(er, 'sort_by') else "",
            i18n_join_fields=er.i18n_join_fields if hasattr(er, 'i18n_join_fields') else [],
            default_value_code=er.default_value_code if hasattr(er, 'default_value_code') else "",
        )
        behavior.binding_strength = er.binding_strength.value if hasattr(er, 'binding_strength') else "strict"
        behavior.validation = er.binding_strength == EnumBindingStrength.STRICT if hasattr(er, 'binding_strength') else True
        presentation.result_type = "dropdown"
        presentation.display_format = er.display_format if hasattr(er, 'display_format') else ""
        presentation.color_mapping = er.color_mapping if hasattr(er, 'color_mapping') else {}

    # 2. 从 dimension_reference.search_help 迁移
    elif field.dimension_reference:
        dr = field.dimension_reference
        sh = dr.search_help or {}
        source = ValueHelpSource(
            type="bo",
            target_bo=dr.target_bo,
            value_field="id",
            display_field=dr.display_field,
            code_field=dr.code_field,
            apply_target_permissions=dr.apply_target_permissions,
        )
        behavior.min_search_length = sh.get("min_length", 0)
        behavior.validation = True
        behavior.binding_strength = "strict"
        # additional_bindings → parameter_bindings
        for ab in sh.get("additional_bindings", []):
            behavior.parameter_bindings.append(ValueHelpParameterBinding(
                local_field=ab.get("source_field", ""),
                target_field=ab.get("target_field", ""),
            ))
        presentation.result_type = "dialog"
        presentation.display_format = f"{{{dr.code_field}}} - {{{dr.display_field}}}"

    # 3. 从旧 UIAnnotation.value_help 迁移
    if field.ui and field.ui.value_help:
        old_vh = field.ui.value_help
        behavior.validation = old_vh.validation
        behavior.enabled_condition = old_vh.enabled_condition
        if old_vh.label:
            presentation.display_format = old_vh.label

    # 4. 从 UIAnnotation.widget 推断 result_type
    if field.ui and field.ui.widget:
        widget_map = {
            "select": "dropdown",
            "lookup": "dialog",
            "select_with_search": "dropdown",
        }
        if not presentation.result_type or presentation.result_type == "dropdown":
            presentation.result_type = widget_map.get(field.ui.widget, "dropdown")

    if source:
        config = ValueHelpConfig(source=source, behavior=behavior, presentation=presentation)
        field._value_help_migrated = config
        return config

    return None
```

### 9.4 Alternatives Considered

| Option | Pros | Cons | Decision |
| ------ | ---- | ---- | -------- |
| **A: 简单扩展** - 在现有 ValueHelpConfig 上加字段 | 改动最小 | 无法解决碎片化问题，source/behavior/presentation 混在一起 | Rejected |
| **B: 三层抽象模型** - Source/Behavior/Presentation 分离 | 清晰分层，各层独立变化，借鉴 SAP 最佳实践 | 改动较大，需要迁移 | **Selected** |
| **C: 完全重写** - 废弃所有旧模型，只保留新模型 | 最干净 | 破坏兼容性，风险高 | Rejected |

**选择 Option B 的理由**：
1. 三层分离与 SAP @Consumption.valueHelpDefinition + PresentationVariant 的设计哲学一致
2. Source 层可扩展新的数据源类型（如 OData / GraphQL），不影响 Behavior 和 Presentation
3. 向后兼容通过迁移函数实现，旧 YAML 继续工作
4. 改动范围可控，不破坏现有 API

### 9.5 Implementation & Migration Plan

- **Implementation Order**:
  1. 新增 ValueHelpSource / ValueHelpBehavior / ValueHelpPresentation / ValueHelpConfig 数据模型
  2. 重构 yaml_loader.py，新增 `parse_value_help_block()` 函数
  3. 实现 `migrate_to_unified_value_help()` 迁移函数
  4. 实现 EnumValueHelpProvider / BoValueHelpProvider / CustomValueHelpProvider
  5. 新增 value_help_api.py 路由
  6. 扩展 BO 元数据 API，返回 value_help 配置
  7. 实现 useValueHelp.js Composable
  8. 实现 ValueHelpField.vue + SearchHelpDialog.vue
  9. DynamicForm 集成 ValueHelpField
  10. 编写单元测试 + E2E 测试

- **Risk Mitigation**:
  - 旧模型兼容性风险 → 迁移函数 + 旧字段保留 + 全量回归测试
  - 前端组件迁移风险 → 新旧组件并存 + feature flag 切换
  - API 性能风险 → Enum Provider 使用缓存 + BO Provider 使用分页

- **Testing Strategy**:
  - Unit tests: ValueHelpSource/Behavior/Presentation 解析, Provider.search/resolve, 迁移函数
  - Integration tests: Value Help API 端点, 元数据 API 扩展
  - E2E tests: DynamicForm 中 ValueHelpField 交互（枚举下拉、BO弹窗、层级树形、级联过滤）

- **Rollback Plan**:
  - 后端：ValueHelpConfig 新模型与旧模型并存，迁移函数可禁用
  - 前端：DynamicForm 可通过 feature flag 切回旧组件
  - API：v2 Value Help API 独立路由，不影响现有 v1 API

## 10. TBD List

| ID     | Item                          | Missing Information           | Next Step              | Status |
| ------ | ----------------------------- | ----------------------------- | ---------------------- | ------ |
| TBD-1  | Custom Source Provider 详细设计 | 自定义 API 端点的认证/鉴权方式 | 实现时与用户确认       | Open |
| TBD-2  | 层级树形选择的交互细节         | 节点展开/折叠/搜索的交互规范   | 实现时与用户确认       | Open |
| TBD-3  | 多值 Value Help（多选）        | 是否需要在 Phase 12 支持      | 已确认：Phase 12 必须支持 | ✅ Resolved → FR-006a |
| TBD-4  | Value Help 缓存策略            | 枚举数据是否需要前端缓存       | 实现时决定             | Open |
| TBD-5  | Association 与 Value Help 的边界 | 两者是互斥还是协作           | 已确认：SAP 协作模式，Association 定义关系语义，Value Help 定义选择行为 | ✅ Resolved → RFC 9.3.5 |

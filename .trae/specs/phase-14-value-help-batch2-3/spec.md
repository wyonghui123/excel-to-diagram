# Phase 14 子 Spec: Value Help Batch 2/3 — YAML 迁移 + 组件集成

> **父 Spec**: [unified-metadata-api-architecture/spec.md](../unified-metadata-api-architecture/spec.md) → 十三、Phase 14
> **关联 Spec**: [phase-12-value-help-architecture/spec.md](../phase-12-value-help-architecture/spec.md)
> **创建日期**: 2026-05-18
> **更新日期**: 2026-05-19
> **当前状态**: ✅ Phase 14 已完成 100% — Batch 1/2/3 全部交付，7 YAML 17字段，组件集成完成

---

## 一、背景

### 1.1 Batch 1 已完成交付（60%）

| 已交付 | 实现 | 文件 | 测试 |
|--------|------|------|------|
| EnumValueHelp 枚举值帮助 | `EnumVHProvider` | `meta/core/value_help_providers.py` | ✅ |
| BO Association 关联帮助 | `BoVHProvider` | `meta/core/value_help_providers.py` | ✅ |
| 自定义帮助 | `CustomVHProvider` | `meta/core/value_help_providers.py` | ✅ |
| v2 Value Help API | `GET /api/v2/value-help/<type>/<id>` + `/resolve` | `meta/api/value_help_api.py` | ✅ |
| 前端 Composable | `useValueHelp()` — 12 个导出 | `src/composables/useValueHelp.js` | 44 测试 |
| ValueHelpField 组件 | dropdown / dialog / inline 三模式 | `src/components/common/ValueHelpField.vue` | - |
| SearchHelpDialog 组件 | flat / tree / tree_flat 三模式 | `src/components/common/SearchHelpDialog.vue` | - |
| **已集成 FilterBar** | `v-if="field.type === 'value_help'"` | `FilterBar.vue` L45-L52 | ✅ |
| **已集成 InlineEditCell** | `v-if="fieldConfig.type === 'value_help'"` | `InlineEditCell` L30-L36, L55-L61 | ✅ |
| **已配置 YAML** 6 文件 10 字段 | 见下方 | 见下方 | ✅ |

### 1.2 已配置 value_help 的 YAML 清单

| YAML 文件 | 字段 | source type | source_id | result_type |
|-----------|------|-------------|-----------|-------------|
| `relationship.yaml` | `source_bo_id` | bo | business_object | select |
| `audit_log.yaml` | `category` | enum | audit_log_category | dropdown |
| `audit_log.yaml` | `log_level` | enum | audit_log_level | dropdown |
| `audit_log.yaml` | `action` | enum | audit_action_type | dropdown |
| `enum_type.yaml` | `category` | enum | enum_category | dropdown |
| `enum_value.yaml` | `enum_type_id` | bo | enum_type | dropdown |
| `enum_value.yaml` | `is_active` | enum | yes_no | dropdown |
| `user.yaml` | `status` | enum | user_status | dropdown |
| `user_group.yaml` | `parent_id` | bo | user_group | dialog(tree) |
| `user_group.yaml` | `manager_id` | bo | user | dialog |

---

## 二、目标

1. **Batch 2**: 9 个核心业务对象的 YAML value_help 配置迁移
2. **Batch 3**: 剩余前端组件集成（TableHeaderFilter） + TreeValueHelp 懒加载实现

---

## 三、Batch 2: YAML value_help 批量迁移

### 3.1 待迁移对象清单（9 个对象，~15 个字段）

| # | YAML 文件 | 需配置字段 | source type | source_id | result_type | 级联依赖 |
|---|-----------|-----------|-------------|-----------|-------------|---------|
| 1 | [domain.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/domain.yaml) | `version_id` | bo | version | dropdown | - |
| 2 | [sub_domain.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/sub_domain.yaml) | `domain_id` | bo | domain | dropdown | version_id → domain_id |
| 3 | [service_module.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/service_module.yaml) | `sub_domain_id` | bo | sub_domain | dropdown | domain_id → sub_domain_id |
| 4 | [business_object.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/business_object.yaml) | `service_module_id` | bo | service_module | dropdown | 5级 cascade_select |
| 5 | [product.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/product.yaml) | `owner_id` | bo | user | dialog | - |
| 6 | [version.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/version.yaml) | `product_id` | bo | product | dropdown | - |
| 7 | [role.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/role.yaml) | `parent_id` (如有) | bo | role | dialog(tree) | - |
| 8 | [relationship.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/relationship.yaml) | `target_bo_id` | bo | business_object | dropdown | - |
| 9 | [management_dimension.yaml](file:///d:/filework/excel-to-diagram/meta/schemas/management_dimension.yaml) | 关联字段 | bo | TBD | dropdown | - |

### 3.2 配置模板

#### BO 类型 dropdown（以 domain.version_id 为例）

```yaml
# domain.yaml
fields:
  - id: version_id
    name: 所属版本
    type: integer
    required: true
    value_help:
      source:
        type: bo
        target_bo: version
        value_field: id
        display_field: name
        code_field: code
        apply_target_permissions: false
      behavior:
        validation: true
        binding_strength: strict
      presentation:
        result_type: dropdown
        display_format: "{code} - {name}"
        columns:
          - field: code
            label: 编码
            width: 120
          - field: name
            label: 名称
            width: 200
```

#### BO 类型 dialog（以 product.owner_id 为例）

```yaml
# product.yaml
fields:
  - id: owner_id
    name: 负责人
    type: integer
    value_help:
      source:
        type: bo
        target_bo: user
        value_field: id
        display_field: username
        apply_target_permissions: false
      behavior:
        validation: true
        binding_strength: strict
        search_fields: [username, display_name]
      presentation:
        result_type: dialog
        display_format: "{username}"
        columns:
          - field: username
            label: 用户名
            width: 150
          - field: display_name
            label: 显示名称
            width: 200
```

#### 带级联依赖（以 sub_domain.domain_id 为例）

```yaml
# sub_domain.yaml
fields:
  - id: domain_id
    name: 所属领域
    type: integer
    required: true
    value_help:
      source:
        type: bo
        target_bo: domain
        value_field: id
        display_field: name
        apply_target_permissions: false
      behavior:
        validation: true
        binding_strength: strict
        parameter_bindings:
          - param: filters[version_id]
            field: version_id
      presentation:
        result_type: dropdown
        display_format: "{name}"
        columns:
          - field: name
            label: 名称
            width: 200
```

### 3.3 执行步骤

#### M2.1: domain.yaml + sub_domain.yaml（2 对象 2 字段）

两个对象形成 2 级级联：
- domain.yaml: `version_id` → bo/version (dropdown)
- sub_domain.yaml: `domain_id` → bo/domain (dropdown, 依赖 version_id)

**验证**: 创建 sub_domain 时，选择 version → domain_id 下拉仅显示该版本的 domain

#### M2.2: service_module.yaml + business_object.yaml（2 对象 2 字段）

- service_module.yaml: `sub_domain_id` → bo/sub_domain (dropdown)
- business_object.yaml: `service_module_id` → bo/service_module (dropdown, 需与 cascade_select 协同)

**验证**: 创建 business_object 时，5 级级联下拉正常

#### M2.3: product.yaml + version.yaml（2 对象 2 字段）

- product.yaml: `owner_id` → bo/user (dialog)
- version.yaml: `product_id` → bo/product (dropdown)

**验证**: version 管理页面 product_id 下拉正常

#### M2.4: role.yaml + relationship.yaml + management_dimension.yaml（3 对象）

- role.yaml: 检查并配置 `parent_id` (如有)
- relationship.yaml: 补充 `target_bo_id` value_help
- management_dimension.yaml: 确认并配置关联字段

**验证**: 3 个对象的关联字段 value_help 正常

---

## 四、Batch 3: 组件集成 + TreeValueHelp

### 4.1 任务清单

| # | 任务 | 组件 | 当前状态 | 目标 |
|---|------|------|---------|------|
| 1 | TableHeaderFilter 集成 ValueHelpField | `TableHeaderFilter.vue` | ❌ 仅支持 search/select/date-range/number-range/multi-select | 新增 `value_help` 类型 |
| 2 | TreeValueHelp 懒加载实现 | `SearchHelpDialog.vue` L231-L233 | ❌ `loadTreeNode` 返回 `[]` | 调用后端 API 按需加载子节点 |
| 3 | MetaForm 集成确认 | `MetaForm.vue` | ❓ 未验证 | 确认并补充集成 |

### 4.2 TableHeaderFilter 集成方案

当前 TableHeaderFilter 支持 5 种 filterType：`search`, `select`, `date-range`, `number-range`, `multi-select`。

需新增第 6 种：**`value_help`**。

**实现方案**（[TableHeaderFilter.vue L43-L151](file:///d:/filework/excel-to-diagram/src/components/common/TableHeaderFilter/TableHeaderFilter.vue#L43-L151)）：

```vue
<!-- 在 template 中 condition 区域新增 -->
<div v-if="filterType === 'value_help' && valueHelpConfig"
     class="thf-value-help-container" style="min-width: 220px">
  <ValueHelpField
    :model-value="modelValue"
    :value-help-config="valueHelpConfig"
    :placeholder="placeholder"
    @update:model-value="handleChange"
  />
</div>
```

**改动要点**:
1. 新增 prop: `valueHelpConfig: { type: Object, default: null }`
2. 新增 `<div v-else-if="filterType === 'value_help'">` 模板块
3. 从 columns 的 `filter_config.value_help` 透传 `valueHelpConfig` 给 TableHeaderFilter
4. 在 `useMetaList.js` 中 `_backfillColumnFilterType` 增加 `value_help` 类型的识别

**验证**: 配置了 `value_help` 的字段在列头过滤时显示 ValueHelpField 下拉

### 4.3 TreeValueHelp 懒加载实现

**当前状态**（[SearchHelpDialog.vue L231-L233](file:///d:/filework/excel-to-diagram/src/components/common/SearchHelpDialog/ValueHelpField.vue)）:

```javascript
async function loadTreeNode(node, resolve) {
  resolve([])  // STUB：直接返回空数组
}
```

**目标实现**:

```javascript
async function loadTreeNode(node, resolve) {
  const isRoot = node.level === 0
  const params = {
    page: 1,
    pageSize: node.level === 0 ? 100 : 50,
  }

  // 根节点：获取顶层记录
  // 子节点：按 parent_id 过滤
  if (!isRoot) {
    const parentIdField = props.valueHelpConfig?.source?.hierarchy?.parent_field || 'parent_id'
    params.filters = { [parentIdField]: node.data.id }
  }

  try {
    const sourceType = props.valueHelpConfig?.source?.type
    const sourceId = props.valueHelpConfig?.source?.target_bo
      || props.valueHelpConfig?.source?.enum_type_id

    const response = await boService.searchValueHelp(sourceType, sourceId, params)
    const items = response.data?.data || []

    const treeNodes = items.map(item => ({
      id: item.id,
      label: item.display || item.name || item.code,
      data: item,
      leaf: node.level >= 3, // 限制最大深度
    }))

    resolve(treeNodes)
  } catch (err) {
    console.error('[SearchHelpDialog] loadTreeNode failed:', err)
    resolve([])
  }
}
```

**改动文件**:
- `src/components/common/SearchHelpDialog.vue` — 替换 `loadTreeNode` 实现
- `src/composables/useValueHelp.js` — 新增 `loadTreeNode(page, parentId)` 方法

**验证**: 用户组 parent_id 字段使用 dialog(tree) 模式，树节点可正常展开并加载子级

### 4.4 MetaForm 集成确认

需检查 [MetaForm.vue](file:///d:/filework/excel-to-diagram/src/components/bo/MetaForm.vue) 中：

1. 是否已识别 `ui.widget === 'value_help'` 并渲染 `ValueHelpField`
2. 是否已透传 `formValues`（用于 parameter_bindings）
3. 是否已处理 `update:modelValue` / `update:displayValue` 事件

如未集成，参照 `FilterBar.vue` L45-L52 的模式进行集成。

---

## 五、实施计划（5 个里程碑）

### M1: Batch 2 — domain/sub_domain + service_module/business_object YAML

**产出**:
- `domain.yaml` 新增 `version_id` value_help 配置
- `sub_domain.yaml` 新增 `domain_id` value_help 配置（含 version_id 参数绑定）
- `service_module.yaml` 新增 `sub_domain_id` value_help 配置
- `business_object.yaml` 新增 `service_module_id` value_help 配置

**验证**: 架构数据管理 4 个对象的表单中，关联字段显示为 ValueHelpField 下拉

### M2: Batch 2 — product/version + role/relationship/management_dimension YAML

**产出**:
- `product.yaml` 新增 `owner_id` value_help 配置
- `version.yaml` 新增 `product_id` value_help 配置
- `role.yaml` 补充关联字段
- `relationship.yaml` 补充 `target_bo_id`
- `management_dimension.yaml` 补充关联字段

**验证**: 产品/版本/角色/关系管理页面各关联字段 value_help 正常

### M3: Batch 3 — TableHeaderFilter 集成

**产出**:
- `TableHeaderFilter.vue` 新增 `value_help` filterType 支持
- `useMetaList.js` 中 `_backfillColumnFilterType` 增加 `value_help` 类型识别

**验证**: 配置了 value_help 的字段在列头过滤时弹出 ValueHelpField

### M4: Batch 3 — TreeValueHelp 懒加载

**产出**:
- `SearchHelpDialog.vue` `loadTreeNode` 从 stub 变为完整实现
- `useValueHelp.js` 增加 `loadTreeNode` 方法

**验证**: user_group.parent_id dialog(tree) 模式的树节点可展开加载子节点

### M5: MetaForm 集成确认 + 端到端测试

**产出**:
- 确认/补充 `MetaForm.vue` 的 ValueHelpField 集成
- 端到端回归测试

**验证**: 所有已配置 value_help 的对象在 MetaForm 中正常渲染

---

## 六、文件变更清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `meta/schemas/domain.yaml` | 修改 | + version_id value_help |
| `meta/schemas/sub_domain.yaml` | 修改 | + domain_id value_help (含 parameter_bindings) |
| `meta/schemas/service_module.yaml` | 修改 | + sub_domain_id value_help |
| `meta/schemas/business_object.yaml` | 修改 | + service_module_id value_help |
| `meta/schemas/product.yaml` | 修改 | + owner_id value_help |
| `meta/schemas/version.yaml` | 修改 | + product_id value_help |
| `meta/schemas/role.yaml` | 修改 | + parent_id value_help (如有) |
| `meta/schemas/relationship.yaml` | 修改 | + target_bo_id value_help |
| `meta/schemas/management_dimension.yaml` | 修改 | 关联字段 value_help |
| `src/components/common/TableHeaderFilter/TableHeaderFilter.vue` | 修改 | + value_help filterType |
| `src/composables/useMetaList.js` | 修改 | _backfillColumnFilterType 增加 value_help 识别 |
| `src/components/common/SearchHelpDialog.vue` | 修改 | loadTreeNode 完整实现 |
| `src/composables/useValueHelp.js` | 修改 | + loadTreeNode 方法 |
| `src/components/bo/MetaForm.vue` | 确认/修改 | ValueHelpField 集成 |

---

## 七、验收标准

### Batch 2 验收

- [ ] 9 个对象的 YAML 均包含正确的 value_help 配置
- [ ] `GET /api/v2/bo/<object>/` 接口返回的 `_schema` 中包含 value_help 配置
- [ ] 创建/编辑这 9 个对象时，关联字段显示为 ValueHelpField（非原始 input）
- [ ] 级联依赖正确生效（选 version → domain 过滤，选 domain → sub_domain 过滤）
- [ ] 所有已有 value_help 的字段无回归

### Batch 3 验收

- [ ] TableHeaderFilter 支持 `value_help` 类型，列头过滤使用 ValueHelpField
- [ ] dialog(tree) 模式的 `loadTreeNode` 可正常展开并懒加载子节点
- [ ] MetaForm.vue 已正确集成 ValueHelpField
- [ ] 全量回归测试通过

---

## 八、风险与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|---------|
| cascade_select 与 value_help 的 parameter_bindings 冲突 | 中 | 高 | 先完成 value_help，再与 Phase 18.3 cascade_select 联合测试 |
| addFilterParam 逻辑复制导致 `filters[...]` 格式不一致 | 中 | 中 | 使用 FilterService.buildFilterQueryParams 统一构建 |
| business_object.yaml 的 5 级级联配置过于复杂 | 中 | 中 | 分步实现：先单层 value_help，再叠加参数绑定 |

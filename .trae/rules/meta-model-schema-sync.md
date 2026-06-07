# 元模型 Schema 同步规范

> **最后更新**: 2026-05-19 (v1.5 更新)
>
> **状态**: Active - 核心规范，所有 YAML 变更必须遵循
>
> **相关规范**:
> - [YAML 规范 v2.0](../../docs/architecture/02-yaml-conventions-v2.md) ← **完整语法参考**
> - [ARCHITECTURE_V2.md](../../docs/ARCHITECTURE_V2.md) ← **架构总览**
> - [API 契约 v2.0](../../docs/architecture/04-api-contracts-v2.md) ← **API 定义**

## 核心原则

1. **YAML是元模型的唯一真相来源**（`meta/schemas/*.yaml`）
2. **元模型变更必须同步Schema**（先YAML → diff → dry-run → execute）
3. **层级处理必须基于元数据模型**（禁止硬编码）
4. **关系类型必须基于relation_types注册表**
5. **YAML 单一事实原则**（配置最小化，智能推导）

---

## YAML 单一事实原则 ⭐ 重要

### 原则说明

YAML 配置应遵循**最小化配置**原则，系统通过智能推导自动计算默认值：

```
┌─────────────────────────────────────────────────────────────┐
│              YAML 单一事实原则                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  1. 只配置例外情况，无需重复声明默认值                        │
│  2. 通过 semantics 定义业务语义，自动推导权限                 │
│  3. 后端统一计算，前端直接使用                               │
│  4. 配置层级：全局 → detail 级别覆盖                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 字段权限智能推导规则

后端 `bo_framework.py` 已实现以下智能推导：

| 规则 | 触发条件 | 推导结果 |
|------|---------|---------|
| **系统字段** | `id`, `created_at`, `updated_at`, `created_by`, `updated_by` | `readonly: true`, `editable: false` |
| **时间戳字段** | `type: datetime/timestamp/date` | `readonly: true`, `editable: false` |
| **敏感字段** | `password_hash`, `password`, `secret`, `token`, `api_key` | `visible: false`, `hidden_in_*: true` |
| **业务键字段** | `semantics.business_key: true` | `readonly: true`（创建后不可修改） |
| **计算字段** | `semantics.computed: true` 或 `calculated: true` | `readonly: true`, `editable: false` |

---

## Enum 字段规范 ⭐ 重要

### 定义规范

Enum 字段通过 `enum_values` 定义枚举值：

```yaml
fields:
  - id: status
    name: 状态
    type: string                    # 类型可以是 string 或 enum
    enum_values:                    # 枚举值定义
      - value: active               # 存储值
        label: 活跃                 # 显示标签
        color: success              # 标签颜色（可选）
      - value: inactive
        label: 未激活
        color: info
      - value: locked
        label: 已锁定
        color: danger
```

### 显示规范

| 场景 | 规范 | 说明 |
|------|------|------|
| **只读模式** | 显示 `label` 而非 `value` | 用户看到"活跃"而不是"active" |
| **编辑模式** | 使用下拉选择（Value Help） | 用户从列表中选择，而非手动输入 |
| **列表模式** | 显示 `label`，使用 `color` 作为标签颜色 | 统一的视觉呈现 |

### 前端判断逻辑

```javascript
// 判断是否为 Enum 字段
function isEnumField(field) {
  return !!(field.enum_values || field.type === 'enum')
}

// 获取 Enum 显示标签
function getEnumLabel(field, value) {
  if (!field.enum_values) return value
  const option = field.enum_values.find(o => o.value === value)
  return option?.label || value
}

// 获取 Enum 标签颜色
function getEnumColor(field, value) {
  if (!field.enum_values) return ''
  const option = field.enum_values.find(o => o.value === value)
  return option?.color || ''
}
```

### 后端返回格式

后端 `bo_framework.py` 已返回 `enum_values`：

```json
{
  "id": "status",
  "name": "状态",
  "type": "string",
  "enum_values": [
    {"value": "active", "label": "活跃", "color": "success"},
    {"value": "inactive", "label": "未激活", "color": "info"},
    {"value": "locked", "label": "已锁定", "color": "danger"}
  ]
}
```

### 常见错误

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| 显示 `inactive` 而非"未激活" | 前端未使用 `enum_values` | 使用 `field.enum_values` 判断并显示 `label` |
| 编辑时无下拉选择 | 未判断 `enum_values` | 使用 `field.enum_values || field.type === 'enum'` 判断 |
| 标签颜色不正确 | 未使用 `color` 属性 | 从 `enum_values[].color` 获取颜色 |

### YAML 配置示例

```yaml
# [X] 错误：冗余配置
fields:
  - id: username
    ui:
      visible: true        # 冗余：默认就是 true
      editable: true       # 冗余：默认就是 true
      readonly: false      # 冗余：默认就是 false
      hidden_in_detail: false  # 冗余：默认就是 false

  - id: created_at
    type: datetime
    ui:
      editable: false      # 冗余：datetime 类型自动推导为只读
      readonly: true       # 冗余：系统字段自动推导为只读

# [OK] 正确：最小化配置
fields:
  - id: username
    semantics:
      business_key: true   # 自动推导：创建后不可修改

  - id: created_at
    type: datetime         # 自动推导：只读

  - id: password_hash
    ui:
      visible: false       # 仅配置例外情况

# [OK] 正确：detail 级别仅覆盖需要修改的字段
ui_view_config:
  detail:
    tabs:
      - id: basic
        fields:
          - username       # 使用字符串，引用 fields 定义
          - display_name
          - email
          - status         # 仅在需要覆盖时使用对象格式
          - created_at
```

### 配置层级优先级

```
优先级（从高到低）:

1. detail.tabs[].fields[].readonly     # 最高优先级
2. detail.tabs[].fields[].editable
3. detail.tabs[].fields[].visible
4. fields[].ui.readonly
5. fields[].ui.editable
6. fields[].ui.visible                 # 最低优先级
7. 智能推导规则                         # 兜底默认值
```

### 触发关键词

涉及以下场景时，必须遵循单一事实原则：

- 新增/修改 YAML 配置
- 设计字段权限（visible/editable/readonly）
- 设计 detail/form/list 视图配置
- 配置字段 UI 属性

---

## 变更流程

### 新增业务对象

```
1. 在 meta/schemas/ 创建新的 YAML 文件
2. 定义 id, name, table_name, description, fields, relations, actions, validations
3. 运行: python -m meta.tools.sync_schema --diff
4. 运行: python -m meta.tools.sync_schema --dry-run
5. 确认后执行: python -m meta.tools.sync_schema --execute
6. 运行测试: python meta/tests/run_all_tests.py
```

### 修改现有对象

```
1. 打开对应的 YAML 文件
2. 修改字段定义（新增/删除/修改）
3. 运行 --diff 检查
4. 确认变更后执行同步
5. 运行测试确认 8/8 全部通过
```

### 新增字段时检查清单

- [ ] 字段定义完整性（id, name, type, description）
- [ ] 关联字段配置（ui.widget: select, ui.relation, ui.display_field）
- [ ] 视图配置更新（list.columns, detail.facets, form.sections）

### 修改视图配置时检查清单

- [ ] 列表视图：确保列字段在 fields 中已定义
- [ ] 详情视图：关联字段使用 _name 后缀的显示字段
- [ ] 表单视图：关联字段配置 ui.widget: select 和 ui.relation

### 层级关系变更时检查清单

- [ ] DynamicForm.vue 的 HIERARCHY_READONLY_FIELDS
- [ ] manage_api.py 的 _enrich_record_with_names

### 3.3 前端组件规范

**[OK] 当前推荐（v2 更新）**：

```vue
<!-- 使用元数据驱动的统一组件 -->
<template>
  <MetaListPage
    object-type="user"
    :enable-detail="true"
    :enable-auto-crud="true"
  />
</template>

<!-- 或 ObjectPage（更灵活） -->
<template>
  <ObjectPage
    object-type="product"
  />
</template>
```

**[X] 已废弃（Phase 19 待清理）**：

以下组件已废弃，请勿在新代码中使用：
- `DynamicForm.vue` → 已被 `MetaForm` + `MetaDialog` 替代
- `ArchDataManageApp.vue` → 已被独立的 Management 页面替代
- `DomainManagement.vue` → 已被 `MetaListPage` 替代

**迁移指南**：

| 废弃组件 | 替代方案 | 迁移时间 |
|---------|---------|----------|
| DynamicForm.vue | MetaForm / MetaDialog | Phase 19 |
| ArchDataManageApp.vue | 独立管理页面 | Phase 19 |
| DomainManagement.vue | MetaListPage (object-type="domain") | Phase 19 |
| manage_api.py 直接调用 | bo_api.py v2 API | 已完成 |

## 层级处理规范

### 层级过滤必须基于元数据

```javascript
// [X] 禁止硬编码
switch (dimension) {
  case 'domain': params.id = domainIds; break;
  case 'sub_domain': params.domain_id = domainIds; break;
}

// [OK] 正确：基于元数据动态获取
const schema = getMetaSchema(dimension)
const filterField = getParentFilterField(schema)
params[filterField] = ancestorIds
```

### 层级过滤参数

| 当前维度 | 过滤参数 | 来源 |
|---------|---------|------|
| domain | id | 直接用ID过滤 |
| sub_domain | domain_id | sub_domain.fields.domain_id |
| service_module | sub_domain_id | service_module.fields.sub_domain_id |
| business_object | service_module_id | business_object.fields.service_module_id |

### switch/if 必须覆盖所有维度

domain / sub_domain / service_module / business_object 全部覆盖

## 关系模型规范

- 关系类型定义：`meta/schemas/relationship.yaml#relation_types`
- 关系分类定义：`meta/schemas/relationship.yaml#relation_categories`
- 层级定义：`meta/schemas/hierarchies.yaml#hierarchies`
- 删除行为：`hierarchies.yaml#levels[].delete_behavior`
- 禁止硬编码关系类型和层级定义

## 命令参考

| 命令 | 说明 |
|------|------|
| `python -m meta.tools.sync_schema --diff` | 显示变更差异 |
| `python -m meta.tools.sync_schema --dry-run` | 预览SQL（不执行） |
| `python -m meta.tools.sync_schema --execute` | 执行Schema同步 |
| `python meta/tests/run_all_tests.py` | 运行全部测试 |

## 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 详情页显示ID而非名称 | 缺少 ui.display_field | 添加 display_field: xxx_name |
| 表单下拉框无选项 | 缺少 ui.widget/relation | 添加 widget: select, relation: xxx |
| 编辑时父元素可编辑 | HIERARCHY_READONLY_FIELDS不完整 | 在DynamicForm.vue中补充 |
| YAML修改后不生效 | 缓存未刷新 | DEV_MODE=1 或调用 /api/v1/meta/reload |

## 触发关键词

涉及以下关键词时，必须先读取相关YAML文件：
- domain, sub_domain, service_module, business_object
- 层级, 维度, 过滤, filter
- relation_code, PROVIDES, CALLS
- switch dimension, currentDim

涉及以下场景时，必须遵循 YAML 单一事实原则：
- 新增/修改 YAML 配置
- 设计字段权限（visible/editable/readonly）
- 设计 detail/form/list 视图配置
- 配置字段 UI 属性
- 编写详情页、表单、列表组件

涉及以下场景时，必须遵循 Enum 字段规范：
- 定义枚举字段（status, type 等有固定选项的字段）
- 显示枚举值（必须显示 label 而非 value）
- 编辑枚举字段（必须使用下拉选择/Value Help）
- 判断字段类型（使用 `field.enum_values` 而非仅 `field.type`）

## 详细参考

YAML文件结构、规则体系、Action执行器、Query查询等详细内容见：
- `.trae/context/architect/meta-model-guide.md`
- `meta/schemas/*.yaml`（源文件）

# YAML Schema 扩展示例：`child_list_config`

## 概述

`child_list_config` 是 `ui_view_config` 的扩展配置，用于定义在父对象详情页中嵌入的子对象列表的展示行为。

## 配置位置

在 YAML 文件的 `ui_view_config` 下添加 `child_sections` 配置：

```yaml
ui_view_config:
  # ... 现有的 list, detail, form 配置 ...

  # 子对象列表配置（新增）
  child_sections:
    - child_object: version                    # 子对象类型
      title: 版本列表                          # Section 标题
      display: expandable                      # 显示模式：always | expandable
      pageSize: 10                            # 分页大小
      columns:                                # 列配置
        - name
        - code
        - is_current
        - created_at
      actions:                                # 操作按钮
        - key: edit
          label: 编辑
        - key: delete
          label: 删除
        - key: set_current
          label: 设为当前版本
          condition: "row.is_current !== true"  # 条件显示
      defaultSort:
        field: created_at
        order: desc
```

## 完整示例：`product.yaml` 扩展示例

以下是 `product.yaml` 添加 `child_sections` 配置的完整示例：

```yaml
# ============================================
# 产品线元模型
# ============================================

id: product
name: 产品线
table_name: products
description: 产品线是业务系统的顶层分类，代表一个独立的产品或产品系列。
display_name_field: name

# ... 现有的 deletability, authorization, hierarchy 配置 ...

# ────────────────────────────────────────────
# UI 视图配置
# ────────────────────────────────────────────
ui_view_config:
  filter:
    layout: sidebar
    filters:
      - key: is_active
        title: 状态
        type: select
        position: 0
        options:
          - value: true
            label: 启用
          - value: false
            label: 禁用
  list:
    pageSize: 20
    columns:
      - key: name
        title: 名称
        width: 200
      - key: code
        title: 编码
        width: 120
      - key: is_active
        title: 状态
        width: 80
      - key: child_count
        title: 版本数
        width: 80
    selectable: true
  detail:
    facets:
      - title: 基本信息
        type: fieldGroup
        fields:
          - name
          - code
          - description
          - is_active
      - title: 系统信息
        type: fieldGroup
        fields:
          - created_at
          - updated_at
    showChangeHistory: true

  # ============================================
  # 子对象列表配置（新增）
  # ============================================
  child_sections:
    - child_object: version
      title: 版本列表
      display: expandable
      pageSize: 10
      columns:
        - key: name
          title: 版本名称
          width: 150
        - key: code
          title: 编码
          width: 100
        - key: is_current
          title: 当前版本
          width: 90
        - key: created_at
          title: 创建时间
          width: 160
      actions:
        - key: edit
          label: 编辑
          type: text
        - key: delete
          label: 删除
          type: text
          danger: true
          condition: "row.is_system !== true"
        - key: set_current
          label: 设为当前
          type: primary
          condition: "row.is_current !== true"
      defaultSort:
        field: created_at
        order: desc

# ────────────────────────────────────────────
# 关联关系
# ────────────────────────────────────────────
relations:
  - id: product_to_versions
    name: 包含版本
    type: parent_child
    target: version
    cardinality: "1:N"
```

## `child_sections` 配置详解

### 配置字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `child_object` | string | 是 | 子对象的类型名称 |
| `title` | string | 否 | Section 标题，默认使用子对象的 `label` |
| `display` | string | 否 | 显示模式：`always`（始终展开）或 `expandable`（可折叠） |
| `pageSize` | number | 否 | 分页大小，默认 10 |
| `columns` | array | 否 | 显示的列，默认显示所有可见列 |
| `actions` | array | 否 | 操作按钮配置 |
| `defaultSort` | object | 否 | 默认排序 |

### `columns` 子配置

```yaml
columns:
  - key: name                    # 字段键名（必填）
    title: 版本名称              # 列标题（默认使用字段的 label）
    width: 150                   # 列宽度
    minWidth: 120                # 最小宽度
    fixed: left                  # 固定列：left | right | false
    sortable: true               # 是否可排序
    filterable: true             # 是否可过滤
```

### `actions` 子配置

```yaml
actions:
  - key: edit                    # 操作键名（必填）
    label: 编辑                  # 显示标签
    type: text                   # 按钮类型：text | primary | danger
    icon: edit                   # 图标名称
    condition: "row.is_system !== true"  # 显示条件（可选）
    confirmMessage: "确定要编辑吗？"  # 确认消息（可选）
```

### `display` 显示模式

| 模式 | 说明 |
|------|------|
| `always` | Section 始终展开，不显示折叠图标 |
| `expandable` | Section 可折叠，点击标题可展开/折叠 |

## 多层级示例：四级父子关系

对于 Domain → SubDomain → ServiceModule → BusinessObject 的四级关系：

```yaml
ui_view_config:
  child_sections:
    # 第一层：Domain 的子对象
    - child_object: sub_domain
      title: 子域名列表
      display: expandable
      pageSize: 10
      columns:
        - name
        - code
        - child_count
      actions:
        - edit
        - delete

    # 第二层：SubDomain 的子对象（在 SubDomain 详情页中）
    - child_object: service_module
      title: 服务模块列表
      display: expandable
      pageSize: 10
      columns:
        - name
        - code
      actions:
        - edit
        - delete
```

## 前端使用示例

### 在 ObjectPage 中使用

```vue
<template>
  <ObjectPage
    :object-type="objectType"
    :id="recordId"
  >
    <template #sections>
      <!-- 基本信息 Section -->
      <ObjectSection title="基本信息" :fields="basicFields" />

      <!-- 子对象列表 Section（自动渲染） -->
      <ObjectChildSection
        v-for="section in childSections"
        :key="section.child_object"
        :parent-object-type="objectType"
        :child-object-type="section.child_object"
        :parent-id="recordId"
        :config="section"
        :title="section.title"
        :display-mode="section.display"
      />
    </template>
  </ObjectPage>
</template>

<script setup>
import { computed } from 'vue'
import { ObjectPage, ObjectChildSection } from '@/components/common'

const props = defineProps({
  objectType: { type: String, required: true },
  recordId: { type: [String, Number], required: true },
  metaConfig: { type: Object, required: true }
})

const childSections = computed(() => {
  return props.metaConfig?.ui_view_config?.child_sections || []
})
</script>
```

### 手动使用 useParentChild

```vue
<template>
  <div class="version-list">
    <div class="toolbar">
      <el-button type="primary" @click="handleCreate">
        新增版本
      </el-button>
    </div>

    <el-table :data="childList" v-loading="childLoading">
      <el-table-column prop="name" label="版本名称" />
      <el-table-column prop="code" label="编码" />
      <el-table-column prop="is_current" label="当前版本" />
      <el-table-column label="操作">
        <template #default="{ row }">
          <el-button @click="handleEdit(row)">编辑</el-button>
          <el-button type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-pagination
      v-model:current-page="pagination.current"
      v-model:page-size="pagination.pageSize"
      :total="pagination.total"
      @current-change="loadChildList"
    />
  </div>
</template>

<script setup>
import { useParentChild } from '@/composables/useParentChild'

const props = defineProps({
  productId: { type: [String, Number], required: true }
})

const {
  childList,
  childLoading,
  childPagination,
  createChild,
  updateChild,
  deleteChild,
  loadChildList
} = useParentChild('product', 'version', {
  parentId: props.productId,
  autoLoadParent: false,
  autoLoadChild: true
})

async function handleCreate() {
  const result = await createChild({
    name: '新版本',
    code: 'V2.0'
  })
  if (result.success) {
    ElMessage.success('创建成功')
  }
}
</script>
```

## 后端 Schema 扩展

后端 `metaService` 需要在返回的 `ui_view_config` 中包含 `child_sections` 配置：

```json
{
  "object_name": "product",
  "ui_view_config": {
    "list": { ... },
    "detail": { ... },
    "child_sections": [
      {
        "child_object": "version",
        "title": "版本列表",
        "display": "expandable",
        "pageSize": 10,
        "columns": [
          { "key": "name", "title": "版本名称", "width": 150 },
          { "key": "code", "title": "编码", "width": 100 },
          { "key": "is_current", "title": "当前版本", "width": 90 },
          { "key": "created_at", "title": "创建时间", "width": 160 }
        ],
        "actions": [
          { "key": "edit", "label": "编辑", "type": "text" },
          { "key": "delete", "label": "删除", "type": "text", "danger": true },
          { "key": "set_current", "label": "设为当前", "type": "primary" }
        ],
        "defaultSort": {
          "field": "created_at",
          "order": "desc"
        }
      }
    ]
  }
}
```

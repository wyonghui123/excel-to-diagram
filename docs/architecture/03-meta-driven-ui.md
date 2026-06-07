# 元数据驱动 UI 模式

> 本文档说明了如何使用元数据驱动的 UI 组件快速构建页面。

---

## 一、核心组件

### 1.1 组件概览

| 组件 | 用途 | 使用场景 |
|------|------|---------|
| **MetaListPage** | 列表页 | 管理页、报表页 |
| **DetailPage** | 详情页 | 编辑、创建、查看 |
| **AssociationPanel** | 关联面板 | 成员管理、角色分配 |
| **DetailSection** | 字段表单 | 自定义表单 |

### 1.2 组件关系

```
MetaListPage
    ├── FilterBar (自动生成)
    ├── MetaTable (自动生成)
    ├── ToolbarActions (自动生成)
    ├── BatchActions (自动生成)
    ├── Pagination (自动生成)
    ├── ExportDialog (自动集成)
    ├── ImportDialog (自动集成)
    └── DetailPage (点击详情/编辑/新建时打开)
            ├── DetailSection (基本信息)
            ├── AssociationPanel (关联管理)
            └── AuditLog (变更历史)
```

---

## 二、MetaListPage 组件

### 2.1 基本用法

```vue
<template>
  <MetaListPage
    object-type="user"
    :options="{
      autoLoad: true,
      pageSize: 20,
      debug: false
    }"
    enable-detail
    enable-auto-crud
    @detail="handleDetail"
  />
</template>

<script setup>
import { MetaListPage } from '@/components/common/MetaListPage'

function handleDetail({ row }) {
  // 自定义详情处理逻辑
}
</script>
```

### 2.2 Props

| Prop | Type | Default | 说明 |
|------|------|---------|------|
| `objectType` | String | 必填 | 对象类型，对应 YAML 的 `id` |
| `options` | Object | `{}` | 配置选项 |
| `enableDetail` | Boolean | `false` | 是否启用详情页 |
| `enableAutoCrud` | Boolean | `false` | 是否启用自动 CRUD |
| `exportOptions` | Object | `{}` | 导出选项 |
| `importOptions` | Object | `{}` | 导入选项 |

### 2.3 Options 配置

```javascript
const options = {
  autoLoad: true,           // 自动加载数据
  pageSize: 20,             // 默认分页大小
  debug: false,              // 调试模式
  filterDisplayMode: 'hover' // 过滤器显示模式
}
```

### 2.4 Events

| Event | Payload | 说明 |
|-------|---------|------|
| `detail` | `{ row }` | 点击详情 |
| `edit` | `{ row }` | 点击编辑 |
| `delete` | `{ row }` | 点击删除 |
| `create` | - | 点击新建 |
| `action` | `{ action, row }` | 通用操作事件 |
| `refresh` | - | 刷新列表 |

---

## 三、DetailPage 组件

### 3.1 基本用法

```vue
<template>
  <DetailPage
    v-model="showDetail"
    :object-type="objectType"
    :object-id="objectId"
    :readonly="readonly"
    :create-mode="createMode"
    @save="handleSave"
    @cancel="handleCancel"
  />
</template>
```

### 3.2 Props

| Prop | Type | Default | 说明 |
|------|------|---------|------|
| `modelValue` | Boolean | `false` | 显示状态 |
| `objectType` | String | 必填 | 对象类型 |
| `objectId` | Number/String | null | 对象 ID（编辑模式） |
| `readonly` | Boolean | `false` | 只读模式 |
| `createMode` | Boolean | `false` | 创建模式 |

### 3.3 Tabs 配置（来自 YAML）

```yaml
detail:
  layout: tabs
  tabs:
    - id: basic
      label: 基本信息
      type: fields
      fields: [code, name, description]
    
    - id: members
      label: 成员
      type: association
      association: members
    
    - id: history
      label: 变更历史
      type: history
```

### 3.4 插槽机制

```vue
<DetailPage v-model="show" :object-type="objectType">
  <!-- 自定义关联面板 -->
  <template #association:members="{ config }">
    <CustomMemberPanel :config="config" />
  </template>
</DetailPage>
```

---

## 四、AssociationPanel 组件

### 4.1 基本用法

```vue
<AssociationPanel
  :object-type="objectType"
  :object-id="objectId"
  :association-name="associationName"
  :config="associationConfig"
  :readonly="false"
  :actions="['assign', 'unassign']"
  @refresh="handleRefresh"
/>
```

### 4.2 Props

| Prop | Type | 说明 |
|------|------|------|
| `objectType` | String | 源对象类型 |
| `objectId` | Number | 源对象 ID |
| `associationName` | String | 关联名称 |
| `config` | Object | 关联配置（来自 YAML） |
| `readonly` | Boolean | 只读模式 |
| `actions` | Array | 支持的操作 |

### 4.3 YAML 配置

```yaml
associations:
  members:
    name: 成员
    target_type: user
    type: many_to_many
    through: user_group_members
    display:
      label: 成员
      target_display_field: display_name
    actions:
      assign:
        name: add_member
        label: 添加成员
      unassign:
        name: remove_member
        label: 移除成员
```

---

## 五、字段权限控制

### 5.1 创建态 vs 编辑态 vs 查看态

| 场景 | password 字段 | business_key 字段 | required 字段 |
|------|--------------|------------------|--------------|
| 创建 | ✅ 显示 | ✅ 显示 | ✅ 显示+必填 |
| 编辑 | ❌ 隐藏 | ❌ 只读 | ✅ 显示 |
| 查看 | ❌ 隐藏 | ✅ 只读 | ✅ 只读 |

### 5.2 DetailSection 配置

```vue
<DetailSection
  :fields="getFieldsForTab('basic')"
  :data="formData"
  :readonly="readonly"
  :editing="editing"
  :is-creating="createMode"
  @field-change="handleFieldChange"
/>
```

---

## 六、自定义插槽

### 6.1 自定义列渲染

```vue
<MetaListPage object-type="user">
  <!-- 自定义名称列 -->
  <template #cell-name="{ row }">
    <div class="user-cell">
      <el-avatar :src="row.avatar">{{ row.name }}</el-avatar>
      <span>{{ row.name }}</span>
    </div>
  </template>

  <!-- 自定义操作列 -->
  <template #cell-actions="{ row }">
    <el-button type="primary" @click="handleCustom(row)">
      自定义操作
    </el-button>
  </template>
</MetaListPage>
```

### 6.2 自定义工具栏

```vue
<MetaListPage object-type="user">
  <template #toolbar-extra>
    <el-button type="success" @click="handleExport">
      导出报表
    </el-button>
  </template>
</MetaListPage>
```

---

## 七、完整示例

### 7.1 用户管理页面

```vue
<template>
  <div class="user-management">
    <MetaListPage
      ref="metaListRef"
      object-type="user"
      :options="{ autoLoad: true, pageSize: 20 }"
      :export-options="{ includeFilters: true }"
      enable-detail
      enable-auto-crud
      @detail="handleDetail"
    >
      <!-- 自定义用户列 -->
      <template #cell-name="{ row }">
        <div class="user-cell">
          <el-avatar size="small" :src="row.avatar">
            {{ row.name?.charAt(0) }}
          </el-avatar>
          <div class="user-info">
            <span class="name">{{ row.name }}</span>
            <span class="username">@{{ row.username }}</span>
          </div>
        </div>
      </template>

      <!-- 状态标签 -->
      <template #cell-status="{ row }">
        <el-tag :type="getStatusType(row.status)">
          {{ getStatusLabel(row.status) }}
        </el-tag>
      </template>
    </MetaListPage>

    <!-- 详情页 -->
    <DetailPage
      v-model="showDetail"
      :object-type="currentObjectType"
      :object-id="currentObjectId"
      :readonly="detailReadonly"
      :create-mode="createMode"
      @save="handleSave"
      @cancel="showDetail = false"
      @refresh="metaListRef?.refresh()"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { MetaListPage, DetailPage } from '@/components/common'

const metaListRef = ref(null)
const showDetail = ref(false)
const detailReadonly = ref(false)
const createMode = ref(false)
const currentObjectType = ref('user')
const currentObjectId = ref(null)

function handleDetail({ row }) {
  currentObjectType.value = 'user'
  currentObjectId.value = row.id
  detailReadonly.value = false
  createMode.value = false
  showDetail.value = true
}

function getStatusType(status) {
  const map = { active: 'success', inactive: 'info', locked: 'danger' }
  return map[status] || 'info'
}

function getStatusLabel(status) {
  const map = { active: '活跃', inactive: '未激活', locked: '已锁定' }
  return map[status] || status
}
</script>
```

---

## 八、变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| 1.0 | 2026-05-12 | 初始版本 |

---
title: UI 组件使用指南
version: 1.0.0
date: 2026-06-07
status: 活跃
audience: 前端开发者
---

## 目录

1. [一、核心原则](#一-核心原则)
2. [二、UI组件规范](#二-ui组件规范)
3. [三、设计令牌速查](#三-设计令牌速查)
4. [四、组件导入指南](#四-组件导入指南)
5. [五、开发检查清单](#五-开发检查清单)
6. [六、相关文档](#六-相关文档)
7. [七、Element Plus 主题定制规范](#七-element-plus-主题定制规范)
8. [八、版本历史](#八-版本历史)

---
# UI组件开发规范

> **版本**: v1.1  
> **基于**: 用友YonDesign设计系统  
> **目的**: 确保所有UI开发默认遵循yonDesign规范

---

## 一、核心原则

### 1.1 必须遵守

1. **使用设计令牌**：所有颜色、间距、字体必须使用CSS变量
2. **复用现有组件**：优先使用项目已有的组件
3. **遵循yonDesign规范**：参考 [YONYOU_DESIGN.md](../src/styles/YONYOU_DESIGN.md)

### 1.2 禁止事项

1. ❌ 禁止硬编码颜色值（如 `color: #333`）
2. ❌ 禁止自定义滚动条样式（使用浏览器默认）
3. ❌ 禁止使用 `alert()` 进行消息通知
4. ❌ 禁止在循环中使用 `index` 作为 `key`

---

## 二、UI组件规范

### 2.1 Tab 导航

#### 规范说明

- **样式**：使用底部指示线，不使用填充背景
- **颜色**：激活状态使用主色，非激活使用次要文本色
- **交互**：hover时文本颜色加深

#### 标准代码模板

```vue
<template>
  <nav class="tabs" role="tablist">
    <button
      v-for="tab in tabs"
      :key="tab.key"
      class="tab"
      :class="{ 'tab--active': activeTab === tab.key }"
      @click="activeTab = tab.key"
      role="tab"
      :aria-selected="activeTab === tab.key"
    >
      {{ tab.label }}
    </button>
  </nav>
</template>

<style scoped>
.tabs {
  display: flex;
  gap: var(--spacing-lg);
  border-bottom: 1px solid var(--color-border);
  padding: 0 var(--spacing-lg);
}

.tab {
  position: relative;
  padding: var(--spacing-md) 0;
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: color var(--transition-normal);
}

.tab:hover {
  color: var(--color-text-primary);
}

.tab--active {
  color: var(--color-primary);
  font-weight: var(--font-weight-semibold);
}

.tab--active::after {
  content: '';
  position: absolute;
  bottom: -1px;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--color-primary);
  border-radius: 2px 2px 0 0;
}
</style>
```

#### 常见错误

```vue
<!-- ❌ 错误：使用 AppButton 作为 Tab -->
<AppButton variant="primary">Tab名称</AppButton>

<!-- ❌ 错误：使用填充背景 -->
.tab--active {
  background: var(--color-primary);
  color: white;
}

<!-- ✅ 正确：使用底部指示线 -->
.tab--active::after {
  content: '';
  height: 2px;
  background: var(--color-primary);
}
```

---

### 2.2 侧边导航

#### 规范说明

- **样式**：使用左侧指示线，不使用背景填充
- **宽度**：固定宽度 200px
- **交互**：hover时文本颜色加深，激活时显示主色指示线

#### 标准代码模板

```vue
<template>
  <aside class="sidebar">
    <nav class="sidebar-nav">
      <button
        v-for="item in menuItems"
        :key="item.key"
        :class="['nav-item', { active: currentMenu === item.key }]"
        @click="currentMenu = item.key"
      >
        <AppIcon :name="item.icon" :size="16" />
        <span>{{ item.label }}</span>
      </button>
    </nav>
  </aside>
</template>

<style scoped>
.sidebar {
  width: 200px;
  border-right: 1px solid var(--color-border);
  padding: var(--spacing-sm) 0;
  background: var(--color-bg-primary);
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-lg);
  cursor: pointer;
  transition: all var(--transition-normal);
  border-left: 2px solid transparent;
  color: var(--color-text-secondary);
  background: transparent;
  border-right: none;
  border-top: none;
  border-bottom: none;
  font-size: var(--font-size-sm);
  width: 100%;
  text-align: left;
}

.nav-item:hover {
  color: var(--color-text-primary);
  background: transparent;
}

.nav-item.active {
  border-left-color: var(--color-primary);
  color: var(--color-primary);
  font-weight: var(--font-weight-medium);
  background: transparent;
}
</style>
```

#### 常见错误

```vue
<!-- ❌ 错误：使用背景填充 -->
.nav-item.active {
  background: var(--color-primary-bg);
  border-left: none;
}

<!-- ❌ 错误：使用边框包裹 -->
.nav-item.active {
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-md);
}

<!-- ✅ 正确：使用左侧指示线 -->
.nav-item.active {
  border-left: 2px solid var(--color-primary);
  color: var(--color-primary);
}
```

---

### 2.3 文本颜色使用

#### 规范说明

| 变量 | 色值 | 用途 | 使用场景 |
|------|------|------|---------|
| `--color-text-primary` | #333333 | 主要文本 | 标题、正文、重要信息 |
| `--color-text-secondary` | #666666 | 次要文本 | 描述、说明、次要信息 |
| `--color-text-tertiary` | #999999 | 辅助文本 | 占位符、禁用状态、注释 |
| `--color-text-disabled` | #cccccc | 禁用文本 | 禁用状态 |

#### 使用原则

1. **表格内容**：使用 `--color-text-primary`
2. **表格表头**：使用 `--color-text-secondary`
3. **辅助说明**：使用 `--color-text-tertiary`
4. **禁用状态**：使用 `--color-text-disabled`

#### 常见错误

```scss
// ❌ 错误：表格内容使用 tertiary 颜色
.data-table td {
  color: var(--color-text-tertiary);  // 对比度不足，可能产生删除线视觉效果
}

// ✅ 正确：表格内容使用 primary 颜色
.data-table td {
  color: var(--color-text-primary);
}

// ✅ 正确：表格表头使用 secondary 颜色
.data-table th {
  color: var(--color-text-secondary);
  font-weight: var(--font-weight-medium);
}
```

---

### 2.4 滚动条

#### 规范说明

- **默认**：使用浏览器原生滚动条
- **隐藏**：如需隐藏滚动条，使用 `@include hide-scrollbar` mixin
- **禁止**：全局自定义滚动条样式

#### 标准做法

```scss
// ✅ 正确：使用浏览器默认滚动条
.content {
  overflow-y: auto;
}

// ✅ 正确：如需隐藏滚动条
@import '@/styles/mixins.scss';

.content {
  overflow-y: auto;
  @include hide-scrollbar;
}
```

#### 常见错误

```scss
// ❌ 错误：全局自定义滚动条
::-webkit-scrollbar {
  width: 8px;
}

::-webkit-scrollbar-thumb {
  background: var(--color-primary);
  border-radius: 4px;
}

// ❌ 错误：在 mixins.scss 中定义全局滚动条样式
@mixin scrollbar {
  &::-webkit-scrollbar {
    width: 6px;
  }
}
```

---

### 2.5 消息通知

#### 规范说明

- **必须**：使用 `useMessage()` composable
- **禁止**：使用 `alert()`、`confirm()`

#### 标准代码模板

```vue
<script setup>
import { useMessage } from '@/composables/useMessage'

const message = useMessage()

async function handleSave() {
  try {
    await saveData()
    message.success('保存成功')
  } catch (error) {
    message.error(`保存失败: ${error.message}`)
  }
}

async function handleDelete() {
  const confirmed = await message.confirm({
    title: '确认删除',
    message: '删除后无法恢复，确定要删除吗？',
    type: 'danger'
  })
  
  if (confirmed) {
    await deleteData()
    message.success('删除成功')
  }
}
</script>
```

---

### 2.6 表格

#### 规范说明

- **表头**：使用 `--color-text-secondary`，中等字重
- **表格内容**：使用 `--color-text-primary`
- **边框**：使用 `--color-border`
- **斑马纹**：偶数行使用 `--color-bg-secondary`

#### 标准代码模板

```vue
<template>
  <table class="data-table">
    <thead>
      <tr>
        <th>列标题</th>
      </tr>
    </thead>
    <tbody>
      <tr v-for="item in items" :key="item.id">
        <td>{{ item.value }}</td>
      </tr>
    </tbody>
  </table>
</template>

<style scoped>
.data-table {
  width: 100%;
  border-collapse: collapse;
}

.data-table th {
  padding: var(--spacing-sm) var(--spacing-md);
  text-align: left;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-secondary);
  background: var(--color-bg-secondary);
  border-bottom: 1px solid var(--color-border);
}

.data-table td {
  padding: var(--spacing-sm) var(--spacing-md);
  font-size: var(--font-size-sm);
  color: var(--color-text-primary);
  border-bottom: 1px solid var(--color-border-light);
}

.data-table tbody tr:nth-child(even) {
  background: var(--color-bg-secondary);
}

.data-table tbody tr:hover {
  background: var(--color-bg-tertiary);
}
</style>
```

---

### 2.7 状态徽章

#### 规范说明

- **成功**：绿色背景 + 绿色文字
- **警告**：橙色背景 + 橙色文字
- **错误**：红色背景 + 红色文字
- **信息**：蓝色背景 + 蓝色文字

#### 标准代码模板

```vue
<template>
  <span class="status-badge" :class="`status-badge--${status}`">
    {{ label }}
  </span>
</template>

<style scoped>
.status-badge {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: var(--font-size-xs);
  font-weight: var(--font-weight-medium);
  border-radius: var(--radius-sm);
}

.status-badge--success {
  background: var(--color-success-bg, #dcfce7);
  color: var(--color-success, #16a34a);
}

.status-badge--warning {
  background: var(--color-warning-bg, #fef3c7);
  color: var(--color-warning, #d97706);
}

.status-badge--error {
  background: var(--color-danger-bg, #fee2e2);
  color: var(--color-danger, #dc2626);
}

.status-badge--info {
  background: var(--color-info-bg, #dbeafe);
  color: var(--color-info, #2563eb);
}
</style>
```

---

### 2.8 MasterDetailLayout 主从布局

#### 规范说明

- **用途**：用于创建主从结构的页面布局，左侧为主列表，右侧为详情面板
- **特性**：支持侧边栏折叠、宽度拖拽调整、响应式布局
- **交互**：hover时显示折叠按钮，拖拽时显示调整指示器

#### 标准代码模板

```vue
<template>
  <MasterDetailLayout
    v-model:sidebarCollapsed="isCollapsed"
    :sidebar-width="280"
    :sidebar-collapsible="true"
    :min-width="200"
    :max-width="500"
    @collapse-change="handleCollapseChange"
  >
    <template #master>
      <div class="master-list">
        <div v-for="item in items" :key="item.id" class="list-item">
          {{ item.name }}
        </div>
      </div>
    </template>

    <template #detail>
      <div class="detail-panel">
        <h2>{{ selectedItem?.name }}</h2>
        <p>{{ selectedItem?.description }}</p>
      </div>
    </template>

    <template #empty>
      <EmptyState type="select" title="请选择一项查看详情" />
    </template>
  </MasterDetailLayout>
</template>

<script setup>
import { ref } from 'vue'
import { MasterDetailLayout, EmptyState } from '@/components/common'

const isCollapsed = ref(false)

function handleCollapseChange(collapsed) {
  console.log('侧边栏折叠状态:', collapsed)
}
</script>
```

#### Props 说明

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `sidebarWidth` | String | '280px' | 侧边栏初始宽度 |
| `sidebarCollapsible` | Boolean | false | 是否可折叠 |
| `sidebarCollapsed` | Boolean | false | 折叠状态（支持 v-model） |
| `showBorder` | Boolean | true | 是否显示拖拽边框 |
| `minWidth` | Number | 200 | 最小宽度 |
| `maxWidth` | Number | 500 | 最大宽度 |

#### 常见错误

```vue
<!-- ❌ 错误：不使用具名插槽 -->
<MasterDetailLayout>
  <div>主列表内容</div>
  <div>详情内容</div>
</MasterDetailLayout>

<!-- ✅ 正确：使用具名插槽 -->
<MasterDetailLayout>
  <template #master>主列表内容</template>
  <template #detail>详情内容</template>
</MasterDetailLayout>
```

---

### 2.9 Pagination 分页

#### 规范说明

- **用途**：数据列表的分页导航
- **特性**：支持页码切换、每页条数选择、快速跳转
- **交互**：hover时边框变为主色，当前页码高亮显示

#### 标准代码模板

```vue
<template>
  <Pagination
    v-model:current="currentPage"
    v-model:pageSize="pageSize"
    :total="total"
    :show-size-changer="true"
    :show-quick-jumper="true"
    :page-size-options="[10, 20, 50, 100]"
    :show-total="true"
    @change="handlePageChange"
    @page-size-change="handlePageSizeChange"
  />
</template>

<script setup>
import { ref } from 'vue'
import { Pagination } from '@/components/common'

const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(100)

function handlePageChange(page) {
  console.log('切换到第', page, '页')
}

function handlePageSizeChange(size) {
  console.log('每页显示', size, '条')
}
</script>
```

#### Props 说明

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `current` | Number | 1 | 当前页码（支持 v-model） |
| `total` | Number | 0 | 数据总条数 |
| `pageSize` | Number | 10 | 每页条数（支持 v-model） |
| `showSizeChanger` | Boolean | true | 是否显示每页条数选择器 |
| `showQuickJumper` | Boolean | false | 是否显示快速跳转 |
| `pageSizeOptions` | Array | [10, 20, 50, 100] | 每页条数选项 |
| `showTotal` | Boolean | true | 是否显示总条数 |

---

### 2.10 Drawer 抽屉

#### 规范说明

- **用途**：从屏幕边缘滑出的浮层面板，用于展示详情或表单
- **特性**：支持左右方向、自定义宽度、遮罩层控制
- **交互**：ESC键关闭、点击遮罩关闭（可配置）

#### 标准代码模板

```vue
<template>
  <button @click="visible = true">打开抽屉</button>

  <Drawer
    v-model="visible"
    title="详情信息"
    width="600px"
    placement="right"
    :closable="true"
    :mask="true"
    :mask-closable="true"
    :keyboard="true"
    @open="handleOpen"
    @close="handleClose"
  >
    <div class="drawer-content">
      <p>抽屉内容</p>
    </div>

    <template #footer>
      <AppButton variant="secondary" @click="visible = false">取消</AppButton>
      <AppButton variant="primary" @click="handleConfirm">确定</AppButton>
    </template>
  </Drawer>
</template>

<script setup>
import { ref } from 'vue'
import { Drawer, AppButton } from '@/components/common'

const visible = ref(false)

function handleOpen() {
  console.log('抽屉打开')
}

function handleClose() {
  console.log('抽屉关闭')
}

function handleConfirm() {
  console.log('确认操作')
  visible.value = false
}
</script>
```

#### Props 说明

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `modelValue` | Boolean | false | 是否显示（支持 v-model） |
| `title` | String | '' | 标题 |
| `width` | String/Number | '600px' | 宽度 |
| `placement` | String | 'right' | 方向（left/right） |
| `closable` | Boolean | true | 是否显示关闭按钮 |
| `mask` | Boolean | true | 是否显示遮罩 |
| `maskClosable` | Boolean | true | 点击遮罩是否关闭 |
| `keyboard` | Boolean | true | 是否支持 ESC 键关闭 |

---

### 2.11 MetaTable 高级表格

#### 规范说明

- **用途**：基于元数据配置的高级表格组件
- **特性**：支持搜索、排序、多选、分页、自定义列渲染
- **交互**：点击表头排序，复选框选择行

#### 多选功能

```vue
<template>
  <MetaTable
    :columns="columns"
    :data="tableData"
    :selectable="true"
    :selected-keys="selectedKeys"
    :row-key="'id'"
    @selection-change="handleSelectionChange"
  />
</template>

<script setup>
import { ref } from 'vue'
import { MetaTable } from '@/components/common'

const columns = [
  { key: 'name', label: '名称' },
  { key: 'status', label: '状态', type: 'status' }
]

const tableData = ref([
  { id: 1, name: '项目A', status: 'active' },
  { id: 2, name: '项目B', status: 'inactive' }
])

const selectedKeys = ref([])

function handleSelectionChange(selectedRows) {
  console.log('已选择:', selectedRows)
}
</script>
```

#### 分页功能

```vue
<template>
  <MetaTable
    :columns="columns"
    :data="tableData"
    :pagination="{
      current: currentPage,
      pageSize: pageSize,
      total: total,
      showSizeChanger: true,
      showQuickJumper: true
    }"
    @page-change="handlePageChange"
    @page-size-change="handlePageSizeChange"
  />
</template>

<script setup>
import { ref } from 'vue'
import { MetaTable } from '@/components/common'

const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(100)

function handlePageChange(page) {
  currentPage.value = page
  fetchData()
}

function handlePageSizeChange(size) {
  pageSize.value = size
  fetchData()
}
</script>
```

---

### 2.12 MetaForm 高级表单

#### 规范说明

- **用途**：基于元数据配置的高级表单组件
- **特性**：支持多种字段类型、表单验证、条件显示、字段联动

#### 条件显示功能

```vue
<template>
  <MetaForm
    :fields="fields"
    v-model="formData"
    :field-visibility="fieldVisibility"
  />
</template>

<script setup>
import { ref } from 'vue'
import { MetaForm } from '@/components/common'

const formData = ref({
  userType: '',
  companyName: ''
})

const fields = [
  { key: 'userType', label: '用户类型', type: 'select', options: [
    { value: 'personal', label: '个人' },
    { value: 'enterprise', label: '企业' }
  ]},
  { key: 'companyName', label: '公司名称', type: 'text', required: true }
]

const fieldVisibility = {
  companyName: (formData) => formData.userType === 'enterprise'
}
</script>
```

#### 字段联动功能

```vue
<template>
  <MetaForm
    :fields="fields"
    v-model="formData"
    :field-dependencies="fieldDependencies"
  />
</template>

<script setup>
import { ref } from 'vue'
import { MetaForm } from '@/components/common'

const formData = ref({
  province: '',
  city: ''
})

const fields = [
  { key: 'province', label: '省份', type: 'select', options: provinceOptions },
  { key: 'city', label: '城市', type: 'select', options: [] }
]

const fieldDependencies = {
  province: {
    onChange: (value, formData, context) => {
      context.setFieldValue('city', '')
      const cities = getCityOptionsByProvince(value)
      const cityField = fields.find(f => f.key === 'city')
      if (cityField) {
        cityField.options = cities
      }
    }
  }
}
</script>
```

---

### 2.13 AppSelect 选择器

#### 规范说明

- **用途**：下拉选择器组件
- **特性**：支持单选/多选、搜索、选项分组、键盘导航

#### 选项分组功能

```vue
<template>
  <AppSelect
    v-model="selectedCity"
    :options="groupedOptions"
    placeholder="请选择城市"
    searchable
  />
</template>

<script setup>
import { ref } from 'vue'
import { AppSelect } from '@/components/common'

const selectedCity = ref('')

const groupedOptions = [
  {
    label: '一线城市',
    options: [
      { value: 'beijing', label: '北京' },
      { value: 'shanghai', label: '上海' },
      { value: 'guangzhou', label: '广州' },
      { value: 'shenzhen', label: '深圳' }
    ]
  },
  {
    label: '二线城市',
    options: [
      { value: 'hangzhou', label: '杭州' },
      { value: 'nanjing', label: '南京' },
      { value: 'chengdu', label: '成都' }
    ]
  }
]
</script>
```

---

### 2.14 AppTabs 标签页

#### 规范说明

- **用途**：标签页导航组件
- **特性**：支持图标、徽章、溢出处理（下拉/滚动）

#### 溢出处理功能

```vue
<template>
  <AppTabs
    v-model="activeTab"
    :tabs="tabs"
    overflow-mode="dropdown"
  />
</template>

<script setup>
import { ref } from 'vue'
import { AppTabs } from '@/components/common'

const activeTab = ref('tab1')

const tabs = [
  { key: 'tab1', label: '标签一', icon: 'home' },
  { key: 'tab2', label: '标签二', icon: 'user', badge: '3' },
  { key: 'tab3', label: '标签三' },
  { key: 'tab4', label: '标签四' },
  { key: 'tab5', label: '标签五' },
  { key: 'tab6', label: '标签六' },
  { key: 'tab7', label: '标签七' }
]
</script>
```

#### 溢出模式说明

| 模式 | 说明 |
|------|------|
| `dropdown` | 超出部分收起到"更多"下拉菜单中 |
| `scroll` | 显示左右滚动按钮 |

---

### 2.15 AppSideNav 侧边导航

#### 规范说明

- **用途**：侧边栏导航组件
- **特性**：支持图标、徽章、折叠功能

#### 折叠功能

```vue
<template>
  <AppSideNav
    v-model="activeMenu"
    v-model:collapsed="isCollapsed"
    :items="menuItems"
    :collapsible="true"
    :width="200"
    collapsed-width="64px"
    @collapse-change="handleCollapseChange"
  />
</template>

<script setup>
import { ref } from 'vue'
import { AppSideNav } from '@/components/common'

const activeMenu = ref('home')
const isCollapsed = ref(false)

const menuItems = [
  { key: 'home', label: '首页', icon: 'home' },
  { key: 'users', label: '用户管理', icon: 'user', badge: '5' },
  { key: 'settings', label: '系统设置', icon: 'settings' }
]

function handleCollapseChange(collapsed) {
  console.log('导航折叠状态:', collapsed)
}
</script>
```

---

### 2.16 AppInput 输入框

#### 规范说明

- **用途**：文本输入框组件
- **特性**：支持多种尺寸、前缀/后缀图标、清空按钮、密码显示切换

#### 密码显示切换功能

```vue
<template>
  <AppInput
    v-model="password"
    type="password"
    label="密码"
    placeholder="请输入密码"
    :show-password-toggle="true"
    clearable
  />
</template>

<script setup>
import { ref } from 'vue'
import { AppInput } from '@/components/common'

const password = ref('')
</script>
```

#### Props 说明

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `type` | String | 'text' | 输入类型（text/password/number等） |
| `showPasswordToggle` | Boolean | true | 是否显示密码切换按钮（仅password类型） |
| `clearable` | Boolean | false | 是否可清空 |
| `prefixIcon` | Component | null | 前缀图标 |
| `suffixIcon` | Component | null | 后缀图标 |

---

## 三、设计令牌速查

### 3.1 颜色

```scss
// 主色调
--color-primary: #ea580c;           // 主色
--color-primary-hover: #f97316;     // 悬停
--color-primary-active: #c2410c;    // 激活

// 语义色
--color-success: #52c41a;
--color-warning: #faad14;
--color-error: #ff4d4f;

// 文本
--color-text-primary: #333333;      // 主要文本
--color-text-secondary: #666666;    // 次要文本
--color-text-tertiary: #999999;     // 辅助文本（占位符、禁用）
--color-text-disabled: #cccccc;     // 禁用文本

// 背景
--color-bg-primary: #ffffff;
--color-bg-secondary: #f5f7fa;
--color-bg-tertiary: #f0f0f0;

// 边框
--color-border: #e8e8e8;
--color-border-light: #f0f0f0;
```

### 3.2 间距

```scss
--spacing-xs: 4px;
--spacing-sm: 8px;
--spacing-md: 16px;
--spacing-lg: 24px;
--spacing-xl: 32px;
--spacing-xxl: 48px;
```

### 3.3 字体

```scss
--font-size-xs: 12px;
--font-size-sm: 13px;
--font-size-md: 14px;
--font-size-lg: 16px;
--font-size-xl: 18px;

--font-weight-normal: 400;
--font-weight-medium: 500;
--font-weight-semibold: 600;
```

### 3.4 圆角

```scss
--radius-sm: 4px;
--radius-md: 8px;
--radius-lg: 12px;
--radius-xl: 16px;
--radius-full: 9999px;          // 全圆角
--radius-input: 6px;           // 输入框圆角
```

### 3.5 阴影

```scss
--shadow-sm: 0 2px 8px rgba(0, 0, 0, 0.06);    // 小阴影
--shadow-md: 0 4px 12px rgba(0, 0, 0, 0.1);    // 中等阴影
--shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.15);   // 大阴影
--shadow-focus: 0 0 0 2px var(--color-primary-bg);  // 聚焦阴影
```

### 3.6 过渡

```scss
--transition-fast: 0.15s ease;    // 快速过渡
--transition-normal: 0.2s ease;   // 标准过渡
--transition-slow: 0.3s ease;     // 慢速过渡
```

### 3.7 行高

```scss
--line-height-tight: 1.25;      // 紧凑行高
--line-height-normal: 1.5;      // 标准行高
--line-height-relaxed: 1.75;    // 宽松行高
```

### 3.8 输入框高度

```scss
--input-height-sm: 28px;        // 小尺寸输入框
--input-height-md: 36px;        // 中等尺寸输入框
--input-height-lg: 44px;        // 大尺寸输入框
```

### 3.9 Z-Index 层级

```scss
--z-index-dropdown: 1000;       // 下拉菜单
--z-index-modal: 1050;          // 模态框/抽屉
--z-index-tooltip: 1100;        // 提示框
```

### 3.10 边框

```scss
--border-width-thin: 1px;       // 细边框
--border-width-medium: 2px;     // 中等边框
```

---

## 四、组件导入指南

### 4.1 统一导入

```javascript
import {
  AppButton,
  AppInput,
  AppSelect,
  AppTabs,
  AppSideNav,
  AppCard,
  AppModal,
  MasterDetailLayout,
  Pagination,
  Drawer,
  MetaTable,
  MetaForm,
  EmptyState,
  ConfirmDialog,
  EnumSelect,
  AuditLog
} from '@/components/common'
```

### 4.2 单独导入

```javascript
import { AppButton } from '@/components/common/AppButton'
import { AppInput } from '@/components/common/AppInput'
import { MasterDetailLayout } from '@/components/common/MasterDetailLayout'
import { Pagination } from '@/components/common/Pagination'
import { Drawer } from '@/components/common/Drawer'
```

### 4.3 可用组件列表

| 组件 | 说明 | 导入路径 |
|------|------|---------|
| `AppButton` | 按钮 | `@/components/common/AppButton` |
| `AppInput` | 输入框 | `@/components/common/AppInput` |
| `AppSelect` | 选择器 | `@/components/common/AppSelect` |
| `AppTabs` | 标签页 | `@/components/common/AppTabs` |
| `AppSideNav` | 侧边导航 | `@/components/common/AppSideNav` |
| `AppCard` | 卡片 | `@/components/common/AppCard` |
| `AppModal` | 模态框 | `@/components/common/AppModal` |
| `MasterDetailLayout` | 主从布局 | `@/components/common/MasterDetailLayout` |
| `Pagination` | 分页 | `@/components/common/Pagination` |
| `Drawer` | 抽屉 | `@/components/common/Drawer` |
| `MetaTable` | 高级表格 | `@/components/common/MetaTable` |
| `MetaForm` | 高级表单 | `@/components/common/MetaForm` |
| `EmptyState` | 空状态 | `@/components/common/EmptyState` |
| `ConfirmDialog` | 确认对话框 | `@/components/common/ConfirmDialog` |
| `EnumSelect` | 枚举选择器 | `@/components/common/EnumSelect` |
| `AuditLog` | 审计日志 | `@/components/common/AuditLog` |

---

## 五、开发检查清单

在开发UI组件时，请逐项检查：

### 5.1 开发前

- [ ] 是否查阅了本文档？
- [ ] 是否查阅了 [YONYOU_DESIGN.md](../src/styles/YONYOU_DESIGN.md)？
- [ ] 是否有现有组件可以复用？

### 5.2 开发中

- [ ] 是否使用了设计令牌（CSS变量）？
- [ ] 是否遵循了组件规范？
- [ ] 是否使用了 `useMessage()` 进行消息通知？
- [ ] 是否避免了硬编码颜色值？

### 5.3 开发后

- [ ] 是否进行了视觉检查？
- [ ] 是否进行了响应式测试？
- [ ] 是否进行了可访问性测试？

---

## 六、相关文档

| 文档 | 说明 |
|------|------|
| [YONYOU_DESIGN.md](../src/styles/YONYOU_DESIGN.md) | yonDesign设计系统规范 |
| [variables.scss](../src/styles/variables.scss) | CSS变量定义 |
| [mixins.scss](../src/styles/mixins.scss) | SCSS mixins |
| [design-principles.md](../.trae/context/pm/design-principles.md) | 交互设计原则 |

---

## 七、Element Plus 主题定制规范

### 7.1 问题背景

在使用 Element Plus 时，由于其 CSS 变量注入机制复杂，容易出现主题色被覆盖的问题。常见问题包括：

1. **unplugin-vue-components 自动导入覆盖**：按需导入组件时，会重新注入 Element Plus 默认 CSS 变量
2. **样式加载顺序问题**：多个样式表定义相同的 CSS 变量，后者覆盖前者
3. **硬编码颜色值**：组件中直接使用 Element Plus 默认颜色 `#409eff`

### 7.2 样式文件架构

```
src/styles/
├── tokens-yonyou.scss          # 设计令牌（颜色、间距等）
├── variables.scss              # 应用级变量
├── element-variables.scss      # Element Plus 变量映射（仅变量定义）
├── element-plus-overrides.css  # 强制覆盖（使用 !important）
└── index.scss                  # 样式入口
```

### 7.3 样式加载顺序

```javascript
// main.js 中的加载顺序（重要！）
import 'element-plus/theme-chalk/index.css'     // 1. Element Plus 默认样式
import './styles/tokens-yonyou.scss'             // 2. 设计令牌
import './styles/variables.scss'                 // 3. 应用变量
import './styles/element-variables.scss'         // 4. EP 变量映射
import './styles/element-plus-overrides.css'     // 5. 强制覆盖（最后加载）
```

### 7.4 CSS 变量强制覆盖

由于 `unplugin-vue-components` 会在运行时注入组件样式，需要在 `element-plus-overrides.css` 中使用更高特异性的选择器：

```css
/* 使用更高特异性 + !important 确保覆盖 */
:root:root,
html:root,
html :root {
  --el-color-primary: #ea580c !important;
  --el-color-primary-light-3: #fb923c !important;
  --el-color-primary-light-5: #fdba74 !important;
  --el-color-primary-light-7: #fed7aa !important;
  --el-color-primary-light-8: #ffedd5 !important;
  --el-color-primary-light-9: #fff7ed !important;
  --el-color-primary-dark-2: #c2410c !important;
}
```

### 7.5 禁止事项

```scss
// ❌ 禁止硬编码 Element Plus 默认颜色
.filter-icon:hover {
  color: #409eff;  // 错误！这是 Element Plus 默认蓝色
}

// ✅ 正确：使用 CSS 变量
.filter-icon:hover {
  color: var(--el-color-primary, #ea580c);
}

// ❌ 禁止在悬停时改变排序图标颜色
.el-table .caret-wrapper:hover .sort-caret {
  border-color: #ea580c !important;  // 会导致排序图标悬停变色
}

// ✅ 正确：只在激活状态改变颜色
.el-table th.ascending .sort-caret.ascending {
  border-bottom-color: #ea580c !important;
}
```

### 7.6 表格排序样式规范

```scss
/* 表头背景 - 保持浅灰色，悬停不变色 */
.el-table th.el-table__cell,
.el-table th.el-table__cell:hover {
  background-color: #fafafa !important;
}

/* 排序图标容器 - 背景透明 */
.el-table .caret-wrapper,
.el-table .caret-wrapper:hover {
  background: transparent !important;
}

/* 排序箭头 - 仅在激活状态显示主色 */
.el-table th.ascending .sort-caret.ascending {
  border-bottom-color: var(--el-color-primary) !important;
}

.el-table th.descending .sort-caret.descending {
  border-top-color: var(--el-color-primary) !important;
}
```

### 7.7 调试方法

使用 Playwright 或浏览器开发者工具检查 CSS 变量实际值：

```javascript
// 检查 --el-color-primary 是否正确
const style = getComputedStyle(document.documentElement);
console.log(style.getPropertyValue('--el-color-primary'));
// 预期输出: #ea580c（不是 #409eff）
```

### 7.8 常见问题排查清单

- [ ] 检查 `--el-color-primary` 是否为 `#ea580c`
- [ ] 检查样式加载顺序是否正确
- [ ] 检查是否有组件硬编码了 `#409eff`
- [ ] 检查 `element-plus-overrides.css` 是否在最后加载
- [ ] 检查是否有悬停样式导致颜色变化

---

## 八、版本历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| v1.2 | 2026-05-10 | 新增 Element Plus 主题定制规范，包含 CSS 变量覆盖、样式加载顺序、表格排序样式规范、调试方法等 |
| v1.1 | 2026-05-07 | 新增 MasterDetailLayout、Pagination、Drawer 组件指南；新增 MetaTable 多选/分页、MetaForm 条件显示/字段联动、AppSelect 选项分组、AppTabs 溢出处理、AppSideNav 折叠、AppInput 密码切换功能指南；更新设计令牌速查表；新增组件导入指南 |
| v1.0 | 2026-05-07 | 初始版本，包含Tab、Nav、文本颜色、滚动条、消息通知、表格、状态徽章规范 |

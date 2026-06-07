# 标准组件库完整使用示例

> **版本**: v1.0.0
> **更新日期**: 2026-05-19
> **适用范围**: 所有前端开发人员和 AI 智能体

---

## 📋 目录

1. [快速开始](#1-快速开始)
2. [顶部导航系统](#2-顶部导航系统)
3. [基础UI组件](#3-基础ui组件)
4. [业务页面组件](#4-业务页面组件)
5. [数据管理组件](#5-数据管理组件)
6. [对话框与交互组件](#6-对话框与交互组件)
7. [完整页面示例](#7-完整页面示例)
8. [常见问题FAQ](#8-常见问题faq)

---

## 1. 快速开始

### 1.1 安装依赖

```bash
# 项目已预装 Element Plus
npm install element-plus @element-plus/icons-vue
```

### 1.2 全局导入（main.js）

```javascript
// src/main.js
import { createApp } from 'vue'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'

// 导入 YonDesign 主题
import './styles/yon-ep.scss'

const app = createApp(App)

// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(ElementPlus)
app.mount('#app')
```

### 1.3 组件导入方式

```vue
<script setup>
// 方式1: 按需导入（推荐）
import { AppShell, AppTabs, UserMenu } from '@/components/common'

// 方式2: 从 index.js 导入所有
import { AppButton, AppInput, AppSelect } from '@/components/common'

// 方式3: 单独导入
import AppShell from '@/components/common/AppShell/AppShell.vue'
</script>
```

---

## 2. 顶部导航系统

### 2.1 最小化应用（仅Header）

**适用场景**: 简单的管理后台，不需要多Tab和侧边栏

```vue
<!-- src/views/SimpleLayout.vue -->
<template>
  <AppShell :show-sidebar="false">
    <template #header-left>
      <h1 class="app-title">元数据管理系统</h1>
    </template>

    <template #header-right>
      <GlobalSearch placeholder="搜索..." @search="handleSearch" />
      <UserMenu :user="currentUser" @command="handleUserAction" />
    </template>

    <!-- 主内容区 -->
    <div class="page-wrapper">
      <PageHeader title="用户管理" :show-back="true" @back="$router.back()" />
      <MetaListPage object-type="user" />
    </div>
  </AppShell>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { AppShell, GlobalSearch, UserMenu, PageHeader } from '@/components/common'
import { MetaListPage } from '@/components/common/MetaListPage'

const router = useRouter()
const currentUser = ref({ name: 'Admin', role: '管理员' })

function handleSearch(keyword) {
  console.log('搜索:', keyword)
}

function handleUserAction(command) {
  if (command === 'logout') {
    router.push('/login')
  }
}
</script>

<style scoped>
.app-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: var(--yonyou-orange-600);
}
.page-wrapper {
  padding: var(--spacing-md);
}
</style>
```

### 2.2 完整企业级应用布局

**适用场景**: 大型管理系统，需要多Tab、侧边栏、面包屑导航

```vue
<!-- src/layouts/EnterpriseLayout.vue -->
<template>
  <AppShell
    :show-tabs="true"
    :show-sidebar="true"
    :sidebar-width="sidebarWidth"
    :sidebar-collapsible="true"
  >
    <!-- Header Left: Logo + 应用名称 -->
    <template #header-left>
      <div class="brand">
        <el-icon :size="24" color="#ea580c"><Monitor /></el-icon>
        <span class="brand__text">ArchData Platform</span>
      </div>
    </template>

    <!-- Header Center: 面包屑 + 全局搜索 -->
    <template #header-center>
      <div class="nav-center">
        <BreadcrumbNav :items="breadcrumbs" separator="/" />
        <GlobalSearch
          placeholder="搜索功能、用户、设置..."
          :recent-searches="recentSearches"
          :suggestions="searchSuggestions"
          @search="onSearch"
        />
      </div>
    </template>

    <!-- Header Right: 通知 + 用户菜单 -->
    <template #header-right>
      <el-tooltip content="通知">
        <el-badge :value="unreadCount" :max="99" :hidden="unreadCount === 0">
          <el-button :icon="Bell" circle size="small" />
        </el-badge>
      </el-tooltip>

      <UserMenu
        :user="userInfo"
        :show-name="true"
        :menu-items="userActions"
        @command="onUserCommand"
      />
    </template>

    <!-- Tabs Bar: 多页面管理 -->
    <template #tabs>
      <AppTabs
        v-model="activeTab"
        :tabs="openPages"
        :max-tabs="10"
        @tab-click="switchPage"
        @tab-close="closePage"
      />
    </template>

    <!-- Sidebar: 导航菜单 -->
    <template #sidebar>
      <AppSideNav
        :menus="navigationMenus"
        :default-active="currentRoute"
        :collapsed="isCollapsed"
        @select="onNavSelect"
      />
    </template>

    <!-- Main Content: 路由视图 -->
    <router-view v-slot="{ Component, route }">
      <transition name="slide-fade" mode="out-in">
        <component :is="Component" :key="route.path" />
      </transition>
    </router-view>
  </AppShell>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, Monitor } from '@element-plus/icons-vue'
import {
  AppShell, AppTabs, BreadcrumbNav, GlobalSearch,
  UserMenu, AppSideNav
} from '@/components/common'

const route = useRoute()
const router = useRouter()

// ====== 状态管理 ======
const activeTab = ref(route.name)
const sidebarWidth = ref(260)
const isCollapsed = ref(false)
const unreadCount = ref(5)
const userInfo = ref({
  name: '张三',
  email: 'zhangsan@company.com',
  avatar: '',
  role: '系统管理员'
})

// 面包屑数据
const breadcrumbs = computed(() => [
  { label: '首页', to: '/' },
  ...route.matched
    .filter(r => r.meta?.title && r.path !== '/')
    .map(r => ({
      label: r.meta.title,
      to: r.path !== route.path ? r.path : undefined
    }))
])

// 最近搜索
const recentSearches = ref(['用户管理', '角色配置', '审计日志'])

// 搜索建议（实际应从后端获取）
const searchSuggestions = ref([
  { id: 1, title: '用户管理', subtitle: '系统管理 > 用户', type: 'page' },
  { id: 2, title: '张三', subtitle: '管理员', type: 'user' },
  { id: 3, title: '全局设置', subtitle: '配置中心', type: 'setting' }
])

// 打开的页面列表
const openPages = ref([
  { id: 'dashboard', label: '仪表盘', icon: 'Odometer', pinned: true },
  // 动态添加...
])

// 用户菜单项
const userActions = ref([
  { key: 'profile', label: '个人信息', icon: 'User' },
  { key: 'preferences', label: '偏好设置', icon: 'Setting', divided: true },
  { key: 'logout', label: '退出登录', icon: 'SwitchButton', danger: true }
])

// 侧边栏菜单
const navigationMenus = ref([
  {
    title: '主菜单',
    items: [
      { index: '/dashboard', title: '仪表盘', icon: 'Odometer' },
      { index: '/system/users', title: '用户管理', icon: 'User' },
      { index: '/system/roles', title: '角色管理', icon: 'UserFilled' },
      { index: '/architecture/data', title: '架构数据', icon: 'Coin' }
    ]
  },
  {
    title: '系统工具',
    items: [
      { index: '/audit/log', title: '审计日志', icon: 'Document' },
      { index: '/system/settings', title: '系统设置', icon: 'Setting' }
    ]
  }
])

const currentRoute = computed(() => route.path)

// ====== 方法 ======

function onSearch(keyword) {
  router.push({ path: '/search', query: { q: keyword } })
}

function switchPage(tab) {
  if (route.name !== tab.id) {
    router.push({ name: tab.id })
  }
}

function closePage(tabId) {
  const idx = openPages.value.findIndex(t => t.id === tabId)
  if (idx > -1 && !openPages.value[idx].pinned) {
    openPages.value.splice(idx, 1)
    // 如果关闭的是当前页，切换到前一个
    if (activeTab.value === tabId && openPages.value.length > 0) {
      const newTab = openPages.value[Math.max(0, idx - 1)]
      activeTab.value = newTab.id
      router.push({ name: newTab.id })
    }
  }
}

function onUserCommand(command) {
  console.log('用户操作:', command)
  if (command === 'logout') {
    // 执行登出
  }
}

function onNavSelect(index) {
  router.push(index)
}

// 监听路由变化，自动添加到 Tabs
watch(() => route.name, (newName) => {
  if (newName && !openPages.value.find(t => t.id === newName)) {
    openPages.value.push({
      id: newName,
      label: route.meta?.title || newName,
      closable: true
    })
  }
  activeTab.value = newName
})
</script>

<style scoped>
.brand {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  font-size: 16px;
  color: var(--yonyou-orange-600);
}

.nav-center {
  display: flex;
  align-items: center;
  gap: 16px;
  flex: 1;
  justify-content: center;
  max-width: 600px;
}

/* 页面切换动画 */
.slide-fade-enter-active,
.slide-fade-leave-active {
  transition: all 0.3s ease;
}

.slide-fade-enter-from {
  opacity: 0;
  transform: translateX(20px);
}

.slide-fade-leave-to {
  opacity: 0;
  transform: translateX(-20px);
}
</style>
```

---

## 3. 基础UI组件

### 3.1 表单控件组合

```vue
<template>
  <AppCard title="基础信息">
    <el-form :model="form" label-width="100px">
      <el-row :gutter="20">
        <el-col :span="12">
          <el-form-item label="用户名">
            <AppInput v-model="form.username" placeholder="请输入用户名" />
          </el-form-item>
        </el-col>

        <el-col :span="12">
          <el-form-item label="角色">
            <AppSelect
              v-model="form.role"
              placeholder="请选择角色"
              :options="roleOptions"
            />
          </el-form-item>
        </el-col>

        <el-col :span="24">
          <el-form-item label="状态">
            <AppSwitch v-model="form.active" />
            <span style="margin-left: 8px; color: #666;">
              {{ form.active ? '启用' : '禁用' }}
            </span>
          </el-form-item>
        </el-col>

        <el-col :span="24">
          <el-form-item label="备注">
            <AppInput
              v-model="form.remark"
              type="textarea"
              :rows="3"
              placeholder="请输入备注信息"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item>
        <AppButton type="primary" @click="handleSubmit">提交</AppButton>
        <AppButton @click="handleReset">重置</AppButton>
      </el-form-item>
    </el-form>
  </AppCard>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { AppCard, AppInput, AppSelect, AppButton } from '@/components/common'

const form = reactive({
  username: '',
  role: '',
  active: true,
  remark: ''
})

const roleOptions = ref([
  { value: 'admin', label: '管理员' },
  { value: 'editor', label: '编辑者' },
  { value: 'viewer', label: '访客' }
])

function handleSubmit() {
  console.log('提交表单:', form)
}

function handleReset() {
  Object.assign(form, {
    username: '',
    role: '',
    active: true,
    remark: ''
  })
}
</script>
```

### 3.2 按钮组与操作栏

```vue
<template>
  <div class="action-bar">
    <div class="action-bar__left">
      <AppButton type="primary" :icon="Plus" @click="handleCreate">
        新建
      </AppButton>
      <AppButton :icon="Upload" @click="handleImport">
        导入
      </AppButton>
      <AppButton :icon="Download" @click="handleExport">
        导出
      </AppButton>
    </div>

    <div class="action-bar__right">
      <AppInput
        v-model="searchText"
        placeholder="搜索..."
        :prefix-icon="Search"
        clearable
        @keyup.enter="handleSearch"
        style="width: 240px;"
      />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Plus, Upload, Download, Search } from '@element-plus/icons-vue'
import { AppButton, AppInput } from '@/components/common'

const searchText = ref('')

function handleCreate() { console.log('新建') }
function handleImport() { console.log('导入') }
function handleExport() { console.log('导出') }
function handleSearch() { console.log('搜索:', searchText.value) }
</script>

<style scoped>
.action-bar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 6px;
}

.action-bar__left,
.action-bar__right {
  display: flex;
  gap: 8px;
  align-items: center;
}
</style>
```

---

## 4. 业务页面组件

### 4.1 元数据驱动的列表页

```vue
<template>
  <div class="user-management-page">
    <PageHeader title="用户管理" />

    <!-- 使用 MetaListPage 自动生成完整的CRUD页面 -->
    <MetaListPage
      object-type="user"
      :enable-detail="true"
      :enable-auto-crud="true"
      :inline-edit-mode="true"
      :config-overrides="{
        listTitle: '用户列表',
        showCreateButton: true,
        showExportButton: true,
        showImportButton: true
      }"
      @row-click="handleRowClick"
      @row-action="handleRowAction"
    />
  </div>
</template>

<script setup>
import { PageHeader } from '@/components/common'
import { MetaListPage } from '@/components/common/MetaListPage'

function handleRowClick(row) {
  console.log('点击行:', row)
  // 可以打开详情面板或跳转详情页
}

function handleRowAction({ action, row }) {
  console.log('行操作:', action.key, row)
  // 处理编辑、删除等操作
}
</script>
```

### 4.2 对象详情页（ObjectPage）

```vue
<template>
  <div class="detail-page">
    <PageHeader
      title="用户详情"
      :show-back="true"
      @back="$router.back()"
    >
      <template #right>
        <AppButton @click="handleEdit">编辑</AppButton>
        <AppButton type="danger" @click="handleDelete">删除</AppButton>
      </template>
    </PageHeader>

    <ObjectPage
      :object-data="userData"
      :field-groups="fieldGroups"
      :tabs="detailTabs"
      :loading="loading"
    >
      <!-- 自定义 Tab 内容 -->
      <template #audit-log>
        <AuditLog :entity-id="userId" entity-type="user" />
      </template>

      <template #associations>
        <AssociationPanel
          :associations="userAssociations"
          @navigate="handleAssociationNavigate"
        />
      </template>
    </ObjectPage>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { PageHeader, ObjectPage, AppButton } from '@/components/common'
import { AuditLog } from '@/components/common/AuditLog'
import { AssociationPanel } from '@/components/common/AssociationPanel'

const route = useRoute()
const userId = route.params.id
const loading = ref(false)
const userData = ref({})
const userAssociations = ref([])

// 字段分组配置
const fieldGroups = ref([
  {
    title: '基本信息',
    collapsible: false,
    fields: [
      { key: 'username', label: '用户名' },
      { key: 'email', label: '邮箱' },
      { key: 'phone', label: '手机号' },
      { key: 'status', label: '状态' }
    ]
  },
  {
    title: '扩展信息',
    collapsible: true,
    fields: [
      { key: 'department', label: '部门' },
      { key: 'position', label: '职位' },
      { key: 'created_at', label: '创建时间' },
      { key: 'updated_at', label: '更新时间' }
    ]
  }
])

// Tab 配置
const detailTabs = ref([
  { key: 'basic', label: '基本信息', default: true },
  { key: 'audit-log', label: '变更历史' },
  { key: 'associations', label: '关联对象' }
])

onMounted(async () => {
  loading.value = true
  try {
    // 从 API 获取数据
    const res = await fetch(`/api/v2/users/${userId}`)
    userData.value = await res.json()
  } finally {
    loading.value = false
  }
})

function handleEdit() {
  console.log('编辑用户')
}

function handleDelete() {
  console.log('删除用户')
}

function handleAssociationNavigate(association) {
  console.log('导航到关联对象:', association)
}
</script>
```

### 4.3 主从布局（Master-Detail）

```vue
<template>
  <MasterDetailLayout
    :master-width="400"
    :show-detail="!!selectedItem"
  >
    <!-- 左侧：列表 -->
    <template #master>
      <div class="list-header">
        <h3>用户列表</h3>
        <AppInput
          v-model="searchText"
          placeholder="搜索..."
          clearable
          style="width: 200px;"
        />
      </div>

      <el-table
        :data="filteredUsers"
        highlight-current-row
        @current-change="handleCurrentChange"
        max-height="600"
      >
        <el-table-column prop="username" label="用户名" />
        <el-table-column prop="email" label="邮箱" />
        <el-table-column prop="role" label="角色" />
      </el-table>
    </template>

    <!-- 右侧：详情 -->
    <template #detail>
      <div v-if="selectedItem" class="detail-content">
        <PageHeader
          :title="selectedItem.username"
          :show-back="true"
          @back="selectedItem = null"
        >
          <template #right>
            <AppButton type="primary" size="small">保存</AppButton>
          </template>
        </PageHeader>

        <el-descriptions :column="1" border>
          <el-descriptions-item label="用户名">
            {{ selectedItem.username }}
          </el-descriptions-item>
          <el-descriptions-item label="邮箱">
            {{ selectedItem.email }}
          </el-descriptions-item>
          <el-descriptions-item label="角色">
            {{ selectedItem.role }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </template>
  </MasterDetailLayout>
</template>

<script setup>
import { ref, computed } from 'vue'
import { MasterDetailLayout, PageHeader, AppInput, AppButton } from '@/components/common'

const searchText = ref('')
const selectedItem = ref(null)
const users = ref([
  { id: 1, username: '张三', email: 'zhangsan@example.com', role: '管理员' },
  { id: 2, username: '李四', email: 'lisi@example.com', role: '编辑者' },
  { id: 3, username: '王五', email: 'wangwu@example.com', role: '访客' }
])

const filteredUsers = computed(() =>
  users.value.filter(u =>
    u.username.includes(searchText.value) ||
    u.email.includes(searchText.value)
  )
)

function handleCurrentChange(row) {
  selectedItem.value = row
}
</script>

<style scoped>
.list-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid #eee;
}

.detail-content {
  padding: 0 16px;
}
</style>
```

---

## 5. 数据管理组件

### 5.1 过滤器栏（FilterBar）高级用法

```vue
<template>
  <div class="data-management">
    <FilterBar
      v-model:filters="filters"
      :fields="filterFields"
      show-reset
      @search="handleSearch"
      @reset="handleReset"
    />

    <div class="table-container">
      <MetaTable
        :columns="tableColumns"
        :data="tableData"
        :loading="loading"
        :pagination="pagination"
        @sort-change="handleSortChange"
        @page-change="handlePageChange"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { FilterBar, MetaTable, Pagination } from '@/components/common'

const loading = ref(false)
const filters = ref({})

// 过滤器字段配置
const filterFields = ref([
  {
    key: 'keyword',
    label: '关键词',
    type: 'search',
    placeholder: '搜索名称/描述...'
  },
  {
    key: 'status',
    label: '状态',
    type: 'select',
    options: [
      { value: '', label: '全部' },
      { value: 'active', label: '启用' },
      { value: 'inactive', label: '禁用' }
    ]
  },
  {
    key: 'dateRange',
    label: '创建时间',
    type: 'date-range',
    placeholder: ['开始日期', '结束日期']
  },
  {
    key: 'category',
    label: '分类',
    type: 'multi-select',
    options: [
      { value: 'cat1', label: '分类A' },
      { value: 'cat2', label: '分类B' },
      { value: 'cat3', label: '分类C' }
    ]
  }
])

// 表格列配置
const tableColumns = ref([
  { prop: 'name', label: '名称', sortable: true, minWidth: 150 },
  { prop: 'status', label: '状态', width: 100 },
  { prop: 'category', label: '分类', width: 120 },
  { prop: 'created_at', label: '创建时间', sortable: true, width: 180 },
  {
    prop: 'actions',
    label: '操作',
    width: 200,
    fixed: 'right',
    actions: [
      { key: 'view', label: '查看', type: 'primary', link: true },
      { key: 'edit', label: '编辑', link: true },
      { key: 'delete', label: '删除', type: 'danger', link: true }
    ]
  }
])

// 分页配置
const pagination = reactive({
  currentPage: 1,
  pageSize: 20,
  total: 0
})

const tableData = ref([])

async function fetchData() {
  loading.value = true
  try {
    const params = {
      ...filters.value,
      page: pagination.currentPage,
      pageSize: pagination.pageSize
    }
    const res = await fetch('/api/v2/data?' + new URLSearchParams(params))
    const json = await res.json()
    tableData.value = json.items
    pagination.total = json.total
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  pagination.currentPage = 1
  fetchData()
}

function handleReset() {
  filters.value = {}
  handleSearch()
}

function handleSortChange({ prop, order }) {
  console.log('排序:', prop, order)
  fetchData()
}

function handlePageChange(page) {
  pagination.currentPage = page
  fetchData()
}

// 初始加载
fetchData()
</script>
```

### 5.2 可折叠面板（CollapsiblePanel）

```vue
<template>
  <div class="workspace-sidebar">
    <!-- 选择器 Panel -->
    <CollapsiblePanel title="选择范围" :default-expanded="true">
      <div class="panel-content">
        <el-form label-position="top" size="small">
          <el-form-item label="产品">
            <AppSelect v-model="scope.product" :options="productOptions" />
          </el-form-item>
          <el-form-item label="版本">
            <AppSelect v-model="scope.version" :options="versionOptions" />
          </el-form-item>
        </el-form>
      </div>
    </CollapsiblePanel>

    <!-- 对象树 Panel -->
    <CollapsiblePanel title="对象树" :default-expanded="true">
      <el-tree
        :data="objectTree"
        :props="{ label: 'name', children: 'children' }"
        node-key="id"
        default-expand-all
        @node-click="handleNodeClick"
      />
    </CollapsiblePanel>

    <!-- 关系树 Panel -->
    <CollapsiblePanel title="关系范围">
      <el-tree
        :data="relationTree"
        :props="{ label: 'title', children: 'children' }"
        show-checkbox
        @check-change="handleCheckChange"
      />
    </CollapsiblePanel>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { CollapsiblePanel, AppSelect } from '@/components/common'

const scope = ref({
  product: '',
  version: ''
})

const productOptions = ref([
  { value: 'p1', label: '产品 A' },
  { value: 'p2', label: '产品 B' }
])

const versionOptions = ref([
  { value: 'v1', label: 'v1.0.0' },
  { value: 'v2', label: 'v2.0.0' }
])

const objectTree = ref([
  {
    id: 1,
    name: '领域模型',
    children: [
      { id: 11, name: '用户域' },
      { id: 12, name: '订单域' }
    ]
  }
])

const relationTree = ref([...])

function handleNodeClick(data) {
  console.log('选中节点:', data)
}

function handleCheckChange(data, checked) {
  console.log('勾选变化:', data, checked)
}
</script>

<style scoped>
.workspace-sidebar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  height: 100%;
  overflow-y: auto;
}

.panel-content {
  padding: 12px;
}
</style>
```

---

## 6. 对话框与交互组件

### 6.1 确认对话框

```vue
<template>
  <div>
    <AppButton type="danger" @click="showDeleteConfirm = true">
      删除选中项
    </AppButton>

    <ConfirmDialog
      v-model="showDeleteConfirm"
      title="确认删除"
      :content="`确定要删除选中的 ${selectedCount} 项吗？此操作不可恢复。`"
      confirm-text="删除"
      cancel-text="取消"
      confirm-button-type="danger"
      @confirm="handleConfirmDelete"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { AppButton, ConfirmDialog } from '@/components/common'

const showDeleteConfirm = ref(false)
const selectedCount = ref(5)

function handleConfirmDelete() {
  console.log('执行删除')
  showDeleteConfirm.value = false
}
</script>
```

### 6.2 导入导出对话框

```vue
<template>
  <div class="toolbar">
    <AppButton :icon="Upload" @click="showImport = true">导入</AppButton>
    <AppButton :icon="Download" @click="showExport = true">导出</AppButton>

    <!-- 导入对话框 -->
    <ImportDialog
      v-model="showImport"
      title="导入数据"
      :accept-types="'.xlsx,.xls,.csv'"
      template-url="/templates/import-template.xlsx"
      @upload-success="handleImportSuccess"
      @upload-error="handleImportError"
    />

    <!-- 导出对话框 -->
    <ExportDialog
      v-model="showExport"
      title="导出数据"
      :export-formats="['excel', 'csv']"
      :selected-count="selectedRows.length"
      @export="handleExport"
    />
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { Upload, Download } from '@element-plus/icons-vue'
import { AppButton, ImportDialog, ExportDialog } from '@/components/common'

const showImport = ref(false)
const showExport = ref(false)
const selectedRows = ref([])

function handleImportSuccess(response) {
  console.log('导入成功:', response)
}

function handleImportError(error) {
  console.error('导入失败:', error)
}

function handleExport(options) {
  console.log('导出选项:', options)
  // 调用导出 API
}
</script>
```

### 6.3 抽屉面板（Drawer）

```vue
<template>
  <div>
    <AppButton @click="showDrawer = true">打开详情抽屉</AppButton>

    <Drawer
      v-model="showDrawer"
      title="详细信息"
      :width="600"
      :destroy-on-close="true"
    >
      <template #header-extra>
        <AppButton size="small" @click="handleEdit">编辑</AppButton>
      </template>

      <div class="drawer-content">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="名称">{{ detail.name }}</el-descriptions-item>
          <el-descriptions-item label="描述">{{ detail.description }}</el-descriptions-item>
          <el-descriptions-item label="状态">
            <el-tag :type="detail.status === 'active' ? 'success' : 'info'">
              {{ detail.status }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <template #footer>
        <div style="flex: 1;" />
        <AppButton @click="showDrawer = false">关闭</AppButton>
        <AppButton type="primary" @click="handleSave">保存</AppButton>
      </template>
    </Drawer>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { AppButton, Drawer } from '@/components/common'

const showDrawer = ref(false)
const detail = ref({
  name: '示例对象',
  description: '这是一个示例',
  status: 'active'
})

function handleEdit() {
  console.log('编辑')
}

function handleSave() {
  console.log('保存')
  showDrawer.value = false
}
</script>
```

---

## 7. 完整页面示例

### 7.1 架构数据管理页面（完整版）

```vue
<!-- src/views/ArchDataManage.vue -->
<template>
  <AppShell :show-tabs="true" :sidebar-collapsible="true">
    <!-- Header -->
    <template #header-center>
      <BreadcrumbNav :items="breadcrumbs" />
    </template>

    <template #header-right>
      <GlobalSearch placeholder="搜索架构数据..." @search="onSearch" />
      <UserMenu :user="currentUser" @command="onUserCommand" />
    </template>

    <!-- Tabs -->
    <template #tabs>
      <AppTabs v-model="activeTab" :tabs="tabs" @tab-close="closeTab" />
    </template>

    <!-- Sidebar -->
    <template #sidebar>
      <WorkspaceSidebar>
        <!-- 产品+版本选择器 -->
        <CollapsiblePanel title="选择范围" :default-expanded="true">
          <el-form size="small" label-position="top">
            <el-form-item label="产品">
              <AppSelect v-model="scope.product" :options="products" />
            </el-form-item>
            <el-form-item label="版本">
              <AppSelect v-model="scope.version" :options="versions" />
            </el-form-item>
          </el-form>
        </CollapsiblePanel>

        <!-- 对象树 -->
        <CollapsiblePanel title="对象树" :default-expanded="true">
          <ObjectTree :data="objectTree" @select="onObjectSelect" />
        </CollapsiblePanel>

        <!-- 关系树 -->
        <CollapsiblePanel title="关系范围">
          <RelationScopeTree :data="relationTree" @change="onRelationChange" />
        </CollapsiblePanel>
      </WorkspaceSidebar>
    </template>

    <!-- Main Content -->
    <div class="main-content">
      <!-- 工具栏 -->
      <div class="toolbar">
        <div class="toolbar__left">
          <AppButton type="primary" :icon="Plus" @click="handleCreate">
            新建
          </AppButton>
          <AppButton :icon="Upload" @click="showImport = true">
            导入
          </AppButton>
          <AppButton :icon="Download" @click="showExport = true">
            导出
          </AppButton>
        </div>

        <div class="toolbar__right">
          <FilterBar
            v-model:filters="filters"
            :fields="filterFields"
            size="small"
            @search="handleFilter"
          />
        </div>
      </div>

      <!-- 视图切换 -->
      <AppTabs v-model="viewMode" :tabs="viewModes" />

      <!-- 数据展示区域 -->
      <DynamicView
        :mode="viewMode"
        :data="tableData"
        :loading="loading"
        :pagination="pagination"
        @row-click="handleRowClick"
        @action="handleAction"
        @page-change="handlePageChange"
      />

      <!-- 详情侧滑面板 -->
      <Drawer
        v-model="showDetail"
        title="对象详情"
        :width="640"
        placement="right"
      >
        <ObjectPage
          v-if="selectedItem"
          :object-data="selectedItem"
          :field-groups="detailFields"
        />
      </Drawer>

      <!-- 导入/导出对话框 -->
      <ImportDialog v-model="showImport" @success="refreshData" />
      <ExportDialog v-model="showExport" @export="handleExport" />
    </div>
  </AppShell>
</template>

<script setup>
// 此处省略具体实现代码...
// 参考上述各组件的使用方式组合
</script>
```

---

## 8. 常见问题 FAQ

### Q1: 如何自定义组件样式？

**A**: 所有组件都支持通过 CSS Variables 覆盖默认样式：

```scss
// 在你的页面或全局样式中
.my-custom-page {
  --el-color-primary: #your-color;
  --spacing-md: 24px;  // 自定义间距
}
```

### Q2: 如何处理组件的事件？

**A**: 使用 `@event-name` 监听事件：

```vue
<AppTabs
  v-model="activeTab"
  :tabs="tabs"
  @tab-click="onTabClick"
  @tab-close="onTabClose"
/>
```

### Q3: 组件支持 TypeScript 吗？

**A**: ✅ 支持！所有组件都有完整的 TypeScript 类型定义。可以参考 API 文档中的 `interface` 定义。

### Q4: 如何进行单元测试？

**A**: 使用 Vitest + Vue Test Utils：

```javascript
import { mount } from '@vue/test-utils'
import { AppTabs } from '@/components/common'

describe('AppTabs', () => {
  it('should render tabs correctly', () => {
    const wrapper = mount(AppTabs, {
      props: {
        tabs: [{ id: '1', label: 'Tab 1' }],
        modelValue: '1'
      }
    })
    expect(wrapper.find('.app-tabs__item').exists()).toBe(true)
  })
})
```

### Q5: 性能优化建议？

**A**:
1. 使用 `<KeepAlive>` 缓存 Tab 内容
2. 对于大数据量表格，启用虚拟滚动
3. 使用 `v-once` 静态内容
4. 懒加载非首屏组件

---

## 📚 相关资源

- **API 文档**: [顶部导航组件 API](file:///d:/filework/excel-to-diagram/docs/architecture/14-top-navigation-components-api.md)
- **设计规范**: [YonDesign UI 规范](file:///d:/filework/excel-to-diagram/src/styles/YON_EP_GUIDE.md)
- **治理规则**: [组件治理规范](file:///d:/filework/excel-to-diagram/.trae/rules/component-governance.md)
- **架构分析**: [顶部导航架构](file:///d:/filework/excel-to-diagram/docs/architecture/13-top-navigation-architecture.md)

---

**文档维护者**: 架构团队
**最后更新**: 2026-05-19

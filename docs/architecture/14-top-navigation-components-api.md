## 目录

1. [📋 目录](#-目录)
2. [1. 系统架构概览](#1-系统架构概览)
3. [2. AppShell - 全局容器](#2-appshell---全局容器)
4. [3. AppTabs - 多页面Tab管理](#3-apptabs---多页面tab管理)
5. [4. BreadcrumbNav - 面包屑导航](#4-breadcrumbnav---面包屑导航)
6. [5. UserMenu - 用户菜单](#5-usermenu---用户菜单)
7. [6. GlobalSearch - 全局搜索](#6-globalsearch---全局搜索)
8. [7. PageHeader - 页面标题栏](#7-pageheader---页面标题栏)
9. [8. 集成示例](#8-集成示例)
10. [9. 最佳实践](#9-最佳实践)
11. [📚 相关文档](#-相关文档)
12. [🔄 版本历史](#-版本历史)

---
# 顶部导航系统组件库 API 文档

> **版本**: v1.0.0
> **创建日期**: 2026-05-19
> **状态**: ✅ 已完成
> **参考**: SAP Fiori / Salesforce Lightning Console / Microsoft Dynamics 365

---

## 📋 目录

1. [系统架构概览](#1-系统架构概览)
2. [AppShell - 全局容器](#2-appshell---全局容器)
3. [AppTabs - 多页面Tab管理](#3-apptabs---多页面tab管理)
4. [BreadcrumbNav - 面包屑导航](#4-breadcrumbnav---面包屑导航)
5. [UserMenu - 用户菜单](#5-usermenu---用户菜单)
6. [GlobalSearch - 全局搜索](#6-globalsearch---全局搜索)
7. [PageHeader - 页面标题栏](#7-pageheader---页面标题栏)
8. [集成示例](#8-集成示例)
9. [最佳实践](#9-最佳实践)

---

## 1. 系统架构概览

### 1.1 架构设计理念

参考头部企业产品的 UI Pattern，构建统一的全局导航系统：

```
┌─────────────────────────────────────────────────────────────────────┐
│ AppShell (全局容器)                                                 │
│ ┌─────────────────────────────────────────────────────────────────┐ │
│ │ Header (56px)                                                   │ │
│ │ [Logo] [面包屑] [搜索框.............] [通知] [用户▼]           │ │
│ ├─────────────────────────────────────────────────────────────────┤ │
│ │ Tabs Bar (44px)                                                 │ │
│ │ [Page1] [Page2] [Page3]...                              [更多 ▼]│ │
│ ├───────────┬─────────────────────────────────────────────────────┤ │
│ │ Sidebar   │ Content Area                                       │ │
│ │ (240px)   │                                                     │ │
│ │ (可选)    │                                                     │ │
│ └───────────┴─────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.2 组件依赖关系

```
AppShell (容器)
├── AppHeader (可选)
│   ├── BreadcrumbNav
│   ├── GlobalSearch
│   └── UserMenu
├── AppTabs (可选)
├── AppSideNav (Sidebar，可选)
└── Content Area (Slot)
```

### 1.3 技术栈要求

- **Vue 3** Composition API (`<script setup>`)
- **Element Plus** ^2.14.0
- **YonDesign Theme** (圆润风格)
- **CSS Variables** (间距/颜色/圆角)

---

## 2. AppShell - 全局容器

### 2.1 组件说明

应用的最外层容器，提供统一的布局结构（Header + Tabs + Sidebar + Content）。

**文件路径**: `src/components/common/AppShell/AppShell.vue`

### 2.2 Props

| Prop | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `showSidebar` | Boolean | `true` | 是否显示侧边栏 |
| `showTabs` | Boolean | `false` | 是否显示 Tab 栏 |
| `sidebarWidth` | Number \| String | `240` | 侧边栏宽度（px） |
| `sidebarCollapsible` | Boolean | `false` | 是否可折叠侧边栏 |

### 2.3 Slots

| Slot 名称 | 说明 | 作用域 |
|-----------|------|--------|
| `header` | 自定义 Header 区域 | - |
| `header-left` | Header 左侧区域（Logo） | - |
| `header-center` | Header 中间区域（面包屑/搜索） | - |
| `header-right` | Header 右侧区域（用户菜单） | - |
| `tabs` | Tab 栏内容 | - |
| `sidebar` | 侧边栏内容 | - |
| `default` | 主内容区 | - |
| `footer` | 底部区域（可选） | - |

### 2.4 使用示例

#### 基础用法

```vue
<template>
  <AppShell :show-tabs="true" :sidebar-width="260">
    <!-- Header 区域 -->
    <template #header-left>
      <img src="/logo.png" alt="Logo" height="32" />
    </template>

    <template #header-center>
      <BreadcrumbNav :items="breadcrumbs" />
      <GlobalSearch placeholder="搜索..." />
    </template>

    <template #header-right>
      <UserMenu :user="currentUser" :menu-items="userMenuItems" />
    </template>

    <!-- Tab 栏 -->
    <template #tabs>
      <AppTabs v-model="activeTab" :tabs="openTabs" @tab-close="closeTab" />
    </template>

    <!-- 侧边栏 -->
    <template #sidebar>
      <AppSideNav :menus="navigationMenus" />
    </template>

    <!-- 主内容区 -->
    <router-view />
  </AppShell>
</template>

<script setup>
import { ref } from 'vue'
import { AppShell, AppTabs, BreadcrumbNav, GlobalSearch, UserMenu, AppSideNav } from '@/components/common'

const activeTab = ref('home')
const currentUser = ref({ name: '张三', email: 'zhangsan@example.com', role: '管理员' })
const breadcrumbs = ref([
  { label: '首页', to: '/' },
  { label: '系统管理', to: '/system' },
  { label: '用户管理' }
])
const openTabs = ref([
  { id: 'home', label: '首页', icon: 'home', pinned: true },
  { id: 'users', label: '用户管理', closable: true }
])
const userMenuItems = ref([
  { key: 'profile', label: '个人信息', icon: 'User' },
  { key: 'settings', label: '账户设置', icon: 'Setting', divided: true },
  { key: 'logout', label: '退出登录', icon: 'SwitchButton', danger: true }
])
</script>
```

#### 最小化用法（仅 Header）

```vue
<template>
  <AppShell :show-sidebar="false">
    <template #header-right>
      <UserMenu :user="user" />
    </template>

    <div class="page-content">
      <h1>页面内容</h1>
    </div>
  </AppShell>
</template>
```

### 2.5 样式定制

AppShell 使用 CSS Variables，可通过覆盖变量自定义样式：

```scss
// 覆盖 AppShell 默认样式
.app-shell {
  --app-shell-header-height: 64px;        // Header 高度（默认 56px）
  --app-shell-sidebar-width: 280px;       // 侧边栏宽度
  --app-shell-tabs-height: 48px;          // Tabs 高度（默认 44px）
}
```

---

## 3. AppTabs - 多页面Tab管理

### 3.1 组件说明

多页面 Tab 管理组件，支持打开多个页面并快速切换。参考 Salesforce Console 的 Primary Tabs 设计。

**文件路径**: `src/components/common/AppTabs/AppTabs.vue`

### 3.2 Props

| Prop | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `tabs` | Array | `[]` | Tab 列表（见下文数据结构） |
| `modelValue` (v-model) | String \| Number | `null` | 当前激活的 Tab ID |
| `maxTabs` | Number | `8` | 最大可见 Tab 数量 |

#### Tab 数据结构

```typescript
interface TabItem {
  id: string | number        // 唯一标识
  label: string              // 显示文本
  icon?: string              // 图标名称（可选）
  badge?: string \| number   // 徽章数字/文本（可选）
  closable?: boolean         // 是否可关闭（默认 true，pinned 时 false）
  pinned?: boolean           // 是否固定（不可关闭）
}
```

### 3.3 Events

| 事件名 | 参数 | 说明 |
|--------|------|------|
| `update:modelValue` | `(value: string\|number)` | 激活 Tab 切换时触发 |
| `tab-click` | `(tab: TabItem)` | 点击 Tab 时触发 |
| `tab-close` | `(tabId: string\|number)` | 关闭 Tab 时触发 |

### 3.4 使用示例

#### 基础用法

```vue
<template>
  <AppTabs v-model="activeTab" :tabs="tabs" @tab-close="handleClose" />
</template>

<script setup>
import { ref } from 'vue'
import { AppTabs } from '@/components/common'

const activeTab = ref('dashboard')
const tabs = ref([
  {
    id: 'dashboard',
    label: '仪表盘',
    icon: 'dashboard',
    pinned: true  // 固定 Tab，不可关闭
  },
  {
    id: 'users',
    label: '用户管理',
    closable: true,
    badge: 5  // 未读数
  },
  {
    id: 'roles',
    label: '角色管理',
    closable: true
  }
])

function handleClose(tabId) {
  const index = tabs.value.findIndex(t => t.id === tabId)
  if (index > -1 && !tabs.value[index].pinned) {
    tabs.value.splice(index, 1)
    // 如果关闭的是当前激活的 Tab，切换到前一个
    if (activeTab.value === tabId && tabs.value.length > 0) {
      activeTab.value = tabs.value[Math.max(0, index - 1)].id
    }
  }
}

function openNewPage(pageId, pageTitle) {
  // 避免重复打开
  if (!tabs.value.find(t => t.id === pageId)) {
    tabs.value.push({
      id: pageId,
      label: pageTitle,
      closable: true
    })
  }
  activeTab.value = pageId
}
</script>
```

#### 与路由联动

```vue
<template>
  <AppTabs v-model="activeTab" :tabs="tabs" @tab-click="navigateToTab" @tab-close="closeTab" />
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'

const router = useRouter()
const route = useRoute()
const activeTab = ref(route.name)
const tabs = ref([{ id: route.name, label: route.meta.title, pinned: true }])

// 监听路由变化
watch(() => route.name, (newName) => {
  if (!tabs.value.find(t => t.id === newName)) {
    tabs.value.push({
      id: newName,
      label: route.meta.title || newName,
      closable: true
    })
  }
  activeTab.value = newName
})

function navigateToTab(tab) {
  router.push({ name: tab.id })
}

function closeTab(tabId) {
  const index = tabs.value.findIndex(t => t.id === tabId)
  if (index > -1) {
    tabs.value.splice(index, 1)
    if (activeTab.value === tabId && tabs.value.length > 0) {
      navigateToTab(tabs.value[Math.max(0, index - 1)])
    }
  }
}
</script>
```

---

## 4. BreadcrumbNav - 面包屑导航

### 4.1 组件说明

面包屑导航组件，支持路由跳转、省略号折叠、自定义分隔符。

**文件路径**: `src/components/common/BreadcrumbNav/BreadcrumbNav.vue`

### 4.2 Props

| Prop | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `items` | Array | **必填** | 面包屑项列表 |
| `separator` | String | `'›'` | 分隔符（默认 ›） |
| `maxItems` | Number | `5` | 最大显示项数（超出显示省略号） |
| `homeItem` | Object | `{ label: '首页', to: '/' }` | 首页配置 |
| `ariaLabel` | String | `'面包屑导航'` | 无障碍标签 |

#### Item 数据结构

```typescript
interface BreadcrumbItem {
  label: string       // 显示文本
  to?: string | object  // 路由路径（最后一项不渲染链接）
}
```

### 4.3 使用示例

#### 基础用法

```vue
<template>
  <BreadcrumbNav :items="breadcrumbs" />
</template>

<script setup>
import { ref } from 'vue'
import { BreadcrumbNav } from '@/components/common'

const breadcrumbs = ref([
  { label: '首页', to: '/' },
  { label: '系统管理', to: '/system' },
  { label: '用户管理', to: '/system/users' },
  { label: '用户详情' }  // 当前页，无 to 属性
])
</script>
```

#### 自定义分隔符和首页

```vue
<template>
  <BreadcrumbNav
    :items="breadcrumbs"
    separator="/"
    :max-items="3"
    :home-item="{ label: 'Home', to: '/dashboard' }"
  />
</template>
```

#### 动态生成（基于路由）

```vue
<template>
  <BreadcrumbNav :items="matchedRoutes" />
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const matchedRoutes = computed(() =>
  route.matched
    .filter(record => record.meta?.title)
    .map(record => ({
      label: record.meta.title,
      to: record.path !== route.path ? record.path : undefined
    }))
)
</script>
```

---

## 5. UserMenu - 用户菜单

### 5.1 组件说明

用户信息下拉菜单，展示头像、用户名、角色及操作项。

**文件路径**: `src/components/common/UserMenu/UserMenu.vue`

### 5.2 Props

| Prop | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user` | Object | `{}` | 用户信息对象 |
| `menuItems` | Array | `[默认菜单项]` | 菜单项列表 |
| `showName` | Boolean | `false` | 是否显示用户名 |
| `showHeader` | Boolean | `true` | 是否显示头部信息卡片 |

#### User 数据结构

```typescript
interface UserInfo {
  name: string        // 用户姓名
  email?: string      // 邮箱
  avatar?: string     // 头像 URL
  role?: string       // 角色名称
}
```

#### MenuItem 数据结构

```typescript
interface MenuItem {
  key: string             // 唯一标识
  label: string           // 显示文本
  icon?: Component        // Element Plus 图标组件
  divided?: boolean       // 是否显示分割线（默认 false）
  disabled?: boolean      // 是否禁用（默认 false）
  danger?: boolean        // 是否危险操作（红色，默认 false）
}
```

### 5.3 Events

| 事件名 | 参数 | 说明 |
|--------|------|------|
| `command` | `(key: string)` | 点击菜单项时触发 |

### 5.4 使用示例

#### 基础用法

```vue
<template>
  <UserMenu
    :user="currentUser"
    :menu-items="menuItems"
    :show-name="true"
    @command="handleCommand"
  />
</template>

<script setup>
import { ref } from 'vue'
import { UserMenu } from '@/components/common'
import { Setting, SwitchButton, User as UserIcon } from '@element-plus/icons-vue'

const currentUser = ref({
  name: '张三',
  email: 'zhangsan@example.com',
  avatar: '/avatars/zhangsan.png',
  role: '系统管理员'
})

const menuItems = ref([
  { key: 'profile', label: '个人信息', icon: UserIcon },
  { key: 'account', label: '账户设置', icon: Setting, divided: true },
  { key: 'logout', label: '退出登录', icon: SwitchButton, danger: true }
])

function handleCommand(key) {
  switch (key) {
    case 'profile':
      console.log('查看个人信息')
      break
    case 'settings':
      console.log('打开设置')
      break
    case 'logout':
      // 执行登出逻辑
      logout()
      break
  }
}
</script>
```

---

## 6. GlobalSearch - 全局搜索

### 6.1 组件说明

全局搜索输入框，支持快捷键唤起、搜索建议、最近搜索历史。

**文件路径**: `src/components/common/GlobalSearch/GlobalSearch.vue`

### 6.2 Props

| Prop | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `placeholder` | String | `'搜索...'` | 占位文本 |
| `hotkey` | String | `'Ctrl+K'` | 快捷键组合 |
| `suggestions` | Array | `[]` | 搜索建议列表 |
| `recentSearches` | Array | `[]` | 最近搜索历史 |

#### Suggestion 数据结构

```typescript
interface Suggestion {
  id: string | number
  title: string           // 标题
  subtitle?: string       // 副标题
  type?: 'page' | 'folder' | 'user' | 'setting'  // 类型（影响图标）
}
```

### 6.3 Events

| 事件名 | 参数 | 说明 |
|--------|------|------|
| `search` | `(keyword: string)` | 按回车或点击搜索时触发 |
| `suggestion-click` | `(suggestion: Suggestion)` | 点击建议项时触发 |
| `recent-click` | `(keyword: string)` | 点击最近搜索时触发 |
| `clear` | - | 清空搜索框时触发 |

### 6.4 使用示例

#### 基础用法

```vue
<template>
  <GlobalSearch
    placeholder="搜索功能、页面、用户..."
    hotkey="Ctrl+K"
    :recent-searches="recentList"
    :suggestions="suggestions"
    @search="handleSearch"
    @suggestion-click="handleSuggestionClick"
  />
</template>

<script setup>
import { ref } from 'vue'
import { GlobalSearch } from '@/components/common'

const recentList = ref(['用户管理', '角色权限', '审计日志'])
const suggestions = ref([
  { id: 1, title: '用户管理', subtitle: '系统管理 > 用户管理', type: 'page' },
  { id: 2, title: '张三', subtitle: '系统管理员', type: 'user' },
  { id: 3, title: '系统设置', subtitle: '全局配置', type: 'setting' }
])

function handleSearch(keyword) {
  console.log('搜索关键词:', keyword)
  // 执行搜索逻辑
  router.push({ path: '/search', query: { q: keyword } })
}

function handleSuggestionClick(suggestion) {
  console.log('点击建议:', suggestion)
  // 根据类型跳转
  switch (suggestion.type) {
    case 'page':
      router.push(suggestion.subtitle.split('> ')[1])
      break
    case 'user':
      router.push(`/users/${suggestion.id}`)
      break
  }
}
</script>
```

---

## 7. PageHeader - 页面标题栏

### 7.1 组件说明

页面级标题栏，通常用于子页面，包含返回按钮、标题和操作按钮。

**文件路径**: `src/components/common/AppHeader.vue`（别名 PageHeader）

### 7.2 Props

| Prop | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `title` | String | `''` | 页面标题 |
| `showBack` | Boolean | `false` | 是否显示返回按钮 |

### 7.3 Events

| 事件名 | 参数 | 说明 |
|--------|------|------|
| `back` | - | 点击返回按钮时触发 |

### 7.4 Slots

| Slot 名称 | 说明 |
|-----------|------|
| `left` | 左侧自定义内容（替换默认的返回按钮+标题） |
| `right` | 右侧操作按钮区域 |

### 7.5 使用示例

```vue
<template>
  <PageHeader
    title="用户详情"
    :show-back="true"
    @back="$router.back()"
  >
    <template #right>
      <el-button type="primary" @click="save">保存</el-button>
      <el-button @click="reset">重置</el-button>
    </template>
  </PageHeader>

  <div class="page-content">
    <!-- 页面主体内容 -->
  </div>
</template>

<script setup>
import { PageHeader } from '@/components/common'

function save() {
  // 保存逻辑
}

function reset() {
  // 重置逻辑
}
</script>
```

---

## 8. 集成示例

### 8.1 完整应用布局（推荐）

```vue
<!-- src/App.vue 或 src/layouts/MainLayout.vue -->
<template>
  <AppShell :show-tabs="true" :sidebar-collapsible="true">
    <!-- ====== Header Left: Logo ====== -->
    <template #header-left>
      <div class="logo">
        <img src="@/assets/logo.svg" alt="System Logo" height="28" />
        <span class="logo__title">元数据管理系统</span>
      </div>
    </template>

    <!-- ====== Header Center: Navigation ====== -->
    <template #header-center>
      <div class="header-center">
        <BreadcrumbNav :items="currentBreadcrumbs" />
        <GlobalSearch
          placeholder="搜索..."
          :recent-searches="recentSearches"
          @search="onGlobalSearch"
        />
      </div>
    </template>

    <!-- ====== Header Right: User Actions ====== -->
    <template #header-right>
      <div class="header-actions">
        <el-badge :value="notificationCount" :max="99">
          <el-button :icon="Bell" circle />
        </el-badge>
        <UserMenu
          :user="currentUser"
          :menu-items="userMenuItems"
          :show-name="true"
          @command="handleUserCommand"
        />
      </div>
    </template>

    <!-- ====== Tabs Bar ====== -->
    <template #tabs>
      <AppTabs
        v-model="activeTabId"
        :tabs="openTabs"
        @tab-click="onTabClick"
        @tab-close="onTabClose"
      />
    </template>

    <!-- ====== Sidebar ====== -->
    <template #sidebar>
      <AppSideNav :menus="sidebarMenus" :collapsed="sidebarCollapsed" />
    </template>

    <!-- ====== Main Content ====== -->
    <router-view v-slot="{ Component }">
      <transition name="fade" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </AppShell>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell } from '@element-plus/icons-vue'
import {
  AppShell, AppTabs, BreadcrumbNav, GlobalSearch,
  UserMenu, AppSideNav
} from '@/components/common'

const route = useRoute()
const router = useRouter()

// State
const activeTabId = ref(route.name)
const sidebarCollapsed = ref(false)
const notificationCount = ref(3)
const currentUser = ref({
  name: 'Admin',
  email: 'admin@example.com',
  role: '超级管理员'
})

// Computed
const currentBreadcrumbs = computed(() => [
  { label: '首页', to: '/' },
  ...route.matched
    .filter(r => r.meta?.title)
    .map(r => ({
      label: r.meta.title,
      to: r.path !== route.path ? r.path : undefined
    }))
])

const openTabs = ref([
  { id: 'home', label: '仪表盘', icon: 'Odometer', pinned: true },
  // ... 其他打开的页面
])

const userMenuItems = ref([
  { key: 'profile', label: '个人信息', icon: 'User' },
  { key: 'settings', label: '系统设置', icon: 'Setting', divided: true },
  { key: 'logout', label: '退出登录', icon: 'SwitchButton', danger: true }
])

// Methods
function onTabClick(tab) {
  router.push({ name: tab.id })
}

function onTabClose(tabId) {
  const idx = openTabs.value.findIndex(t => t.id === tabId)
  if (idx > -1) openTabs.value.splice(idx, 1)
}

function onGlobalSearch(keyword) {
  router.push({ path: '/search', query: { q: keyword } })
}

function handleUserCommand(key) {
  if (key === 'logout') {
    // 登出逻辑
  }
}
</script>

<style scoped>
.logo {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  font-weight: 600;
  font-size: 16px;
  color: var(--yonyou-orange-600);
}

.header-center {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  flex: 1;
  justify-content: center;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}
</style>
```

---

## 9. 最佳实践

### 9.1 性能优化

1. **懒加载 Tab 内容**
   ```vue
   <KeepAlive :include="cachedTabs">
     <router-view />
   </KeepAlive>
   ```

2. **限制最大 Tab 数量**
   ```vue
   <AppTabs :max-tabs="8" :tabs="tabs" />
   ```

3. **防抖搜索输入**
   ```javascript
   import { useDebounceFn } from '@vueuse/core'
   const debouncedSearch = useDebounceFn((keyword) => {
     fetchSuggestions(keyword)
   }, 300)
   ```

### 9.2 无障碍性 (A11y)

- 所有组件已内置 ARIA 属性
- 支持键盘导航（Tab/Enter/Esc）
- 面包屑导航使用 `<nav>` 和 `<ol>` 语义标签
- 搜索框支持屏幕阅读器

### 9.3 样式一致性

✅ **必须遵守 YonDesign 规范**：

| 元素 | 圆角 | 间距 | 颜色 |
|------|------|------|------|
| 按钮 | 6px | padding: 8px 16px | 主色 #ea580c |
| 输入框 | 6px | height: 32px | 边框 #e5e6eb |
| 下拉菜单 | 4px | item-padding: 8px 16px | - |
| 卡片 | 8px | padding: 16px | 背景 #fff |

### 9.4 错误处理

```vue
<UserMenu
  :user="user ?? {}"
  :menu-items="menuItems ?? defaultMenus"
  @command="safeHandleCommand"
/>
```

---

## 📚 相关文档

- [YonDesign UI 规范](file:///d:/filework/excel-to-diagram/src/styles/YON_EP_GUIDE.md)
- [组件治理规范](file:///d:/filework/excel-to-diagram/.trae/rules/component-governance.md)
- [顶部导航架构分析](file:///d:/filework/excel-to-diagram/docs/architecture/13-top-navigation-architecture.md)
- [架构数据管理模式分析](file:///d:/filework/excel-to-diagram/docs/architecture/12-arch-data-manage-component-analysis.md)

---

## 🔄 版本历史

| 版本 | 日期 | 变更内容 |
|------|------|----------|
| v1.0.0 | 2026-05-19 | 初始版本，完成 6 个核心组件 |

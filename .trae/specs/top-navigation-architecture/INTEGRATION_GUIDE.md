# 顶部导航与多页面 Tab 管理系统 - 集成指南

## 概述

本文档说明了如何将新创建的顶部导航组件集成到现有应用中。

## 组件清单

### 已创建的组件

1. **AppHeader** (`src/components/common/AppHeader/`)
   - 全功能顶部导航组件
   - 包含 Logo、面包屑、全局搜索、通知、用户菜单
   - 使用 YonDesign Orange 主题色

2. **AppLayout** (`src/components/common/AppLayout/`)
   - 整合 AppShell、AppHeader、AppTabs 的布局包装组件
   - 支持侧边栏和 Tab 栏配置

3. **AppShell** (`src/components/common/AppShell/`)
   - 全局应用容器组件
   - 管理应用级布局结构

4. **AppTabs** (`src/components/common/AppTabs/`)
   - 多页面 Tab 管理组件
   - 支持 Tab 切换、关闭、新建
   - 支持 Tab 溢出处理

5. **BreadcrumbNav** (`src/components/common/BreadcrumbNav/`)
   - 面包屑导航组件
   - 支持最大显示数量配置

6. **GlobalSearch** (`src/components/common/GlobalSearch/`)
   - 全局搜索组件
   - 支持 Ctrl+K 快捷键
   - 支持搜索建议和最近搜索

7. **UserMenu** (`src/components/common/UserMenu/`)
   - 用户菜单组件
   - 支持自定义菜单项

### 已有组件（已存在）

- **appStore.ts** - Pinia 状态管理（已实现 Tab 管理、用户状态、通知状态）
- **router/index.js** - 路由配置（已增强 Tab 管理集成）

## 集成步骤

### 1. 在新页面中使用 AppLayout

```vue
<template>
  <AppLayout
    :show-sidebar="true"
    :show-tabs="true"
    :breadcrumbs="breadcrumbs"
    :search-suggestions="searchSuggestions"
    @logo-click="handleLogoClick"
    @search="handleSearch"
    @user-command="handleUserCommand"
  >
    <template #sidebar>
      <AppSideNav :items="menuItems" />
    </template>

    <!-- 页面内容 -->
    <div class="page-content">
      <h1>欢迎使用架构工作台</h1>
    </div>
  </AppLayout>
</template>

<script setup>
import { ref } from 'vue'
import { AppLayout } from '@/components/common'

const breadcrumbs = ref([
  { label: '首页', to: '/' },
  { label: '当前页面' }
])

const menuItems = ref([
  { key: 'home', label: '首页', icon: 'Home', to: '/' },
  { key: 'data', label: '数据管理', icon: 'Data', to: '/data' }
])

function handleLogoClick() {
  console.log('Logo clicked')
}

function handleSearch(keyword) {
  console.log('Search:', keyword)
}

function handleUserCommand(key) {
  if (key === 'logout') {
    // 处理退出登录
  }
}
</script>

<style scoped>
.page-content {
  padding: var(--spacing-lg);
}
</style>
```

### 2. 在 App.vue 中使用 AppLayout

如果需要全局使用 AppLayout，可以修改 `src/App.vue`：

```vue
<template>
  <div id="app">
    <LoginPage v-if="authEnabled && !authStore.isLoggedIn" />
    <ChangePasswordDialog
      v-if="authEnabled && authStore.isLoggedIn && authStore.mustChangePassword"
      :visible="authStore.mustChangePassword"
      @close="handleChangePasswordClose"
    />
    <AppLayout v-else-if="!authStore.mustChangePassword">
      <router-view />
    </AppLayout>
    <NotificationContainer />
  </div>
</template>

<script setup>
import { AppLayout } from '@/components/common'
// ... 其他导入
</script>
```

### 3. 使用 AppStore 进行状态管理

在组件中使用 appStore：

```javascript
import { useAppStore } from '@/stores/appStore'

const appStore = useAppStore()

// Tab 管理
appStore.openTab({
  id: '/data/1',
  label: '数据管理',
  path: '/data/1'
})

appStore.closeTab('/data/1')
appStore.switchTab('/data/2')

// 用户状态
appStore.setUser({
  id: '1',
  name: '张三',
  email: 'zhangsan@example.com'
})

// 通知状态
appStore.setNotifications([
  { id: '1', title: '新消息', read: false }
])

// 侧边栏控制
appStore.toggleSidebar()
```

### 4. 路由集成

路由守卫已自动集成 Tab 管理。导航时自动创建和切换 Tab：

```javascript
// 路由定义（已在 router/index.js 中配置）
{
  path: '/data/:productId?/:versionId?',
  name: 'data',
  component: () => import('@/views/ArchDataManageApp/index.vue'),
  meta: { title: '架构数据管理' }
}

// 路由守卫会自动：
// 1. 检查是否存在对应的 Tab
// 2. 如果存在，切换到该 Tab
// 3. 如果不存在，创建新的 Tab
```

### 5. 自定义面包屑导航

```vue
<template>
  <AppLayout :breadcrumbs="customBreadcrumbs">
    <!-- 内容 -->
  </AppLayout>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const customBreadcrumbs = computed(() => {
  const crumbs = [
    { label: '首页', to: '/' }
  ]

  if (route.path.startsWith('/data')) {
    crumbs.push({ label: '数据管理', to: '/data' })
  }

  if (route.params.productId) {
    crumbs.push({ label: `产品 ${route.params.productId}` })
  }

  return crumbs
})
</script>
```

### 6. 全局搜索集成

```vue
<template>
  <AppLayout
    :search-suggestions="suggestions"
    :recent-searches="recentSearches"
    @search="handleGlobalSearch"
  >
    <!-- 内容 -->
  </AppLayout>
</template>

<script setup>
import { ref } from 'vue'

const suggestions = ref([
  { id: '1', title: '搜索结果1', type: 'page' },
  { id: '2', title: '搜索结果2', type: 'document' }
])

const recentSearches = ref(['关键词1', '关键词2'])

function handleGlobalSearch(keyword) {
  console.log('Global search:', keyword)
  // 实现搜索逻辑
}
</script>
```

## API 参考

### AppLayout Props

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| showSidebar | Boolean | true | 是否显示侧边栏 |
| showTabs | Boolean | true | 是否显示 Tab 栏 |
| sidebarWidth | Number/String | 240 | 侧边栏宽度 |
| maxTabs | Number | 10 | 最大 Tab 数量 |
| logoUrl | String | '' | Logo 图片 URL |
| logoAlt | String | 'Logo' | Logo 替代文本 |
| logoText | String | 'ArchWorkspace' | Logo 文字 |
| breadcrumbs | Array | [] | 面包屑导航项 |
| searchPlaceholder | String | '搜索...' | 搜索框占位符 |
| searchSuggestions | Array | [] | 搜索建议列表 |
| recentSearches | Array | [] | 最近搜索列表 |

### AppLayout Events

| 事件名 | 参数 | 说明 |
|--------|------|------|
| logo-click | - | 点击 Logo 时触发 |
| notification-click | - | 点击通知图标时触发 |
| search | keyword: string | 触发搜索时触发 |
| suggestion-click | suggestion: object | 点击搜索建议时触发 |
| user-command | key: string | 点击用户菜单项时触发 |
| tab-change | tabId: string | Tab 切换时触发 |
| tab-click | tab: object | 点击 Tab 时触发 |
| tab-close | tabId: string | 关闭 Tab 时触发 |

### appStore API

#### Tab 管理

```javascript
// 打开新 Tab
appStore.openTab({ id, label, path, meta })

// 关闭 Tab
appStore.closeTab(tabId)

// 切换 Tab
appStore.switchTab(tabId)

// 固定/取消固定 Tab
appStore.pinTab(tabId)

// 关闭所有非固定 Tab
appStore.closeAllTabs()

// 关闭其他 Tab
appStore.closeOtherTabs(keepTabId)
```

#### 用户状态

```javascript
// 设置用户信息
appStore.setUser(user)

// 退出登录
appStore.logout()
```

#### 通知状态

```javascript
// 设置通知列表
appStore.setNotifications(notifications)

// 标记单条通知为已读
appStore.markNotificationRead(id)

// 标记所有通知为已读
appStore.markAllNotificationsRead()
```

## 样式规范

所有组件都遵循 YonDesign 设计规范：

- 主色调：`--yonyou-orange-600` (#ea580c)
- 背景色：`rgba(234, 88, 12, 0.06)`（hover 状态）
- 圆角：6px（按钮/输入框）、4px（标签/分页）
- 间距：4px / 8px / 16px / 24px

详细规范请参考：
- `src/styles/YON_DESIGN_CONSTANTS.md`
- `src/styles/YON_EP_GUIDE.md`

## 注意事项

1. **状态持久化**：appStore 使用 Pinia 的 persist 插件，Tab 状态会自动保存到 localStorage
2. **性能优化**：Tab 数量超过 10 个时会显示警告
3. **响应式设计**：组件支持移动端适配
4. **无障碍**：所有组件都支持键盘导航和屏幕阅读器

## 常见问题

### Q: 如何禁用 Tab 自动创建？

A: 在路由 meta 中设置 `openInNewTab: false`：

```javascript
{
  path: '/special-page',
  name: 'special-page',
  component: () => import('@/views/SpecialPage.vue'),
  meta: { title: '特殊页面', openInNewTab: false }
}
```

### Q: 如何自定义用户菜单项？

A: 使用 AppLayout 的 `userMenuItems` prop：

```vue
<AppLayout
  :user-menu-items="customMenuItems"
  @user-command="handleUserCommand"
>
</AppLayout>

<script setup>
const customMenuItems = [
  { key: 'profile', label: '个人资料', icon: 'User' },
  { key: 'settings', label: '设置', icon: 'Setting' },
  { key: 'help', label: '帮助文档', icon: 'QuestionFilled' },
  { key: 'logout', label: '退出登录', icon: 'SwitchButton', danger: true }
]

function handleUserCommand(key) {
  // 处理菜单命令
}
</script>
```

### Q: 如何添加通知徽章？

A: 通过 appStore 设置通知数量：

```javascript
appStore.setNotifications([
  { id: '1', title: '新消息', read: false },
  { id: '2', title: '系统通知', read: false }
])

// unreadCount 会自动计算未读数量
console.log(appStore.unreadCount) // 2
```

## 更新日志

### v1.0.0 (2026-05-14)
- 创建完整的顶部导航组件套件
- 实现多页面 Tab 管理功能
- 集成全局搜索功能
- 实现用户菜单组件
- 添加 Pinia 状态管理
- 增强路由守卫支持

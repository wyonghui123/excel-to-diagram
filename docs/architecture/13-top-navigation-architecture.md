## 目录

1. [一、核心问题](#一-核心问题)
2. [二、头部企业 UI Pattern 分析](#二-头部企业-ui-pattern-分析)
3. [三、顶部导航架构对比](#三-顶部导航架构对比)
4. [四、推荐的顶部导航架构](#四-推荐的顶部导航架构)
5. [五、面包屑系统设计](#五-面包屑系统设计)
6. [六、用户菜单设计](#六-用户菜单设计)
7. [七、全局搜索设计](#七-全局搜索设计)
8. [八、多页面 Tab 管理系统](#八-多页面-tab-管理系统)
9. [九、实施建议](#九-实施建议)
10. [十、总结](#十-总结)
11. [附录：快捷键规范](#附录：快捷键规范)

---
# 顶部导航与多页面 Tab 管理系统架构分析

> **版本**: v1.0  
> **分析日期**: 2024-05-13  
> **参考**: SAP Fiori, Salesforce Console, Microsoft Dynamics 365, Workday, ServiceNow, Atlassian

---

## 一、核心问题

### 1.1 当前问题

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ 当前架构缺失                                                           │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  1. 没有统一的顶部导航架构                                             │
│     - 各页面独立 Header                                                │
│     - 缺少全局 Shell 容器                                             │
│                                                                        │
│  2. 多页面 Tab 管理缺失                                               │
│     - 无法同时打开多个页面                                              │
│     - 无法在页面间快速切换                                            │
│     - 页面状态无法保留                                                │
│                                                                        │
│  3. 面包屑和路径导航不统一                                           │
│     - 各页面自行实现                                                  │
│     - 样式和行为不一致                                               │
│                                                                        │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 需要解决的问题

1. **全局导航**: 如何设计统一的顶部导航区域
2. **多页面管理**: 如何支持同时打开多个页面并快速切换
3. **路径导航**: 如何设计清晰的面包屑系统
4. **用户菜单**: 如何设计用户信息入口
5. **全局搜索**: 如何设计统一的搜索入口

---

## 二、头部企业 UI Pattern 分析

### 2.1 SAP Fiori Shell 架构

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ SAP Fiori Shell                                                                │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ Shell Header (全局导航栏)                                              │  │
│  │ ┌────────────────────────────────────────────────────────────────────┐   │  │
│  │ │ [Logo] [搜索框.....................] [通知] [用户头像 ▼]     │   │  │
│  │ └────────────────────────────────────────────────────────────────────┘   │  │
│  ├──────────────────────────────────────────────────────────────────────────┤  │
│  │ [App 1] [App 2 - Tab] [App 3 - Tab]                          [+] │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌────────────────┬───────────────────────────────────────────────────┐      │
│  │                │                                                   │      │
│  │  Global       │                                                   │      │
│  │  Navigation   │              App Content Area                     │      │
│  │  (Anchor Bar)  │                                                   │      │
│  │                │                                                   │      │
│  │  ├─ Home      │                                                   │      │
│  │  ├─ Sales    │                                                   │      │
│  │  ├─ Purchase  │                                                   │      │
│  │  └─ Finance  │                                                   │      │
│  │                │                                                   │      │
│  └────────────────┴───────────────────────────────────────────────────┘      │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

**核心特点**:
- **Shell 容器**: 整个应用的顶层容器
- **Shell Header**: 全局导航栏（Logo、搜索、通知、用户）
- **App Tabs**: 显示当前打开的应用（最多 8 个）
- **Global Navigation**: 全局导航（左侧）
- **App Content**: 应用内容区

---

### 2.2 Salesforce Lightning Console 架构

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Salesforce Lightning Console                                                     │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ Console Header                                                       │  │
│  │ [← 返回] [刷新] [工具]                          [搜索...] [帮助] [用户] │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ Primary Tabs (最多 10 个)                                           │  │
│  │ [Account: ACME Corp] [Case: 12345] [Opportunity: Deal A]    [+] │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌────────────────┬───────────────────────────────────────────────────────────┐  │
│  │                │                                                           │  │
│  │  Left Sidebar │   Tab Content Area                                      │  │
│  │                │                                                           │  │
│  │  Navigator    │   ┌─────────────────────────────────────────────┐        │  │
│  │  ├─ Accounts  │   │ Subtab: [Details] [Related] [Activity] [Chatter]│   │  │
│  │  ├─ Contacts  │   ├─────────────────────────────────────────────┤        │  │
│  │  ├─ Cases    │   │                                         │        │  │
│  │  └─ Leads    │   │   Content                                │        │  │
│  │                │   │                                         │        │  │
│  │  ─────────    │   │                                         │        │  │
│  │  Utility Bar  │   │                                         │        │  │
│  │  [Path Explorer]  │   └─────────────────────────────────────────────┘        │  │
│  │  [History]   │                                                           │  │
│  └────────────────┴───────────────────────────────────────────────────────────┘  │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

**核心特点**:
- **Console Header**: 控制台全局 Header
- **Primary Tabs**: 主 Tab（对象级别）
- **Subtabs**: 子 Tab（详情内部）
- **Left Sidebar**: 可折叠的导航面板
- **Utility Bar**: 底部工具栏（快速访问）
- **Navigator**: 记录快速切换

---

### 2.3 Microsoft Dynamics 365 架构

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Microsoft Dynamics 365                                                           │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ Navigation Bar                                                         │  │
│  │ [应用切换器] 销售 Hub                        [搜索...] [通知] [设置] [用户]│  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ Command Bar                                                           │  │
│  │ [+ 新建] [导入数据] [导出数据]                [视图: 有效客户 ▼]      │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ Grid View                                                             │  │
│  │ ┌────┬──────────────┬─────────┬────────┬─────────┐                   │  │
│  │ │ ☐  │ 客户名称     │ 行业    │ 区域   │ 状态    │                   │  │
│  │ ├────┼──────────────┼─────────┼────────┼─────────┤                   │  │
│  │ │ ☐  │ ACME Corp   │ 科技    │ 华东   │ 有效    │                   │  │
│  │ └────┴──────────────┴─────────┴────────┴─────────┘                   │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ Record Form (点击记录后)                                             │  │
│  │ ┌───────────────────────────────────────────────────────────────┐    │  │
│  │ │ Command Bar: [保存] [删除] [共享] [分配] [更多 ▼]          │    │  │
│  │ ├───────────────────────────────────────────────────────────────┤    │  │
│  │ │ Header: [图标] ACME Corporation    [状态] [所有者]           │    │  │
│  │ ├───────────────────────────────────────────────────────────────┤    │  │
│  │ │ Tabs: [通用] [详细信息] [相关] [活动] [KPI]                │    │  │
│  │ ├───────────────────────────────────────────────────────────────┤    │  │
│  │ │ Content Area                                           │    │  │
│  │ │                                                        │    │  │
│  │ └───────────────────────────────────────────────────────────────┘    │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

**核心特点**:
- **Navigation Bar**: 应用切换 + 全局搜索
- **Command Bar**: 实体级操作
- **View/Form 切换**: 通过 URL 参数控制
- **Record Form**: 详情页全屏展示

---

### 2.4 Workday 架构

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ Workday Workspace                                                              │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ Global Navigation Bar                                                 │  │
│  │ [Workday Logo] [搜索框.............................] [通知] [收藏] [用户] │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ Breadcrumb                                                          │  │
│  │ ← 返回  人员 > 工作台 > 员工记录                                    │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ Worker Header                                                      │  │
│  │ [照片] 张三 (李四)                                                  │  │
│  │       高级软件工程师 | 研发部 | ACME Corp                           │  │
│  │       [查看完整资料] [编辑] [更多操作 ▼]                              │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ Tab Navigation                                                     │  │
│  │ [概述] [工作时间] [休假] [福利] [工资单] [Talent]                    │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ Content Area                                                       │  │
│  │                                                                     │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

**核心特点**:
- **Global Navigation Bar**: 全局导航（Logo + 搜索 + 通知 + 用户）
- **Breadcrumb**: 清晰的路径导航
- **Worker Header**: 记录级别 Header（照片 + 关键信息）
- **Tab Navigation**: 标签页导航
- **Workspace 概念**: 每个功能模块是独立的 Workspace

---

### 2.5 ServiceNow 架构

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ ServiceNow                                                                │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ Application Navigator Header                                         │  │
│  │ [≡ 菜单] [搜索框.............................] [通知] [设置] [用户 ▼] │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ Breadcrumb + Context Header                                         │  │
││  │ 系统日志 > 迁移 > 迁移计划                                         │  │
│  │ [迁移计划: MGR-001]                              [←] [→] [刷新] [更多 ▼] │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌────────────────┬───────────────────────────────────────────────────────────┐  │
│  │                │                                                           │  │
│  │  Application   │   Content Area                                        │  │
│  │  Navigator     │   ┌─────────────────────────────────────────────┐        │  │
│  │                │   │ Form / List / Dashboard                           │        │  │
│  │  ├─ Incidents │   │                                                 │        │  │
│  │  ├─ Problems  │   │                                                 │        │  │
│  │  ├─ Changes   │   │                                                 │        │  │
│  │  └─ CMDB      │   └─────────────────────────────────────────────┘        │  │
│  │                │                                                           │  │
│  │  [Favorites] │                                                           │  │
│  │  [History]   │                                                           │  │
│  └────────────────┴───────────────────────────────────────────────────────────┘  │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

**核心特点**:
- **Application Navigator**: 左侧可折叠导航
- **Breadcrumb + Context Header**: 清晰的上下文导航
- **History Navigation**: 前进/后退按钮
- **多窗口支持**: 可以同时打开多个记录

---

## 三、顶部导航架构对比

### 3.1 整体架构对比

| 特性 | SAP Fiori | Salesforce | Dynamics 365 | Workday | ServiceNow |
|------|-----------|------------|---------------|----------|-------------|
| **全局容器** | Shell | Console | Navigation Bar | Global Nav | App Navigator |
| **多页面 Tab** | ✅ App Tabs | ✅ Primary Tabs | ❌ 全屏 | ❌ Workspace | ✅ 多窗口 |
| **路径导航** | 面包屑 | 面包屑 | 面包屑 | 面包屑 | 面包屑 |
| **用户菜单** | ✅ Header | ✅ Header | ✅ Header | ✅ Header | ✅ Header |
| **全局搜索** | ✅ Shell | ✅ Header | ✅ Nav Bar | ✅ Global Nav | ✅ Header |
| **通知系统** | ✅ Shell | ✅ Header | ✅ Nav Bar | ✅ Global Nav | ✅ Header |
| **导航位置** | 左侧 | 左侧 | 顶部 | 顶部 | 左侧 |

### 3.2 核心组件对比

| 组件 | SAP Fiori | Salesforce | Dynamics 365 | Workday | ServiceNow |
|------|-----------|------------|---------------|----------|-------------|
| **Logo** | 左侧 | 无 | 应用切换器 | Logo | 菜单按钮 |
| **搜索** | Shell Header | Header (放大镜) | Nav Bar | Global Nav | Header |
| **通知** | Shell Header | Header | Nav Bar | Global Nav | Header |
| **用户** | Shell Header | Header | Nav Bar | Global Nav | Header |
| **后退按钮** | 无 | 无 | 无 | 面包屑左侧 | 上下文 Header |
| **刷新** | 无 | Console Header | 无 | 无 | 上下文 Header |

---

## 四、推荐的顶部导航架构

### 4.1 整体架构设计

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ AppShell (全局容器)                                                            │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ AppHeader (全局导航栏)                                              │  │
│  │                                                                        │  │
│  │  ┌──────────────────────────────────────────────────────────────┐   │  │
│  │  │ [≡ 菜单] [Logo/品牌]  [面包屑...............]   [搜索] [通知] [用户]│   │  │
│  │  └──────────────────────────────────────────────────────────────┘   │  │
│  │                                                                        │  │
│  │  ┌──────────────────────────────────────────────────────────────┐   │  │
│  │  │ [Tab 1] [Tab 2 - Active] [Tab 3]            [更多 ▼] [×] │   │  │
│  │  └──────────────────────────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌────────────────┬───────────────────────────────────────────────────┐  │
│  │                │                                                   │  │
│  │  AppSidebar   │   AppContent (路由视图)                           │  │
│  │  (可选)       │                                                   │  │
│  │                │   ┌─────────────────────────────────────────────┐   │  │
│  │  ├─ 主菜单1   │   │ PageHeader (页面标题栏)                    │   │  │
│  │  ├─ 主菜单2   │   │ [← 返回] 页面标题        [操作1] [操作2] │   │  │
│  │  └─ 主菜单3   │   ├─────────────────────────────────────────────┤   │  │
│  │                │   │                                             │   │  │
│  │                │   │ TabNav / Content / Detail Panel          │   │  │
│  │                │   │                                             │   │  │
│  │                │   │                                             │   │  │
│  │                │   └─────────────────────────────────────────────┘   │  │
│  │                │                                                   │  │
│  └────────────────┴───────────────────────────────────────────────────┘  │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐  │
│  │ AppFooter (可选: 全局提示、状态栏)                                   │  │
│  └──────────────────────────────────────────────────────────────────────────┘  │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 核心组件设计

#### 4.2.1 AppShell 组件

```vue
<!-- AppShell.vue -->
<template>
  <div class="app-shell">
    <AppHeader
      :logo="logo"
      :breadcrumbs="breadcrumbs"
      :user="currentUser"
      :notifications="notifications"
      @search="handleGlobalSearch"
      @notification-click="handleNotificationClick"
      @user-menu-click="handleUserMenuClick"
    />
    
    <div class="app-shell__workspace">
      <AppTabs
        v-if="openPages.length > 0"
        :tabs="openPages"
        :active-tab="activePageId"
        @tab-click="switchPage"
        @tab-close="closePage"
        @tab-more="showPageMenu"
      />
      
      <AppSidebar
        v-if="showSidebar"
        :items="sidebarItems"
        @item-click="handleSidebarClick"
      />
      
      <main class="app-shell__content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
const openPages = ref([])           // 打开的页面列表
const activePageId = ref(null)      // 当前活动页面

function openPage(page) {
  const existing = openPages.value.find(p => p.id === page.id)
  if (existing) {
    activePageId.value = existing.id
    return
  }
  
  if (openPages.value.length >= MAX_TABS) {
    showWarning('最多打开 ' + MAX_TABS + ' 个页面')
    return
  }
  
  openPages.value.push(page)
  activePageId.value = page.id
  router.push(page.path)
}

function closePage(pageId) {
  const index = openPages.value.findIndex(p => p.id === pageId)
  if (index === -1) return
  
  openPages.value.splice(index, 1)
  
  if (activePageId.value === pageId) {
    const newActive = openPages.value[index] || openPages.value[index - 1]
    if (newActive) {
      activePageId.value = newActive.id
      router.push(newActive.path)
    }
  }
}
</script>
```

#### 4.2.2 AppHeader 组件

```vue
<!-- AppHeader.vue -->
<template>
  <header class="app-header">
    <!-- 左侧区域: Logo + 面包屑 -->
    <div class="header-left">
      <button v-if="showMenuButton" class="menu-btn" @click="$emit('menu-click')">
        <AppIcon name="menu" />
      </button>
      
      <router-link to="/" class="logo">
        <img :src="logo" alt="Logo" />
      </router-link>
      
      <nav v-if="breadcrumbs?.length" class="breadcrumb">
        <template v-for="(crumb, index) in breadcrumbs" :key="index">
          <span v-if="index > 0" class="breadcrumb-sep">›</span>
          <router-link 
            v-if="crumb.to" 
            :to="crumb.to"
            class="breadcrumb-item"
          >
            {{ crumb.label }}
          </router-link>
          <span v-else class="breadcrumb-item breadcrumb-item--current">
            {{ crumb.label }}
          </span>
        </template>
      </nav>
    </div>
    
    <!-- 中央区域: 搜索 (可选) -->
    <div v-if="showSearch" class="header-center">
      <div class="global-search">
        <AppIcon name="search" class="search-icon" />
        <input 
          v-model="searchQuery"
          type="text"
          placeholder="搜索..."
          @focus="showSearchDropdown = true"
          @keyup.enter="handleSearch"
        />
        <kbd class="search-shortcut">Ctrl+K</kbd>
      </div>
    </div>
    
    <!-- 右侧区域: 通知 + 用户 -->
    <div class="header-right">
      <AppBadge v-if="notificationCount > 0" :count="notificationCount">
        <button class="icon-btn" @click="$emit('notification-click')">
          <AppIcon name="bell" />
        </button>
      </AppBadge>
      
      <AppDropdown :items="userMenuItems" @command="handleUserMenuCommand">
        <button class="user-btn">
          <AppAvatar :src="user?.avatar" :name="user?.name" size="sm" />
          <span class="user-name">{{ user?.name }}</span>
          <AppIcon name="chevron-down" size="xs" />
        </button>
      </AppDropdown>
    </div>
  </header>
</template>

<script setup>
const props = defineProps({
  logo: String,
  breadcrumbs: Array,
  user: Object,
  notifications: Array,
  showSearch: { type: Boolean, default: true },
  showMenuButton: { type: Boolean, default: true },
})

const emit = defineEmits([
  'search', 
  'notification-click', 
  'user-menu-click',
  'menu-click'
])

const notificationCount = computed(() => props.notifications?.length || 0)

const userMenuItems = [
  { key: 'profile', label: '个人资料', icon: 'user' },
  { key: 'settings', label: '设置', icon: 'settings' },
  { type: 'divider' },
  { key: 'logout', label: '退出登录', icon: 'logout' }
]
</script>
```

#### 4.2.3 AppTabs 组件 (多页面 Tab)

```vue
<!-- AppTabs.vue -->
<template>
  <div class="app-tabs">
    <div class="tabs-scroll">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        :class="['tab-item', { 'tab-item--active': activeTab === tab.id }]"
        @click="$emit('tab-click', tab)"
      >
        <span class="tab-icon" v-if="tab.icon">
          <AppIcon :name="tab.icon" />
        </span>
        <span class="tab-label">{{ tab.label }}</span>
        <button 
          v-if="tab.closable !== false"
          class="tab-close"
          @click.stop="$emit('tab-close', tab.id)"
        >
          <AppIcon name="close" size="xs" />
        </button>
      </button>
    </div>
    
    <AppDropdown v-if="tabs.length > MIN_VISIBLE_TABS" :items="overflowTabs" @command="handleTabCommand">
      <button class="tab-more">
        <AppIcon name="more-horizontal" />
      </button>
    </AppDropdown>
  </div>
</template>

<script setup>
const MAX_VISIBLE_TABS = 8
const MIN_VISIBLE_TABS = 5

const props = defineProps({
  tabs: { type: Array, required: true },
  activeTab: { type: [String, Number], required: true },
})

const emit = defineEmits(['tab-click', 'tab-close', 'tab-more'])

const visibleTabs = computed(() => props.tabs.slice(0, MAX_VISIBLE_TABS))
const overflowTabs = computed(() => props.tabs.slice(MAX_VISIBLE_TABS))
</script>
```

#### 4.2.4 PageHeader 组件

```vue
<!-- PageHeader.vue -->
<template>
  <header class="page-header">
    <div class="page-header__left">
      <button v-if="showBackButton" class="back-btn" @click="$emit('back')">
        <AppIcon name="arrow-left" />
        <span>返回</span>
      </button>
      
      <div class="page-title-group">
        <h1 class="page-title">{{ title }}</h1>
        <p v-if="subtitle" class="page-subtitle">{{ subtitle }}</p>
      </div>
      
      <AppBadge v-if="status" :type="statusType">{{ status }}</AppBadge>
    </div>
    
    <div class="page-header__right">
      <slot name="actions" />
    </div>
  </header>
</template>

<script setup>
const props = defineProps({
  title: { type: String, required: true },
  subtitle: String,
  status: String,
  statusType: { type: String, default: 'default' },
  showBackButton: { type: Boolean, default: false },
})

const emit = defineEmits(['back'])
</script>
```

---

## 五、面包屑系统设计

### 5.1 面包屑配置结构

```typescript
interface BreadcrumbItem {
  label: string          // 显示文本
  to?: string           // 路由路径
  icon?: string         // 图标（可选）
  params?: object       // 路由参数
  query?: object        // 查询参数
}

interface BreadcrumbConfig {
  separator?: string    // 分隔符，默认 '›'
  maxItems?: number      // 最大显示数量，默认 5
  homeItem?: BreadcrumbItem  // 首页配置
  showCurrent?: boolean  // 是否显示当前页
}
```

### 5.2 面包屑组件

```vue
<!-- BreadcrumbNav.vue -->
<template>
  <nav class="breadcrumb-nav" :aria-label="ariaLabel">
    <ol class="breadcrumb-list">
      <!-- 首页 -->
      <li v-if="config.homeItem" class="breadcrumb-item">
        <router-link :to="config.homeItem.to || '/'">
          <AppIcon v-if="config.homeItem.icon" :name="config.homeItem.icon" />
          {{ config.homeItem.label || '首页' }}
        </router-link>
      </li>
      
      <!-- 其他路径 -->
      <template v-for="(item, index) in visibleItems" :key="index">
        <li class="breadcrumb-separator" aria-hidden="true">
          {{ config.separator || '›' }}
        </li>
        <li class="breadcrumb-item" :class="{ 'is-current': index === visibleItems.length - 1 }">
          <router-link 
            v-if="item.to && index < visibleItems.length - 1"
            :to="item.to"
            :class="'breadcrumb-link'"
          >
            {{ item.label }}
          </router-link>
          <span v-else class="breadcrumb-current">{{ item.label }}</span>
        </li>
      </template>
      
      <!-- 省略号 -->
      <li v-if="hasOverflow" class="breadcrumb-ellipsis">
        <button @click="showAll = true">...</button>
      </li>
    </ol>
  </nav>
</template>
```

---

## 六、用户菜单设计

### 6.1 用户菜单配置

```typescript
interface UserMenuItem {
  key: string           // 唯一标识
  label: string         // 显示文本
  icon?: string         // 图标
  disabled?: boolean    // 是否禁用
  danger?: boolean     // 危险操作（红色）
  divided?: boolean    // 分隔线
  children?: UserMenuItem[]  // 子菜单
}

interface UserMenuConfig {
  user: {
    id: string
    name: string
    avatar?: string
    email?: string
    role?: string
  }
  items: UserMenuItem[]
}
```

### 6.2 用户菜单组件

```vue
<!-- UserMenu.vue -->
<template>
  <AppDropdown :items="config.items" placement="bottom-end" @command="handleCommand">
    <button class="user-menu-trigger">
      <AppAvatar 
        :src="config.user.avatar" 
        :name="config.user.name" 
        size="sm" 
      />
      <span class="user-menu-name">{{ config.user.name }}</span>
      <AppIcon name="chevron-down" size="xs" />
    </button>
    
    <template #dropdown-header>
      <div class="user-info">
        <AppAvatar :src="config.user.avatar" :name="config.user.name" size="lg" />
        <div class="user-details">
          <div class="user-name">{{ config.user.name }}</div>
          <div class="user-email">{{ config.user.email }}</div>
          <div v-if="config.user.role" class="user-role">
            <AppBadge>{{ config.user.role }}</AppBadge>
          </div>
        </div>
      </div>
    </template>
  </AppDropdown>
</template>
```

---

## 七、全局搜索设计

### 7.1 搜索配置

```typescript
interface GlobalSearchConfig {
  placeholder?: string
  hotkey?: string          // 快捷键，默认 'Ctrl+K'
  recentSearches?: string[]  // 最近搜索
  suggestions?: SearchSuggestion[]
  onSearch: (query: string) => void
  onSuggestionClick: (suggestion: SearchSuggestion) => void
}

interface SearchSuggestion {
  type: 'page' | 'record' | 'action' | 'help'
  icon?: string
  title: string
  subtitle?: string
  to?: string
  action?: () => void
}
```

### 7.2 搜索组件

```vue
<!-- GlobalSearch.vue -->
<template>
  <div class="global-search" :class="{ 'is-focused': isFocused }">
    <AppIcon name="search" class="search-icon" />
    <input
      v-model="query"
      type="text"
      :placeholder="config.placeholder || '搜索...'"
      @focus="handleFocus"
      @blur="handleBlur"
      @keyup="handleKeyup"
    />
    <kbd v-if="!isFocused" class="search-shortcut">
      {{ config.hotkey || 'Ctrl+K' }}
    </kbd>
    
    <div v-if="isFocused && (suggestions.length || recentSearches.length)" class="search-dropdown">
      <!-- 最近搜索 -->
      <div v-if="recentSearches.length" class="search-section">
        <div class="section-title">最近搜索</div>
        <div 
          v-for="item in recentSearches" 
          :key="item"
          class="search-item"
          @click="handleRecentClick(item)"
        >
          <AppIcon name="history" size="sm" />
          <span>{{ item }}</span>
        </div>
      </div>
      
      <!-- 搜索建议 -->
      <div v-if="suggestions.length" class="search-section">
        <div class="section-title">建议</div>
        <div 
          v-for="suggestion in suggestions" 
          :key="suggestion.id"
          class="search-item"
          :class="'type-' + suggestion.type"
          @click="handleSuggestionClick(suggestion)"
        >
          <AppIcon :name="getIcon(suggestion.type)" size="sm" />
          <div class="item-content">
            <div class="item-title">{{ suggestion.title }}</div>
            <div v-if="suggestion.subtitle" class="item-subtitle">
              {{ suggestion.subtitle }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
```

---

## 八、多页面 Tab 管理系统

### 8.1 Tab 状态管理

```typescript
interface TabState {
  tabs: Tab[]
  activeTabId: string | null
  maxTabs: number
  tabOverflow: 'scroll' | 'dropdown' | 'overflow'
}

interface Tab {
  id: string
  label: string
  icon?: string
  path: string
  closable: boolean
  badge?: number | string
  loading?: boolean
  cached?: boolean  // 是否缓存页面状态
}

interface TabStore {
  state: TabState
  
  // Actions
  openTab(tab: Tab): void
  closeTab(tabId: string): void
  switchTab(tabId: string): void
  pinTab(tabId: string): void
  moveTab(fromIndex: number, toIndex: number): void
  closeAllTabs(): void
  closeOtherTabs(keepTabId: string): void
}
```

### 8.2 Tab 管理 composable

```typescript
// composables/useTabManager.ts
import { defineStore } from 'pinia'

export const useTabStore = defineStore('tabs', {
  state: () => ({
    tabs: [],
    activeTabId: null,
    maxTabs: 10,
  }),
  
  getters: {
    activeTab: (state) => state.tabs.find(t => t.id === state.activeTabId),
    pinnedTabs: (state) => state.tabs.filter(t => t.pinned),
    hasOverflow: (state) => state.tabs.length > 8,
  },
  
  actions: {
    openTab(tab) {
      const existing = this.tabs.find(t => t.id === tab.id)
      
      if (existing) {
        this.activeTabId = existing.id
        return
      }
      
      if (this.tabs.length >= this.maxTabs) {
        console.warn('Tab 数量已达上限')
        return
      }
      
      this.tabs.push({ ...tab, pinned: false, cached: true })
      this.activeTabId = tab.id
    },
    
    closeTab(tabId) {
      const index = this.tabs.findIndex(t => t.id === tabId)
      if (index === -1) return
      
      const tab = this.tabs[index]
      if (tab.pinned) return  // 固定的 Tab 不能关闭
      
      this.tabs.splice(index, 1)
      
      if (this.activeTabId === tabId) {
        const newActive = this.tabs[index] || this.tabs[index - 1]
        this.activeTabId = newActive?.id || null
      }
    },
    
    switchTab(tabId) {
      this.activeTabId = tabId
    },
    
    pinTab(tabId) {
      const tab = this.tabs.find(t => t.id === tabId)
      if (tab) {
        tab.pinned = !tab.pinned
      }
    },
  },
  
  persist: true,  // 持久化 Tab 状态
})
```

---

## 九、实施建议

### 9.1 组件优先级

| 优先级 | 组件 | 说明 |
|--------|-------|------|
| P0 | **AppShell** | 全局容器 |
| P0 | **AppHeader** | 顶部导航栏 |
| P0 | **AppTabs** | 多页面 Tab |
| P0 | **BreadcrumbNav** | 面包屑导航 |
| P1 | **UserMenu** | 用户菜单 |
| P1 | **GlobalSearch** | 全局搜索 |
| P2 | **NotificationPanel** | 通知面板 |

### 9.2 实施步骤

```
Phase 1: 基础架构 (1 周)
├── 创建 AppShell 组件
├── 创建 AppHeader 组件
├── 创建 AppTabs 组件
└── 集成路由系统

Phase 2: 导航功能 (1 周)
├── 创建 BreadcrumbNav 组件
├── 创建 UserMenu 组件
├── 实现面包屑生成逻辑
└── 实现用户菜单

Phase 3: 高级功能 (1 周)
├── 创建 GlobalSearch 组件
├── 创建 NotificationPanel 组件
├── 实现搜索建议
└── 实现通知系统

Phase 4: 优化 (1 周)
├── Tab 状态持久化
├── Tab 拖拽排序
├── 键盘快捷键支持
└── 性能优化
```

---

## 十、总结

### 10.1 推荐架构

```
┌─────────────────────────────────────────────────────────────┐
│ AppShell                                             │
├─────────────────────────────────────────────────────┤
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │ AppHeader                                    │   │
│  │ [≡] [Logo] [面包屑...........] [🔍] [🔔] [👤]│   │
│  └─────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────┐   │
│  │ AppTabs (多页面)                            │   │
│  │ [首页] [业务对象] [供应商] [客户] [+]  │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │ PageHeader                                  │   │
│  │ [← 返回] 业务对象详情   [编辑] [删除]       │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │ Content                                     │   │
│  │                                            │   │
│  │                                            │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
└─────────────────────────────────────────────────────┘
```

### 10.2 关键设计决策

1. **Shell 容器**: 必须有，作为全局状态容器
2. **多 Tab**: 必须有，支持同时打开多个页面
3. **面包屑**: 必须有，提供清晰的路径导航
4. **全局搜索**: 推荐有，提升用户体验
5. **用户菜单**: 必须有，提供用户入口

### 10.3 与现有系统的集成

```
现有系统                    集成方案
─────────────────────────────────────────────
Vue Router                  通过 router-view 在 AppShell 中渲染
Pinia Store               Tab 状态、用户状态、全局状态
权限系统                   AppHeader 根据权限显示/隐藏按钮
通知系统                   NotificationPanel 组件
搜索系统                   GlobalSearch 组件
```

---

## 附录：快捷键规范

| 快捷键 | 功能 |
|---------|------|
| `Ctrl + K` | 全局搜索 |
| `Ctrl + T` | 新建 Tab |
| `Ctrl + W` | 关闭当前 Tab |
| `Ctrl + Tab` | 切换到下一个 Tab |
| `Ctrl + Shift + Tab` | 切换到上一个 Tab |
| `Alt + ←` | 后退 |
| `Alt + →` | 前进 |
| `Escape` | 关闭弹窗/面板 |

# 顶部导航与多页面 Tab 管理系统规范

## Why
当前系统缺少统一的顶部导航架构，存在以下问题：
- 各页面使用独立的 Header，缺乏统一性
- 不支持多页面 Tab 管理，用户无法同时打开多个页面
- 面包屑和路径导航不统一
- 用户菜单、通知系统、全局搜索缺失

## What Changes

### 1. 新建 AppShell 组件
- 全局应用容器
- 管理应用级状态
- 提供全局布局结构

### 2. 新建 AppHeader 组件
- Logo 和品牌标识
- 面包屑导航
- 全局搜索入口
- 通知入口
- 用户菜单

### 3. 新建 AppTabs 组件（多页面 Tab）
- 支持多页面同时打开
- Tab 切换、关闭、新建
- Tab 状态持久化
- Tab 溢出处理（超过 8 个显示"更多"菜单）

### 4. 新建 PageHeader 组件
- 页面级标题
- 返回按钮
- 页面级操作按钮
- 状态标签

### 5. 新建 BreadcrumbNav 组件
- 面包屑导航
- 可配置的分隔符和最大显示数量
- 路径可点击跳转

### 6. 新建 UserMenu 组件
- 用户头像和名称
- 下拉菜单
- 个人资料、设置、退出登录等操作

### 7. 新建 GlobalSearch 组件
- 全局搜索入口
- 快捷键支持（Ctrl+K）
- 搜索建议下拉

## Impact

### Affected Capabilities
- 应用导航系统
- 多页面管理
- 用户交互体验

### Affected Code
- src/components/common/AppShell/
- src/components/common/AppHeader/
- src/components/common/AppTabs/
- src/components/common/PageHeader/
- src/components/common/BreadcrumbNav/
- src/components/common/UserMenu/
- src/components/common/GlobalSearch/
- src/router/ (路由守卫集成)
- src/stores/ (Pinia 状态管理)

## ADDED Requirements

### Requirement: AppShell 全局容器
系统 SHALL 提供 AppShell 组件作为整个应用的全局容器，包含顶部导航、Tab 栏和内容区域。

#### Scenario: 应用启动
- **GIVEN** 用户登录系统
- **WHEN** 应用加载
- **THEN** AppShell 渲染顶部导航和初始页面

### Requirement: AppHeader 顶部导航栏
系统 SHALL 提供 AppHeader 组件，包含面包屑、搜索、通知和用户菜单。

#### Scenario: 显示顶部导航
- **GIVEN** AppShell 渲染
- **WHEN** 导航栏初始化
- **THEN** 显示 Logo、面包屑、搜索、通知和用户菜单

### Requirement: 多页面 Tab 管理
系统 SHALL 支持同时打开多个页面，并可通过 Tab 快速切换。

#### Scenario: 打开新页面
- **GIVEN** 用户在系统中
- **WHEN** 用户打开一个新页面
- **THEN** 创建新的 Tab，并激活该 Tab

#### Scenario: 关闭 Tab
- **GIVEN** 用户打开了多个 Tab
- **WHEN** 用户点击 Tab 的关闭按钮
- **THEN** 关闭该 Tab，并激活相邻的 Tab

#### Scenario: Tab 数量限制
- **GIVEN** 用户打开了 10 个 Tab
- **WHEN** 用户尝试打开第 11 个 Tab
- **THEN** 显示警告提示，阻止打开新 Tab

### Requirement: 面包屑导航
系统 SHALL 提供面包屑组件，显示当前页面路径。

#### Scenario: 显示面包屑
- **GIVEN** 用户在系统的某个页面
- **WHEN** 页面包含面包屑配置
- **THEN** 显示面包屑路径，点击可跳转

### Requirement: 用户菜单
系统 SHALL 提供用户菜单，显示用户信息并提供操作入口。

#### Scenario: 显示用户菜单
- **GIVEN** 用户已登录
- **WHEN** 点击用户头像/名称
- **THEN** 显示下拉菜单，包含个人资料、设置、退出登录等

## EXISTING System Integration

### 现有系统集成方案

#### 1. AppHeader 组件集成
现有 Header 实现：
- `AppHeader.vue` - 已有，需扩展支持面包屑和 Tab
- `ArchWorkspace.vue` - 有独立 Header，需迁移到 AppHeader

集成策略：
- 复用现有 AppHeader 的样式
- 添加面包屑支持
- 添加 AppTabs 支持

#### 2. Sidebar 集成
现有 Sidebar 实现：
- `UnifiedScopePanel.vue` - 架构数据管理侧边栏
- `AppSideNav.vue` - 侧边导航

集成策略：
- Sidebar 移入 AppShell 的左侧区域
- 支持折叠/展开

#### 3. Tab 管理集成
现有 Tab 实现：
- `AppTabs.vue` - 基础 Tab 组件

扩展需求：
- 添加多 Tab 支持
- 添加关闭按钮
- 添加溢出处理

#### 4. 面包屑系统
现有面包屑：
- 部分页面自行实现面包屑

统一方案：
- 新建 BreadcrumbNav 组件
- 统一使用 Vue Router 的 matched routes 生成面包屑

#### 5. 用户菜单
现有用户菜单：
- 分散在各页面中

统一方案：
- 新建 UserMenu 组件
- 统一在 AppHeader 中使用

#### 6. 全局搜索
现有搜索：
- 部分页面有本地搜索

统一方案：
- 新建 GlobalSearch 组件
- 支持 Ctrl+K 快捷键
- 集成到 AppHeader

## MODIFIED Requirements

### Requirement: AppHeader 组件增强
现有 AppHeader 组件 SHAL L新增以下功能：
- 面包屑导航支持
- 全局搜索入口
- 通知图标（带未读数徽章）
- 用户菜单下拉

#### Scenario: 面包屑导航
- **GIVEN** AppHeader 配置了 breadcrumbs
- **WHEN** 渲染页面
- **THEN** 显示面包屑导航，可点击跳转

#### Scenario: 用户菜单交互
- **GIVEN** 用户点击用户头像
- **WHEN** 菜单打开
- **THEN** 显示下拉菜单，包含用户信息和操作选项

## Implementation Notes

### 组件优先级

| 优先级 | 组件 | 工作量 | 说明 |
|--------|------|--------|------|
| P0 | AppShell | 中 | 全局容器 |
| P0 | AppHeader | 小 | 顶部导航栏 |
| P0 | AppTabs | 中 | 多页面 Tab |
| P0 | BreadcrumbNav | 小 | 面包屑 |
| P1 | PageHeader | 小 | 页面标题 |
| P1 | UserMenu | 小 | 用户菜单 |
| P1 | GlobalSearch | 中 | 全局搜索 |

### 依赖关系

```
AppShell
  ├── AppHeader
  │     ├── BreadcrumbNav
  │     ├── GlobalSearch
  │     ├── UserMenu
  │     └── NotificationPanel
  │
  ├── AppTabs
  │     └── TabItem
  │
  └── PageHeader
        ├── BreadcrumbNav
        └── ActionButtons
```

### 状态管理

使用 Pinia Store 管理全局状态：

```typescript
// stores/appStore.ts
interface AppState {
  // 侧边栏
  sidebarCollapsed: boolean
  sidebarWidth: number
  
  // Tab 管理
  tabs: Tab[]
  activeTabId: string
  
  // 用户
  currentUser: User | null
  notifications: Notification[]
  unreadCount: number
  
  // 搜索
  searchQuery: string
  searchResults: SearchResult[]
}
```

### 路由集成

使用 Vue Router 的 beforeEach 守卫管理 Tab：

```typescript
router.beforeEach((to, from, next) => {
  // 检查是否需要打开新 Tab
  if (to.meta.openInNewTab) {
    appStore.openTab({
      id: to.path,
      label: to.meta.title,
      path: to.fullPath
    })
    return false // 阻止导航，由 Tab 管理
  }
  
  next()
})
```

##### 参考文档

- SAP Fiori Shell: https://experience.sap.com/fiori-design/article/shell/
- Salesforce Console: https://www.lightningdesignsystem.com/templates/#console
- Microsoft Dynamics 365: https://docs.microsoft.com/en-us/powerapps/maker/model-driven-apps/
- Workday Design System: Internal
- ServiceNow: https://developer.servicenow.com/dev.do

## UI 规范遵循

### 设计原则
遵循 **YonDesign Element Plus** 圆润风格规范，确保全项目视觉一致性。

### 主题色
| 变量名 | 色值 | 用途 |
|--------|------|------|
| `--yonyou-orange-50` | `#fff7ed` | 极淡背景 |
| `--yonyou-orange-100` | `#ffedd5` | 淡背景 |
| `--yonyou-orange-600` | `#ea580c` | **主色** |
| `--yonyou-orange-700` | `#c2410c` | 深色 |

### 间距规范
| 变量名 | 值 |
|--------|-----|
| `--spacing-xs` | 4px |
| `--spacing-sm` | 8px |
| `--spacing-md` | 16px |
| `--spacing-lg` | 24px |
| `--spacing-xl` | 32px |

### 圆角规范
| 组件类型 | 圆角 |
|----------|------|
| 按钮/输入框/选择器 | 6px |
| 标签/分页/下拉项 | 4px |
| 卡片/弹窗/抽屉 | 8px |
| 圆形按钮 | 9999px |

### AppHeader 规范
| 区域 | 组件 | 说明 |
|------|------|------|
| 左侧 | Logo + 面包屑 | 品牌标识 + 路径导航 |
| 中央 | 全局搜索框 | Ctrl+K 快捷键 |
| 右侧 | 通知 + 用户菜单 | 消息提醒 + 用户操作 |

### AppHeader 样式
```scss
.app-header {
  height: 56px;
  background: #fff;
  border-bottom: 1px solid var(--el-border-color);
  padding: 0 var(--spacing-lg);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
```

### AppTabs 规范
| 特性 | 值 |
|------|-----|
| 最大 Tab 数 | 10 |
| 可见 Tab 数 | 8 |
| 超出显示 | 更多下拉菜单 |
| 关闭按钮 | 显示 |
| 固定 Tab | 支持 |
| 状态持久化 | localStorage |

### AppTabs 样式
```scss
.app-tabs {
  background: var(--el-bg-color);
  border-bottom: 1px solid var(--el-border-color);
  display: flex;
  align-items: center;
  padding: 0 var(--spacing-md);
}

.tab-item {
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: 6px;
  transition: background-color 0.2s;
  
  &.active {
    background: rgba(234, 88, 12, 0.06);
    color: var(--yonyou-orange-600);
  }
}
```

### Link 按钮规范（操作列）
| 状态 | 文字色 | 背景色 |
|------|---------|--------|
| 默认 | `--yonyou-orange-600` | 透明 |
| Hover | `--yonyou-orange-600` | `rgba(234,88,12,0.06)` |
| Focus | `--yonyou-orange-600` | `rgba(234,88,12,0.12)` |
| Active | `--yonyou-orange-600` | `rgba(234,88,12,0.16)` |

### 实现位置
样式实现位于 `src/styles/yon-ep.scss`，自动应用于所有 Element Plus 元素。

### 设计原则
- **Link 按钮**：文字颜色固定为橙色，hover/focus/active 只改变背景透明度
- **文字颜色不变**：确保可读性和对比度稳定
- **渐进式反馈**：通过背景深浅（6% < 12% < 16%）表达交互状态

## 实现状态

### 已完成 ✅

| 组件/功能 | 状态 | 实现位置 | 完成日期 |
|-----------|------|---------|---------|
| AppShell 组件 | ✅ 已完成 | `src/components/common/AppShell/AppShell.vue` | 2026-05-14 |
| AppHeader 组件 | ✅ 已完成 | `src/components/common/AppHeader/AppHeader.vue` | 2026-05-14 |
| AppTabs 组件 | ✅ 已完成 | `src/components/common/AppTabs/AppTabs.vue` | 2026-05-14 |
| BreadcrumbNav 组件 | ✅ 已完成 | `src/components/common/BreadcrumbNav/BreadcrumbNav.vue` | 2026-05-14 |
| UserMenu 组件 | ✅ 已完成 | `src/components/common/UserMenu/UserMenu.vue` | 2026-05-14 |
| GlobalSearch 组件 | ✅ 已完成 | `src/components/common/GlobalSearch/GlobalSearch.vue` | 2026-05-14 |
| AppLayout 包装组件 | ✅ 已完成 | `src/components/common/AppLayout/AppLayout.vue` | 2026-05-14 |
| Pinia Store (appStore) | ✅ 已完成 | `src/stores/appStore.ts` | 2026-05-14 |
| 路由守卫集成 | ✅ 已完成 | `src/router/index.js` | 2026-05-14 |
| 组件导出配置 | ✅ 已完成 | `src/components/common/index.js` | 2026-05-14 |
| 集成指南文档 | ✅ 已完成 | `.trae/specs/top-navigation-architecture/INTEGRATION_GUIDE.md` | 2026-05-14 |

### 待完成

| 任务 | 优先级 | 说明 |
|------|--------|------|
| 集成到现有应用 | 高 | 需要在 App.vue 或具体页面中使用新组件 |
| 测试功能 | 中 | 进行功能测试和兼容性测试 |
| 页面级 Header 迁移 | 低 | 将现有页面 Header 迁移到 AppHeader |

### 使用示例

参考集成指南：`.trae/specs/top-navigation-architecture/INTEGRATION_GUIDE.md`

### 注意事项

1. **向后兼容**：旧的 AppHeader.vue 仍保留在 `src/components/common/` 目录
2. **新组件命名**：新创建的完整导航组件导出为 `TopNavHeader`
3. **布局组件**：AppLayout 提供了开箱即用的完整布局解决方案
4. **状态持久化**：Tab 状态自动保存到 localStorage


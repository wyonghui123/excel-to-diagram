---
title: Top Tab Redesign Phase A - 用户与权限管理升级为顶级菜单 + Tab 重复检测
version: 1.0
date: 2026-06-20
status: Implementation Ready
branch: fix/top-tab-phase-a-2026-06-20
worktree: d:\filework\detail-edit-tab-fix
related:
  - docs/architecture/13-top-navigation-architecture.md
  - .trae/specs/top-navigation-architecture/spec.md
  - meta/scripts/init_menu_permissions.py
  - src/stores/tabStore.ts
  - src/router/modules/business.js
  - src/router/index.js
---

# Spec: Top Tab Redesign Phase A

## 1. Why

当前系统存在两个与"用户与权限管理"相关的体验问题：

1. **菜单层级问题**: "用户与权限管理" 挂在 "系统管理" 分组下，导致侧边栏和顶部 Tab 同时出现两个"用户与权限管理"入口（分组内子菜单 + 独立 Tab），造成视觉重复和导航混乱。
2. **Tab 重复问题**: 多对象 Hub 页（如 `/user-permission/:tab?`）在切换子 Tab 时，路由路径从 `/user-permission` 变为 `/user-permission/users`，`tabStore` 按路径去重，导致同一个 Hub 页被打开成两个 Tab。

本阶段（Phase A）先解决这两个具体问题，为后续完整 top tab 设计打好基础。

## 2. What Changes

### 2.1 A 方案：将"用户与权限管理"改为顶级菜单

- **后端**：修改 `meta/scripts/init_menu_permissions.py` 中 `user-permission` 菜单的 `parent_menu` 从 `'system'` 改为 `''`（空字符串）。
- **影响**：
  - `menus` 表和 `menu_permissions` 表同步更新（脚本会同时写入两表）。
  - `/api/v1/menu-permission/visible` 返回的菜单树中，`user-permission` 成为顶级节点，不再作为 `system` 的子节点。
  - 侧边栏 `AppSideNav` 直接在顶级显示"用户与权限管理"。
  - "系统管理"分组下不再包含"用户与权限管理"，避免重复显示。

### 2.2 Tab 重复检测增强

- **目标**：多对象 Hub 页（`/user-permission/:tab?`、`/business-config/:tab?`）及其子路径（如 `/user-permission/users`）只产生一个 Tab。
- **实现**：
  1. 在 `src/router/modules/business.js` 的 Hub 路由上增加 `meta.baseTabPath`，指定稳定的 Tab ID（如 `/user-permission`）。
  2. 在 `src/router/index.js` 的 `beforeEach` 中，使用 `to.meta.baseTabPath || to.path` 作为 Tab ID。
  3. 在 `src/stores/tabStore.ts` 的 `openTab` 中，当命中已有 Tab 时，若调用方提供了新的 `path`，则更新现有 Tab 的 `path`，确保 Tab 的 URL 始终与当前子 Tab 同步。

## 3. Impact

### Affected Capabilities
- 侧边栏导航层级
- 多对象 Hub 页的 Tab 行为
- 顶部 Tab 栏去重

### Affected Code
- `meta/scripts/init_menu_permissions.py`
- `src/router/modules/business.js`
- `src/router/index.js`
- `src/stores/tabStore.ts`
- `src/stores/__tests__/tabStore.spec.js`（新增/更新测试）

## 4. ADDED Requirements

### Requirement: 用户与权限管理为顶级菜单

系统 SHALL 将"用户与权限管理"菜单显示为侧边栏顶级菜单，不再折叠在"系统管理"分组下。

#### Scenario: 侧边栏导航
- **GIVEN** 用户已登录且有权限
- **WHEN** 侧边栏加载完成
- **THEN** "用户与权限管理"出现在顶级菜单列表
- **AND** "系统管理"分组下不再包含"用户与权限管理"

### Requirement: Hub 页子 Tab 不产生重复 Tab

系统 SHALL 确保多对象 Hub 页的子 Tab 切换不会生成多个 Tab。

#### Scenario: 切换 Hub 子 Tab
- **GIVEN** 用户已打开"用户与权限管理" Tab（路径 `/user-permission`）
- **WHEN** 用户点击"角色管理"子 Tab，路径变为 `/user-permission/roles`
- **THEN** 顶部 Tab 栏仍只有一个"用户与权限管理" Tab
- **AND** 点击该 Tab 时回到当前子 Tab（`/user-permission/roles`）

## 5. EXISTING System Integration

### 元数据驱动菜单
- 菜单层级由 `menus` 表的 `parent_menu` 字段决定。
- `init_menu_permissions.py` 初始化时同时写入 `menu_permissions` 和 `menus`。
- 前端 `useMenuPermissions` 通过 `/api/v1/menu-permission/visible` 获取树形菜单。
- `AppRootLayout.vue` 的 `apiNavigationItems` 直接使用返回的树，渲染侧边栏。

### Tab 管理
- `tabStore.openTab` 当前按 `id`（默认 `path`）去重。
- `router/index.js` 的 `beforeEach` 在路由切换时自动打开/切换 Tab。
- `GenericTabContainer.vue` 内部使用 `SubNavTabs` 切换子 Tab，并通过 `router.replace` 更新 URL 参数。

## 6. MODIFIED Requirements

### Requirement: TabStore 重复检测增强

现有 `tabStore.openTab` 在命中已有 Tab 时只更新 `label`、`closable`、`pinned`。

现在 SHALL 额外更新 `path`（当调用方显式提供时），以支持 Hub 页子 Tab 路径同步。

#### Scenario: 同一 Hub Tab 路径变化
- **GIVEN** 已存在 id 为 `/user-permission` 的 Tab，path 为 `/user-permission`
- **WHEN** 调用 `openTab({ id: '/user-permission', path: '/user-permission/users', label: '用户与权限管理' })`
- **THEN** 不新建 Tab
- **AND** 现有 Tab 的 path 更新为 `/user-permission/users`
- **AND** 该 Tab 被激活

## 7. Implementation Notes

### 7.1 后端菜单修改

文件：`meta/scripts/init_menu_permissions.py`

```python
{
    'menu_code': 'user-permission',
    'menu_name': '用户与权限管理',
    'menu_path': '/user-permission',
    'icon': 'User',
    'color': '#ef4444',
    'sort_order': 51,
    'parent_menu': '',  # 从 'system' 改为空字符串
    # ...
}
```

### 7.2 路由配置增强

文件：`src/router/modules/business.js`

```javascript
{
  path: '/user-permission/:tab?',
  name: 'user-permission',
  component: () => import('@/views/GenericTabContainer.vue'),
  props: { group: 'user-permission' },
  meta: {
    title: '用户与权限管理',
    requiresAuth: true,
    requiresAdmin: true,
    baseTabPath: '/user-permission'
  }
},
{
  path: '/business-config/:tab?',
  name: 'business-config',
  component: () => import('@/views/GenericTabContainer.vue'),
  props: { group: 'business-config' },
  meta: {
    title: '业务配置',
    requiresAuth: true,
    requiresAdmin: true,
    baseTabPath: '/business-config'
  }
}
```

### 7.3 Router Guard 使用 baseTabPath

文件：`src/router/index.js`

在 `beforeEach` 中打开 Tab 前：

```javascript
const tabId = to.meta.baseTabPath || to.path
const existingTab = tabStore.tabs.find(t => t.id === tabId)
// ... 使用 tabId 替代 to.path
```

### 7.4 TabStore 更新 path

文件：`src/stores/tabStore.ts`

在 `openTab` 命中已有 Tab 时：

```typescript
if (existing) {
  // 现有 label/closable/pinned 更新逻辑保留
  if (tab.path && existing.path !== tab.path) {
    existing.path = tab.path
  }
  activeTabId.value = existing.id
  return existing
}
```

## 8. Verification

### 8.1 手动验证步骤

1. 启动后端和前端。
2. 重新初始化菜单权限（或执行 `POST /api/v1/meta/reload` 后硬刷新浏览器）。
3. 登录 admin。
4. 检查侧边栏：
   - "用户与权限管理"应位于顶级。
   - "系统管理"分组下不应有"用户与权限管理"。
5. 点击"用户与权限管理"：顶部 Tab 栏出现一个 Tab。
6. 点击子 Tab（如"角色管理"）：URL 变为 `/user-permission/roles`，顶部仍只有一个 Tab。
7. 点击顶部该 Tab：页面回到 `/user-permission/roles`。

### 8.2 自动测试

- 更新 `src/stores/__tests__/tabStore.spec.js`，新增：
  - `openTab 命中已有 tab 时更新 path`
  - `Hub 子路径变化不新建 tab`

## 9. Migration Notes

- 已部署环境需要重新运行 `init_menu_permissions.py` 或执行 `/api/v1/meta/reload` 使菜单表更新。
- 用户本地缓存的 `menuCache` 可能在硬刷新前显示旧层级，建议验证时硬刷新浏览器。

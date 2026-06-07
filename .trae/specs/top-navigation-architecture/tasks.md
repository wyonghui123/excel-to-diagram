# 顶部导航架构实施任务清单

## 设计规范遵循

### 样式规范
遵循 `src/styles/yon-ep.scss` 中的圆润风格规范：
- 圆角：6px（按钮/输入框）、4px（标签/分页）
- 间距：使用 CSS 变量 `--spacing-*`
- 颜色：使用 `--yonyou-orange-600` 主色
- 字体：使用 `--font-size-*` 变量

### UI 规范
| 组件 | 圆角 | 间距 | 主色 |
|------|------|------|------|
| AppHeader | 6px | 24px | `#ea580c` |
| AppTabs | 6px | 8px | `#ea580c` |
| 按钮 | 6px | 8px | `#ea580c` |
| 面包屑 | - | 8px | `#ea580c` |
| 用户菜单 | 4px | 8px | `#ea580c` |

## Phase 1: 基础架构 (P0)

### Task 1.1: 创建 AppShell 全局容器组件
创建 AppShell.vue 作为应用的顶层容器组件。

- [ ] Task 1.1.1: 创建 AppShell 组件基础结构
  - 创建 src/components/common/AppShell/AppShell.vue
  - 定义 props: logo, showSidebar, showTabs
  - 实现基本布局结构
  - 添加 scoped 样式

- [ ] Task 1.1.2: 集成 Pinia Store
  - 创建 src/stores/appStore.ts
  - 定义 AppState 接口
  - 实现状态管理和持久化

### Task 1.2: 创建 AppHeader 组件
创建 AppHeader.vue 作为顶部导航栏。

- [ ] Task 1.2.1: 创建 AppHeader 组件基础结构
  - 创建 src/components/common/AppHeader/AppHeader.vue
  - 定义 props: breadcrumbs, user, notifications
  - 实现左侧 Logo 区域
  - 实现右侧用户菜单区域

- [ ] Task 1.2.2: 添加面包屑支持
  - 集成 BreadcrumbNav 组件
  - 配置面包屑点击跳转

- [ ] Task 1.2.3: 添加用户菜单支持
  - 集成 UserMenu 组件
  - 配置用户信息显示

### Task 1.3: 创建 AppTabs 多页面 Tab 组件
创建 AppTabs.vue 支持多页面管理。

- [ ] Task 1.3.1: 创建基础 Tab 结构
  - 创建 src/components/common/AppTabs/AppTabs.vue
  - 定义 Tab 数据结构
  - 实现 Tab 渲染

- [ ] Task 1.3.2: 添加 Tab 交互功能
  - Tab 切换
  - Tab 关闭
  - Tab 固定（pinned）

- [ ] Task 1.3.3: 添加 Tab 溢出处理
  - 限制最大 Tab 数量（10 个）
  - 超过限制显示"更多"下拉菜单
  - Tab 拖拽排序

### Task 1.4: 创建 BreadcrumbNav 面包屑组件
创建 BreadcrumbNav.vue 统一面包屑导航。

- [ ] Task 1.4.1: 创建 BreadcrumbNav 组件
  - 创建 src/components/common/BreadcrumbNav/BreadcrumbNav.vue
  - 支持配置分隔符
  - 支持最大显示数量
  - 支持省略号

- [ ] Task 1.4.2: 集成 Vue Router
  - 使用 matched routes 自动生成面包屑
  - 支持手动配置

## Phase 2: 功能增强 (P0)

### Task 2.1: 创建 UserMenu 用户菜单组件
创建 UserMenu.vue 提供用户菜单。

- [ ] Task 2.1.1: 创建 UserMenu 组件
  - 创建 src/components/common/UserMenu/UserMenu.vue
  - 实现下拉菜单结构
  - 支持菜单项配置

- [ ] Task 2.1.2: 添加菜单项
  - 个人资料
  - 设置
  - 退出登录

### Task 2.2: 创建 GlobalSearch 全局搜索组件
创建 GlobalSearch.vue 提供全局搜索功能。

- [ ] Task 2.2.1: 创建 GlobalSearch 组件
  - 创建 src/components/common/GlobalSearch/GlobalSearch.vue
  - 实现搜索输入框
  - 添加快捷键支持（Ctrl+K）

- [ ] Task 2.2.2: 添加搜索建议
  - 最近搜索
  - 搜索建议下拉
  - 搜索结果高亮

### Task 2.3: 创建 PageHeader 页面标题组件
创建 PageHeader.vue 提供页面级标题。

- [ ] Task 2.3.1: 创建 PageHeader 组件
  - 创建 src/components/common/PageHeader/PageHeader.vue
  - 标题和副标题
  - 返回按钮
  - 操作按钮插槽

## Phase 3: 系统集成 (P1)

### Task 3.1: 替换现有 Header
将现有 Header 替换为新的 AppHeader。

- [ ] Task 3.1.1: 分析现有 Header 使用情况
  - 检查 AppHeader.vue 的使用位置
  - 检查 ArchWorkspace.vue 的 Header
  - 制定替换计划

- [ ] Task 3.1.2: 替换 AppHeader
  - 替换所有使用 AppHeader 的页面
  - 确保功能兼容

### Task 3.2: 集成多页面 Tab 功能
在现有系统中集成 AppTabs。

- [ ] Task 3.2.1: 改造路由系统
  - 修改路由配置支持 openInNewTab meta
  - 添加路由守卫

- [ ] Task 3.2.2: 集成 Tab Store
  - 在 AppShell 中集成 Tab 状态
  - 实现 Tab 状态持久化

### Task 3.3: 统一面包屑导航
替换现有面包屑实现。

- [ ] Task 3.3.1: 分析现有面包屑实现
  - 检查各页面的面包屑实现
  - 制定统一方案

- [ ] Task 3.3.2: 统一使用 BreadcrumbNav
  - 替换现有面包屑实现
  - 确保功能兼容

## Phase 4: 优化和测试 (P1)

### Task 4.1: 键盘快捷键支持
添加常用快捷键。

- [ ] Task 4.1.1: 实现全局快捷键
  - Ctrl+K: 全局搜索
  - Ctrl+T: 新建 Tab
  - Ctrl+W: 关闭当前 Tab
  - Ctrl+Tab: 切换 Tab

- [ ] Task 4.1.2: 快捷键提示
  - 显示快捷键提示
  - 提供快捷键设置

### Task 4.2: 状态持久化
保存用户偏好设置。

- [ ] Task 4.2.1: Tab 状态持久化
  - 保存打开的 Tab
  - 保存激活的 Tab
  - 恢复上次会话

- [ ] Task 4.2.2: 用户偏好持久化
  - 侧边栏折叠状态
  - 主题偏好
  - 最近访问

### Task 4.3: 测试和修复
全面测试并修复问题。

- [ ] Task 4.3.1: 单元测试
  - 各组件单元测试
  - Store 单元测试

- [ ] Task 4.3.2: 集成测试
  - 路由集成测试
  - 状态管理测试

- [ ] Task 4.3.3: E2E 测试
  - Tab 操作流程测试
  - 面包屑导航测试
  - 用户菜单测试

# Task Dependencies

- Task 1.2 depends on Task 1.1
- Task 1.3 depends on Task 1.1
- Task 1.4 depends on Task 1.2
- Task 2.1 depends on Task 1.1
- Task 2.2 depends on Task 1.1
- Task 2.3 depends on Task 1.1
- Task 3.1 depends on Task 1.2
- Task 3.2 depends on Task 1.3
- Task 3.3 depends on Task 1.4
- Task 4.1 depends on Task 1.2, Task 2.1, Task 2.2
- Task 4.2 depends on Task 4.1
- Task 4.3 depends on Task 4.2

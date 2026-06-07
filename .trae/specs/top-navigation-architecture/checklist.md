# 顶部导航架构实施检查清单

## UI 规范检查

### 样式检查
- [ ] 遵循 `--spacing-*` 间距变量（xs: 4px, sm: 8px, md: 16px, lg: 24px）
- [ ] 遵循 `--yonyou-orange-600` 主色
- [ ] 圆角符合规范（按钮: 6px, 标签: 4px）
- [ ] 使用 `--font-size-*` 变量定义字号

### 组件检查
- [ ] AppHeader 高度 56px
- [ ] AppTabs Tab 间距 8px
- [ ] AppTabs 圆角 6px
- [ ] 用户菜单圆角 4px
- [ ] Link 按钮样式符合规范（固定文字色，hover 背景透明度 6%）

## Phase 1: 基础架构检查

### AppShell 组件检查

### AppShell 组件检查
- [ ] AppShell.vue 文件创建完成
- [ ] AppShell.vue 样式正确（Flex 布局）
- [ ] AppShell.vue 支持 sidebar 和 tabs 属性
- [ ] AppShell.vue 支持 router-view 渲染
- [ ] AppShell.vue 支持响应式布局

### AppHeader 组件检查
- [ ] AppHeader.vue 文件创建完成
- [ ] AppHeader.vue 左侧区域包含 Logo 和面包屑
- [ ] AppHeader.vue 右侧区域包含通知和用户菜单
- [ ] AppHeader.vue 样式与现有系统一致
- [ ] AppHeader.vue 支持自定义 slot

### AppTabs 组件检查
- [ ] AppTabs.vue 文件创建完成
- [ ] AppTabs 支持添加新 Tab
- [ ] AppTabs 支持关闭 Tab
- [ ] AppTabs 支持切换激活 Tab
- [ ] AppTabs 支持固定 Tab
- [ ] AppTabs 支持溢出处理（超过 8 个显示"更多"菜单）
- [ ] AppTabs 限制最大 Tab 数量为 10 个

### BreadcrumbNav 组件检查
- [ ] BreadcrumbNav.vue 文件创建完成
- [ ] BreadcrumbNav 支持配置分隔符
- [ ] BreadcrumbNav 支持最大显示数量
- [ ] BreadcrumbNav 支持省略号
- [ ] BreadcrumbNav 路径可点击跳转

## Phase 2: 功能增强检查

### UserMenu 组件检查
- [ ] UserMenu.vue 文件创建完成
- [ ] UserMenu 显示用户头像和名称
- [ ] UserMenu 显示下拉菜单
- [ ] UserMenu 包含个人资料入口
- [ ] UserMenu 包含设置入口
- [ ] UserMenu 包含退出登录入口

### GlobalSearch 组件检查
- [ ] GlobalSearch.vue 文件创建完成
- [ ] GlobalSearch 支持 Ctrl+K 快捷键
- [ ] GlobalSearch 显示搜索建议下拉
- [ ] GlobalSearch 支持最近搜索

### PageHeader 组件检查
- [ ] PageHeader.vue 文件创建完成
- [ ] PageHeader 支持标题和副标题
- [ ] PageHeader 支持返回按钮
- [ ] PageHeader 支持操作按钮插槽

## Phase 3: 系统集成检查

### 路由集成检查
- [ ] 路由配置支持 openInNewTab meta
- [ ] beforeEach 守卫正确处理 Tab 导航
- [ ] 路由变化正确更新 Tab

### 状态管理检查
- [ ] appStore.ts 创建完成
- [ ] Tab 状态管理正确
- [ ] 用户状态管理正确
- [ ] 状态持久化工作

### 现有组件替换检查
- [ ] AppHeader 替换完成
- [ ] 面包屑统一使用 BreadcrumbNav
- [ ] 功能无回退

## Phase 4: 优化检查

### 键盘快捷键检查
- [ ] Ctrl+K 打开全局搜索
- [ ] Ctrl+T 新建 Tab
- [ ] Ctrl+W 关闭当前 Tab
- [ ] Ctrl+Tab 切换 Tab
- [ ] 快捷键提示显示

### 状态持久化检查
- [ ] Tab 状态持久化
- [ ] 用户偏好持久化
- [ ] 状态恢复正确

### 测试检查
- [ ] 单元测试通过
- [ ] 集成测试通过
- [ ] E2E 测试通过
- [ ] 性能测试通过

## 视觉检查

### AppShell
- [ ] Logo 正确显示
- [ ] 布局比例正确
- [ ] 响应式适配正确

### AppHeader
- [ ] 高度统一（48px 或 56px）
- [ ] Logo 和面包屑左对齐
- [ ] 搜索、通知、用户右对齐
- [ ] 间距一致

### AppTabs
- [ ] Tab 宽度合适
- [ ] 关闭按钮可见
- [ ] 激活状态高亮
- [ ] 溢出菜单正确

### 面包屑
- [ ] 分隔符一致
- [ ] 文字大小合适
- [ ] 链接样式正确
- [ ] 当前页高亮

### 用户菜单
- [ ] 头像正确显示
- [ ] 下拉菜单样式正确
- [ ] 菜单项间距合适
- [ ] 退出登录样式突出

### 全局搜索
- [ ] 搜索框样式正确
- [ ] 建议下拉正确
- [ ] 快捷键提示显示

## 兼容性检查

### 浏览器兼容
- [ ] Chrome 最新版正常
- [ ] Firefox 最新版正常
- [ ] Safari 最新版正常
- [ ] Edge 最新版正常

### 响应式兼容
- [ ] 桌面端正常
- [ ] 平板端正常
- [ ] 手机端降级处理

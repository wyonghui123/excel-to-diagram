# Tasks

## Phase 1: 基础增强（第1-2周）

- [x] Task 1.1: MetaTable 多选功能 - 为表格添加行选择功能
  - [x] SubTask 1.1.1: 添加 `selectable`、`selectedKeys`、`rowKey` 属性
  - [x] SubTask 1.1.2: 实现复选框列渲染
  - [x] SubTask 1.1.3: 实现全选/取消全选逻辑
  - [x] SubTask 1.1.4: 添加 `selection-change` 事件
  - [x] SubTask 1.1.5: 编写单元测试

- [x] Task 1.2: MetaTable 完整分页 - 为表格添加完整分页功能
  - [x] SubTask 1.2.1: 添加 `pagination` 属性（对象类型）
  - [x] SubTask 1.2.2: 实现分页器UI组件
  - [x] SubTask 1.2.3: 添加 `page-change`、`page-size-change` 事件
  - [x] SubTask 1.2.4: 支持每页条数切换
  - [x] SubTask 1.2.5: 编写单元测试

- [x] Task 1.3: MetaForm 条件显示 - 为表单添加字段条件显示功能
  - [x] SubTask 1.3.1: 添加 `fieldVisibility` 属性
  - [x] SubTask 1.3.2: 实现字段动态显示/隐藏逻辑
  - [x] SubTask 1.3.3: 隐藏字段不参与验证
  - [x] SubTask 1.3.4: 编写单元测试

- [x] Task 1.4: MetaForm 字段联动 - 为表单添加字段联动功能
  - [x] SubTask 1.4.1: 添加 `fieldDependencies` 属性
  - [x] SubTask 1.4.2: 实现字段变化监听
  - [x] SubTask 1.4.3: 提供 `setFieldValue` 方法
  - [x] SubTask 1.4.4: 编写单元测试

## Phase 2: 组件增强（第3-4周）

- [x] Task 2.1: AppSelect 选项分组 - 为选择器添加选项分组功能
  - [x] SubTask 2.1.1: 支持分组选项格式
  - [x] SubTask 2.1.2: 实现分组UI渲染
  - [x] SubTask 2.1.3: 保持扁平选项兼容
  - [x] SubTask 2.1.4: 编写单元测试

- [x] Task 2.2: AppTabs 溢出处理 - 为Tab添加溢出处理功能
  - [x] SubTask 2.2.1: 添加 `overflowMode` 属性
  - [x] SubTask 2.2.2: 实现下拉菜单模式
  - [x] SubTask 2.2.3: 实现滚动模式
  - [x] SubTask 2.2.4: 编写单元测试

- [x] Task 2.3: AppSideNav 折叠功能 - 为侧边导航添加折叠功能
  - [x] SubTask 2.3.1: 添加 `collapsible`、`collapsed` 属性
  - [x] SubTask 2.3.2: 实现折叠/展开动画
  - [x] SubTask 2.3.3: 折叠时仅显示图标
  - [x] SubTask 2.3.4: 编写单元测试

- [x] Task 2.4: AppInput 密码显示切换 - 为输入框添加密码显示切换
  - [x] SubTask 2.4.1: 添加 `showPasswordToggle` 属性
  - [x] SubTask 2.4.2: type="password" 时自动显示切换按钮
  - [x] SubTask 2.4.3: 编写单元测试

## Phase 3: 新增组件（第5-6周）

- [x] Task 3.1: MasterDetailLayout 布局组件 - 创建左右布局组件
  - [x] SubTask 3.1.1: 创建组件文件结构
  - [x] SubTask 3.1.2: 实现左右布局插槽
  - [x] SubTask 3.1.3: 添加侧边栏折叠功能
  - [x] SubTask 3.1.4: 支持自定义宽度
  - [x] SubTask 3.1.5: 编写单元测试

- [x] Task 3.2: Pagination 分页组件 - 创建独立分页组件
  - [x] SubTask 3.2.1: 创建组件文件结构
  - [x] SubTask 3.2.2: 实现分页器UI
  - [x] SubTask 3.2.3: 支持每页条数切换
  - [x] SubTask 3.2.4: 支持快速跳转
  - [x] SubTask 3.2.5: 编写单元测试

- [x] Task 3.3: Drawer 抽屉组件 - 创建右侧抽屉组件
  - [x] SubTask 3.3.1: 创建组件文件结构
  - [x] SubTask 3.3.2: 实现滑出动画
  - [x] SubTask 3.3.3: 支持ESC关闭
  - [x] SubTask 3.3.4: 支持自定义宽度和位置
  - [x] SubTask 3.3.5: 编写单元测试

## Phase 4: 可访问性增强（第7周）

- [x] Task 4.1: MetaTable ARIA 属性 - 添加表格可访问性属性
  - [x] SubTask 4.1.1: 添加 `role="grid"`
  - [x] SubTask 4.1.2: 添加 `aria-sort` 排序状态
  - [x] SubTask 4.1.3: 添加 `aria-selected` 选中状态

- [x] Task 4.2: MetaForm ARIA 属性 - 添加表单可访问性属性
  - [x] SubTask 4.2.1: 添加 `aria-invalid` 验证状态
  - [x] SubTask 4.2.2: 添加 `aria-describedby` 错误提示关联

- [x] Task 4.3: AppModal 焦点管理 - 实现焦点陷阱
  - [x] SubTask 4.3.1: 添加 `role="dialog"` 和 `aria-modal="true"`
  - [x] SubTask 4.3.2: 实现焦点陷阱（Focus Trap）
  - [x] SubTask 4.3.3: 打开时聚焦第一个可聚焦元素

- [x] Task 4.4: AppSelect ARIA 属性 - 添加选择器可访问性属性
  - [x] SubTask 4.4.1: 添加 `aria-expanded`
  - [x] SubTask 4.4.2: 添加 `aria-activedescendant`

## Phase 5: 迁移与清理（第8周）

- [x] Task 5.1: 迁移指南编写 - 提供组件迁移文档
  - [x] SubTask 5.1.1: DataTable 到 MetaTable 迁移指南
  - [x] SubTask 5.1.2: EditForm 到 MetaForm 迁移指南
  - [x] SubTask 5.1.3: 内联Dialog 到 AppModal 迁移指南

- [x] Task 5.2: 重复组件清理 - 清理 ArchDataManageApp 重复组件
  - [x] SubTask 5.2.1: 移除 `ArchDataManageApp/components/ConfirmDialog.vue`（使用公共组件）
  - [x] SubTask 5.2.2: 评估 ExportDialog/ImportDialog 是否可迁移到公共组件

- [x] Task 5.3: 文档更新 - 更新组件文档
  - [x] SubTask 5.3.1: 更新 UI_COMPONENT_GUIDELINES.md
  - [x] SubTask 5.3.2: 更新组件使用示例
  - [x] SubTask 5.3.3: 更新 index.js 导出新组件

# Task Dependencies

- Task 1.2 依赖于 Task 1.1（分页组件可能在多选后使用）
- Task 1.4 依赖于 Task 1.3（字段联动可能使用条件显示逻辑）
- Task 3.1 可以与 Phase 1 并行执行（新组件，无依赖）
- Task 3.2 可以与 Task 3.1 并行执行
- Task 3.3 可以与 Task 3.1 并行执行
- Task 4.x 依赖于 Phase 1-3 完成（需要组件稳定后再添加ARIA）
- Task 5.x 依赖于 Phase 1-4 完成

# 并行执行建议

以下任务可以并行执行：
- Task 1.1 和 Task 1.3（MetaTable 和 MetaForm 独立）
- Task 3.1、Task 3.2、Task 3.3（三个新组件独立）
- Task 4.1、Task 4.2、Task 4.3、Task 4.4（不同组件的ARIA独立）

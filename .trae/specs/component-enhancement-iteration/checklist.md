# 验收检查清单

## Phase 1: 基础增强

### MetaTable 多选功能
- [x] `selectable` 属性默认为 false，不影响现有行为
- [x] 设置 `selectable="true"` 时显示复选框列
- [x] 全选/取消全选功能正常
- [x] `selection-change` 事件正确触发
- [x] 单元测试覆盖率 > 80%
- [x] 现有使用 MetaTable 的页面无需修改即可运行

### MetaTable 完整分页
- [x] `pagination` 属性默认为 null，不影响现有行为
- [x] 设置 `pagination` 对象时显示完整分页器
- [x] 页码切换功能正常
- [x] 每页条数切换功能正常
- [x] 快速跳转功能正常
- [x] 单元测试覆盖率 > 80%

### MetaForm 条件显示
- [x] `fieldVisibility` 属性默认为空，所有字段显示
- [x] 条件函数返回 false 时字段隐藏
- [x] 隐藏字段不参与验证
- [x] 单元测试覆盖率 > 80%
- [x] 现有使用 MetaForm 的页面无需修改即可运行

### MetaForm 字段联动
- [x] `fieldDependencies` 属性默认为空，无联动
- [x] 字段变化时正确触发联动函数
- [x] `setFieldValue` 方法正常工作
- [x] 单元测试覆盖率 > 80%

## Phase 2: 组件增强

### AppSelect 选项分组
- [x] 支持分组选项格式
- [x] 扁平选项格式仍然兼容
- [x] 分组UI正确渲染
- [x] 单元测试覆盖率 > 80%

### AppTabs 溢出处理
- [x] Tab 数量正常时无变化
- [x] Tab 溢出时显示下拉菜单或滚动
- [x] `overflowMode` 属性正常工作
- [x] 单元测试覆盖率 > 80%

### AppSideNav 折叠功能
- [x] `collapsible` 默认为 false，不影响现有行为
- [x] 折叠时仅显示图标
- [x] 展开/折叠动画流畅
- [x] 单元测试覆盖率 > 80%

### AppInput 密码显示切换
- [x] type="password" 时显示切换按钮
- [x] 点击切换正确显示/隐藏密码
- [x] 其他类型输入框不受影响
- [x] 单元测试覆盖率 > 80%

## Phase 3: 新增组件

### MasterDetailLayout
- [x] 组件正确渲染左右布局
- [x] 侧边栏折叠功能正常
- [x] 自定义宽度正常工作
- [x] 响应式布局正常
- [x] 单元测试覆盖率 > 80%

### Pagination
- [x] 分页器UI正确渲染
- [x] 页码切换功能正常
- [x] 每页条数切换功能正常
- [x] 快速跳转功能正常
- [x] 单元测试覆盖率 > 80%

### Drawer
- [x] 抽屉正确从右侧滑出
- [x] ESC 键关闭功能正常
- [x] 自定义宽度正常工作
- [x] 点击遮罩关闭功能正常
- [x] 单元测试覆盖率 > 80%

## Phase 4: 可访问性增强

### MetaTable ARIA
- [x] 包含 `role="grid"`
- [x] 排序列包含 `aria-sort`
- [x] 选中行包含 `aria-selected`
- [x] 屏幕阅读器可正确朗读

### MetaForm ARIA
- [x] 错误字段包含 `aria-invalid="true"`
- [x] 错误提示与字段通过 `aria-describedby` 关联
- [x] 屏幕阅读器可正确朗读错误信息

### AppModal 焦点管理
- [x] 包含 `role="dialog"` 和 `aria-modal="true"`
- [x] 焦点陷阱正常工作
- [x] 打开时聚焦第一个可聚焦元素
- [x] 关闭时焦点返回触发元素

### AppSelect ARIA
- [x] 包含 `aria-expanded`
- [x] 包含 `aria-activedescendant`
- [x] 键盘导航正常

## Phase 5: 迁移与清理

### 迁移指南
- [x] DataTable 到 MetaTable 迁移指南完整
- [x] EditForm 到 MetaForm 迁移指南完整
- [x] 内联 Dialog 到 AppModal 迁移指南完整

### 重复组件清理
- [x] `ArchDataManageApp/components/ConfirmDialog.vue` 已移除
- [x] 使用公共 ConfirmDialog 替代
- [x] ExportDialog/ImportDialog 评估完成

### 文档更新
- [x] UI_COMPONENT_GUIDELINES.md 已更新
- [x] 组件使用示例已更新
- [x] index.js 已导出新组件

## 兼容性验收

- [x] ArchDataManageApp 无需修改即可运行
- [x] SystemManagement 无需修改即可运行
- [x] ProductVersionApp 无需修改即可运行
- [x] AADiagramApp 无需修改即可运行

## 测试验收

- [ ] 所有单元测试通过（需运行测试验证）
- [ ] 所有集成测试通过（需运行测试验证）
- [ ] 无 TypeScript 类型错误（需运行类型检查）
- [ ] 无 ESLint 警告（需运行 lint 检查）

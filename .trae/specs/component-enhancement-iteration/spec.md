# 组件增强迭代 Spec

## Why

现有组件与头部企业（SAP Fiori、Salesforce Lightning、Microsoft Fluent UI）存在功能差距，需要系统性地增强组件功能，同时确保对现有应用无影响或最小影响。

主要差距：
1. MetaTable 缺少多选、完整分页等企业级特性
2. MetaForm 缺少条件显示、字段联动功能
3. 缺少布局组件（MasterDetailLayout、Drawer、Pagination）
4. 可访问性（ARIA）不完整

## What Changes

### Phase 1: 基础增强（向后兼容）
- MetaTable 新增多选功能（可选属性，默认不启用）
- MetaTable 新增完整分页（可选属性，默认显示总数）
- MetaForm 新增条件显示（可选属性，默认所有字段显示）
- MetaForm 新增字段联动（可选属性，默认无联动）

### Phase 2: 组件增强（向后兼容）
- AppSelect 新增选项分组
- AppTabs 新增溢出处理
- AppSideNav 新增折叠功能
- AppInput 新增密码显示切换

### Phase 3: 新增组件（无影响）
- 新增 MasterDetailLayout 布局组件
- 新增 Pagination 分页组件
- 新增 Drawer 抽屉组件

### Phase 4: 可访问性增强（向后兼容）
- 所有组件添加完整 ARIA 属性
- 键盘导航增强

### Phase 5: 迁移与清理（需手动迁移）
- 提供迁移指南
- 清理重复组件

## Impact

### 受影响的规范
- 组件 API 设计
- 可访问性标准

### 受影响的代码
- `src/components/common/MetaTable.vue` - 新增属性
- `src/components/common/MetaForm.vue` - 新增属性
- `src/components/common/AppSelect.vue` - 新增属性
- `src/components/common/AppTabs.vue` - 新增属性
- `src/components/common/AppSideNav.vue` - 新增属性
- `src/components/common/AppInput.vue` - 新增属性
- `src/components/common/MasterDetailLayout/` - 新增
- `src/components/common/Pagination/` - 新增
- `src/components/common/Drawer/` - 新增

### 受影响的应用
- **ArchDataManageApp**: Phase 5 需迁移重复组件
- **SystemManagement**: 无影响
- **ProductVersionApp**: 可选升级新功能
- **AADiagramApp**: 无影响

***

## ADDED Requirements

### Requirement: MetaTable 多选功能

系统 SHALL 为 MetaTable 提供行选择功能。

#### Scenario: 启用多选
- **WHEN** 开发者设置 `selectable="true"`
- **THEN** 表格显示复选框列
- **AND** 支持全选/取消全选
- **AND** 触发 `selection-change` 事件

#### Scenario: 默认行为
- **WHEN** 开发者未设置 `selectable` 属性
- **THEN** 表格不显示复选框列
- **AND** 保持原有行为

### Requirement: MetaTable 完整分页

系统 SHALL 为 MetaTable 提供完整分页功能。

#### Scenario: 启用完整分页
- **WHEN** 开发者设置 `pagination` 对象
- **THEN** 显示分页器（首页、上一页、页码、下一页、末页）
- **AND** 支持每页条数切换
- **AND** 支持快速跳转

#### Scenario: 默认行为
- **WHEN** 开发者未设置 `pagination` 属性
- **THEN** 仅显示总数
- **AND** 保持原有行为

### Requirement: MetaForm 条件显示

系统 SHALL 为 MetaForm 提供字段条件显示功能。

#### Scenario: 条件显示字段
- **WHEN** 开发者设置 `fieldVisibility` 配置
- **THEN** 字段根据条件动态显示/隐藏
- **AND** 隐藏字段不参与验证

#### Scenario: 默认行为
- **WHEN** 开发者未设置 `fieldVisibility` 属性
- **THEN** 所有字段显示
- **AND** 保持原有行为

### Requirement: MetaForm 字段联动

系统 SHALL 为 MetaForm 提供字段联动功能。

#### Scenario: 字段联动
- **WHEN** 开发者设置 `fieldDependencies` 配置
- **THEN** 字段值变化时触发联动逻辑
- **AND** 可修改其他字段值

#### Scenario: 默认行为
- **WHEN** 开发者未设置 `fieldDependencies` 属性
- **THEN** 字段独立
- **AND** 保持原有行为

### Requirement: MasterDetailLayout 布局组件

系统 SHALL 提供 MasterDetailLayout 左右布局组件。

#### Scenario: 使用布局组件
- **WHEN** 开发者需要左右布局
- **THEN** 使用 MasterDetailLayout 组件
- **AND** 支持侧边栏折叠
- **AND** 支持自定义宽度

### Requirement: Pagination 分页组件

系统 SHALL 提供独立的 Pagination 分页组件。

#### Scenario: 使用分页组件
- **WHEN** 开发者需要分页功能
- **THEN** 使用 Pagination 组件
- **AND** 支持完整分页控制

### Requirement: Drawer 抽屉组件

系统 SHALL 提供 Drawer 抽屉组件。

#### Scenario: 使用抽屉组件
- **WHEN** 开发者需要右侧滑出面板
- **THEN** 使用 Drawer 组件
- **AND** 支持自定义宽度
- **AND** 支持 ESC 关闭

### Requirement: 可访问性增强

系统 SHALL 为所有组件提供完整的 ARIA 属性。

#### Scenario: 表格可访问性
- **WHEN** 使用 MetaTable
- **THEN** 包含 `role="grid"`
- **AND** 包含 `aria-sort` 排序状态
- **AND** 包含 `aria-selected` 选中状态

#### Scenario: 表单可访问性
- **WHEN** 使用 MetaForm
- **THEN** 包含 `aria-invalid` 验证状态
- **AND** 包含 `aria-describedby` 错误提示关联

#### Scenario: 模态框可访问性
- **WHEN** 使用 AppModal
- **THEN** 包含 `role="dialog"`
- **AND** 包含 `aria-modal="true"`
- **AND** 实现焦点陷阱（Focus Trap）

## MODIFIED Requirements

### Requirement: AppSelect 选项分组

AppSelect SHALL 支持选项分组显示。

#### Scenario: 分组选项
- **WHEN** 开发者提供分组选项格式
- **THEN** 按分组显示选项
- **AND** 支持扁平选项（向后兼容）

### Requirement: AppTabs 溢出处理

AppTabs SHALL 支持 Tab 溢出处理。

#### Scenario: Tab 溢出
- **WHEN** Tab 数量超过容器宽度
- **THEN** 自动显示下拉菜单
- **AND** 支持滚动模式

### Requirement: AppSideNav 折叠功能

AppSideNav SHALL 支持折叠功能。

#### Scenario: 折叠导航
- **WHEN** 开发者设置 `collapsible="true"`
- **THEN** 显示折叠按钮
- **AND** 折叠时仅显示图标

### Requirement: AppInput 密码显示切换

AppInput SHALL 支持密码显示切换。

#### Scenario: 密码输入框
- **WHEN** type="password"
- **THEN** 自动显示切换按钮
- **AND** 点击切换显示/隐藏密码

## REMOVED Requirements

无移除的需求。所有变更采用增量方式。

***

## 兼容性保证

### API 设计原则

1. **新增属性默认不启用**：所有新功能通过可选属性控制
2. **默认值保持原行为**：不设置新属性时，行为与之前一致
3. **渐进式迁移**：提供迁移指南，不强制升级

### 示例

```vue
<!-- 现有用法完全兼容 -->
<MetaTable :data="data" :columns="columns" />

<!-- 新功能可选启用 -->
<MetaTable
  :data="data"
  :columns="columns"
  :selectable="true"
  :pagination="{ current: 1, pageSize: 20, total: 100 }"
/>
```

***

## 验收标准

1. ✅ 所有新功能通过可选属性控制
2. ✅ 现有应用无需修改即可运行
3. ✅ 新增组件独立，不影响现有代码
4. ✅ 可访问性测试通过
5. ✅ 单元测试覆盖率 > 80%

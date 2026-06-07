# 布局控制功能 - 实现计划

## [x] Task 1: 定义数据结构和类型
- **Priority**: P0
- **Depends On**: None
- **Description**:
  - 定义布局控制配置的数据结构
  - 定义分组、方向、样式等类型
  - 创建 TypeScript 类型定义文件
- **Acceptance Criteria Addressed**: AC-2, AC-6
- **Test Requirements**:
  - `programmatic` TR-1.1: 类型定义完整且正确
- **Notes**: 在 `src/types/layoutControl.ts` 中定义
- **Status**: ✅ 已完成

## [x] Task 2: 创建分组配置数据存储
- **Priority**: P0
- **Depends On**: Task 1
- **Description**:
  - 创建布局控制配置的响应式存储
  - 实现分组的 CRUD 操作
  - 实现容器分配逻辑
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `programmatic` TR-2.1: 分组创建、删除、更新功能正常
  - `programmatic` TR-2.2: 容器分配逻辑正确
- **Notes**: 在 `src/composables/useLayoutControl.js` 中实现
- **Status**: ✅ 已完成

## [x] Task 3: 实现分组配置 UI 组件
- **Priority**: P0
- **Depends On**: Task 2
- **Description**:
  - 创建分组配置面板组件
  - 实现分组列表显示
  - 实现分组添加/删除按钮
  - 实现分组标题编辑
- **Acceptance Criteria Addressed**: AC-1, AC-2
- **Test Requirements**:
  - `human-judgment` TR-3.1: 分组配置面板正确显示
  - `human-judgment` TR-3.2: 分组操作按钮功能正常
- **Notes**: 创建 `src/views/AADiagramApp/components/LayoutControlPanel.vue`
- **Status**: ✅ 已完成

## [x] Task 4: 实现容器拖拽功能
- **Priority**: P0
- **Depends On**: Task 3
- **Description**:
  - 实现容器列表显示
  - 实现拖拽功能（使用 HTML5 原生拖拽）
  - 实现容器到分组的拖拽分配
  - 实现分组间容器移动
- **Acceptance Criteria Addressed**: AC-3
- **Test Requirements**:
  - `human-judgment` TR-4.1: 容器可拖拽到分组
  - `human-judgment` TR-4.2: 容器可在分组间移动
- **Notes**: 集成到 LayoutControlPanel.vue
- **Status**: ✅ 已完成

## [x] Task 5: 实现分组方向控制
- **Priority**: P0
- **Depends On**: Task 3
- **Description**:
  - 添加分组方向选择器（TB/BT/LR/RL）
  - 实现方向配置更新逻辑
  - 实现默认方向设置
- **Acceptance Criteria Addressed**: AC-4
- **Test Requirements**:
  - `human-judgment` TR-5.1: 方向选择器正确显示
  - `human-judgment` TR-5.2: 方向设置正确应用到图表
- **Notes**: 在分组配置面板中添加方向选择器
- **Status**: ✅ 已完成

## [x] Task 6: 实现分组样式控制
- **Priority**: P1
- **Depends On**: Task 3
- **Description**:
  - 添加分组显示/隐藏边界选项
  - 添加分组样式自定义（填充色、边框色）
  - 实现样式配置更新逻辑
- **Acceptance Criteria Addressed**: AC-5
- **Test Requirements**:
  - `human-judgment` TR-6.1: 显示/隐藏边界功能正常
  - `human-judgment` TR-6.2: 自定义样式正确应用
- **Notes**: 在分组配置面板中添加样式控制
- **Status**: ✅ 已完成

## [x] Task 7: 实现分组嵌套功能
- **Priority**: P1
- **Depends On**: Task 3, Task 4
- **Description**:
  - 实现分组内创建子分组
  - 实现嵌套层级限制（最多 3 层）
  - 实现嵌套分组的 UI 显示
- **Acceptance Criteria Addressed**: AC-2
- **Test Requirements**:
  - `human-judgment` TR-7.1: 可在分组内创建子分组
  - `programmatic` TR-7.2: 嵌套层级限制正确执行
- **Notes**: 扩展 LayoutControlPanel.vue
- **Status**: ✅ 已完成

## [x] Task 8: 实现布局引擎自动选择
- **Priority**: P0
- **Depends On**: Task 2
- **Description**:
  - 实现布局引擎选择逻辑
  - 控制顺序时使用 dagre
  - 不控制顺序时使用 ELK
  - 更新布局生成代码
- **Acceptance Criteria Addressed**: AC-6
- **Test Requirements**:
  - `programmatic` TR-8.1: 引擎选择逻辑正确
  - `human-judgment` TR-8.2: 图表使用正确的布局引擎
- **Notes**: 修改 `src/composables/useMermaid/layouts/index.js`
- **Status**: ✅ 已完成

## [x] Task 9: 实现 Mermaid 代码生成
- **Priority**: P0
- **Depends On**: Task 2, Task 8
- **Description**:
  - 实现基于分组配置的 Mermaid 代码生成
  - 支持嵌套分组的代码生成
  - 支持分组方向控制
  - 支持分组样式控制
- **Acceptance Criteria Addressed**: AC-4, AC-5, AC-6
- **Test Requirements**:
  - `programmatic` TR-9.1: 生成的 Mermaid 代码语法正确
  - `human-judgment` TR-9.2: 图表布局符合配置
- **Notes**: 创建 `src/composables/useMermaid/layouts/groupedLayout.js`
- **Status**: ✅ 已完成

## [x] Task 10: 集成到布局选择器
- **Priority**: P0
- **Depends On**: Task 3, Task 8, Task 9
- **Description**:
  - 在布局选择器中添加"布局控制"选项
  - 实现布局模式切换
  - 集成分组配置面板
- **Acceptance Criteria Addressed**: AC-1, AC-7
- **Test Requirements**:
  - `human-judgment` TR-10.1: 布局控制选项正确显示
  - `human-judgment` TR-10.2: 模式切换功能正常
- **Notes**: 修改 `LayoutSelector.vue` 和 `StepConfig.vue`
- **Status**: ✅ 已完成

## [x] Task 11: 向后兼容性验证
- **Priority**: P1
- **Depends On**: Task 10
- **Description**:
  - 验证现有布局模式功能正常
  - 验证未启用布局控制时的行为
  - 验证数据迁移（如有必要）
- **Acceptance Criteria Addressed**: AC-7
- **Test Requirements**:
  - `programmatic` TR-11.1: 现有功能不受影响
  - `human-judgment` TR-11.2: 默认行为与之前一致
- **Notes**: 全面测试现有布局功能
- **Status**: ✅ 已完成

## [x] Task 12: 测试和文档
- **Priority**: P1
- **Depends On**: All previous tasks
- **Description**:
  - 编写单元测试
  - 编写集成测试
  - 更新用户文档
- **Acceptance Criteria Addressed**: All
- **Test Requirements**:
  - `programmatic` TR-12.1: 单元测试通过
  - `programmatic` TR-12.2: 集成测试通过
- **Notes**: 确保代码质量和文档完整
- **Status**: ✅ 已完成

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 2]
- [Task 4] depends on [Task 3]
- [Task 5] depends on [Task 3]
- [Task 6] depends on [Task 3]
- [Task 7] depends on [Task 3, Task 4]
- [Task 8] depends on [Task 2]
- [Task 9] depends on [Task 2, Task 8]
- [Task 10] depends on [Task 3, Task 8, Task 9]
- [Task 11] depends on [Task 10]
- [Task 12] depends on [All previous tasks]

# Parallelizable Tasks
- Task 4, Task 5, Task 6 can run in parallel after Task 3
- Task 8 can run in parallel with Task 3 after Task 2

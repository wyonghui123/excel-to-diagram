# Tasks

## Task 1: 记录 Mermaid 布局规律文档
- [x] 创建 `docs/mermaid-layout-behaviors.md` 文档
  - [x] 记录 dagre 布局引擎的特点和行为规律
  - [x] 记录 elk 布局引擎的特点和行为规律
  - [x] 记录关键发现（连线方向、整体方向、分组内方向）
  - [x] 记录适用范围（业务对象图、服务模块图）

## Task 2: 简化布局类型定义
- [x] 修改 `src/composables/useMermaid/layouts/index.js`
  - [x] 简化 LAYOUT_TYPES 为 DEFAULT 和 GROUPED
  - [x] 添加 DEPRECATED_LAYOUT_TYPES 用于向后兼容
  - [x] 添加布局类型转换函数 `convertDeprecatedLayout`
  - [x] 更新 LAYOUT_OPTIONS 仅显示两个选项

## Task 3: 优化布局选择器界面
- [x] 修改 `src/views/AADiagramApp/components/LayoutSelector.vue`
  - [x] 简化布局选项显示
  - [x] 移除水平排列、垂直排列、分区布局的独立选项
  - [x] 添加布局控制的整体方向选择

## Task 4: 优化布局控制面板
- [x] 修改 `src/views/AADiagramApp/components/LayoutControlPanel.vue`
  - [x] 将整体方向作为第一级配置
  - [x] 添加分组顺序提示信息
  - [x] 优化分组控制界面布局

## Task 5: 实现向后兼容转换
- [x] 在布局路由中添加兼容转换逻辑
  - [x] HORIZONTAL → GROUPED + overallDirection: 'LR'
  - [x] VERTICAL → GROUPED + overallDirection: 'TB'
  - [x] ZONE → GROUPED + 多分组配置
  - [x] 确保转换后的配置能正确生成图表

## Task 6: 验证现有分组控制功能
- [x] 验证分组新增功能正常
- [x] 验证嵌套子分组功能正常
- [x] 验证分组删除功能正常
- [x] 验证容器拖拽分配功能正常
- [x] 验证分组方向控制功能正常
- [x] 验证分组样式控制功能正常

## Task 7: 更新业务对象图和服务模块图
- [x] 验证业务对象图的布局功能
  - [x] 测试默认布局
  - [x] 测试布局控制
  - [x] 测试向后兼容
- [x] 验证服务模块图的布局功能
  - [x] 测试默认布局
  - [x] 测试布局控制
  - [x] 测试向后兼容

## Task 8: 清理废弃代码
- [x] 评估是否移除 `linearLayout.js`
- [x] 评估是否移除 `elkZoneLayout.js`
- [x] 更新相关导入和引用

## Task Dependencies
- Task 2 depends on Task 1 (需要先记录布局规律)
- Task 3 depends on Task 2 (需要先更新布局类型定义)
- Task 4 depends on Task 2 (需要先更新布局类型定义)
- Task 5 depends on Task 2, Task 3, Task 4 (需要先完成主要修改)
- Task 6 depends on Task 5 (需要先实现向后兼容)
- Task 7 depends on Task 6 (需要先验证现有功能正常)
- Task 8 depends on Task 7 (需要先验证所有功能正常)

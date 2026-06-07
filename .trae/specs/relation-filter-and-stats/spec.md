# 关系过滤与统计增强 Spec

## Why
用户需要基于业务对象关系一键过滤业务对象和服务模块，以便更精确地控制图表生成范围；同时需要在页面顶部直观地看到关系数量统计。

## What Changes
- 在业务对象关系列表上方增加"基于业务关系过滤"按钮
- 点击按钮后，根据当前显示的关系中的源/目标业务对象编码，过滤业务对象和服务模块列表
- 在页面顶部统计区域增加"业务对象关系"和"服务模块关系"两个统计指标

## Impact
- Affected specs: 数据预览组件、统计显示组件、范围选择逻辑
- Affected code:
  - `src/components/DataPreview.vue` - 增加关系过滤按钮和逻辑
  - `src/views/AADiagramApp/components/StatsDisplay.vue` - 增加关系统计显示
  - `src/views/AADiagramApp/composables/useDiagramData.js` - 增加关系统计数据
  - `src/components/ScopeSelector.vue` - 支持基于业务对象编码过滤选中范围

## ADDED Requirements

### Requirement: 基于业务关系过滤按钮
系统应在业务对象关系列表上方提供"基于业务关系过滤"按钮，点击后根据关系中的业务对象编码过滤业务对象和服务模块。

#### Scenario: 默认状态
- **WHEN** 用户进入预览页面
- **THEN** 显示"基于业务关系过滤"按钮

#### Scenario: 点击过滤按钮
- **WHEN** 用户点击"基于业务关系过滤"按钮
- **THEN** 系统提取当前显示的所有业务对象关系中的源业务对象编码和目标业务对象编码
- **AND** 更新范围选择，仅选中这些编码对应的业务对象
- **AND** 更新统计数据显示

#### Scenario: 过滤逻辑基于编码
- **WHEN** 执行过滤
- **THEN** 使用业务对象编码（sourceCode、targetCode）进行匹配，而非名称

### Requirement: 关系统计显示
系统应在页面顶部统计区域显示业务对象关系和服务模块关系的数量。

#### Scenario: 显示关系统计
- **WHEN** 数据加载完成
- **THEN** 页面顶部统计区域显示"业务对象关系"和"服务模块关系"的数量

#### Scenario: 统计格式一致性
- **WHEN** 显示关系统计
- **THEN** 使用与现有统计指标相同的格式（当前选中/总数）

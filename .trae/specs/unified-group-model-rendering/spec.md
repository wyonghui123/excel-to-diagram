# 分组模型统一渲染 Spec

## Why
当前BO图和SM图使用两套独立的渲染管线（diagramDataBuilder + useBusinessObjectSyntax vs serviceModuleDiagramBuilder + useServiceModuleSyntax），导致颜色双路径计算、标识策略不一致、参数遗漏风险等问题。两种图的渲染本质完全相同——都是"嵌套容器+叶子节点"，通过GroupModel可以统一为一套渲染管线。

## What Changes
- 新增 `enrichGroupModel()` 函数，为GroupModel树补充颜色、标注等渲染信息
- 新增 `ColorCalculator` 统一颜色计算器，消除双路径问题
- 新增 `UnifiedRenderer` 统一渲染器，从enrichedGroupModel生成Mermaid代码
- Group类型增加渲染字段（color、textColor、annotationCategory、annotationContent）
- 新增 `useUnifiedRenderer` feature flag，控制新旧渲染器切换
- **BREAKING** BO图节点id从name改为code（Phase 3.3，有feature flag保护）
- **BREAKING** 删除旧渲染器文件（Phase 5，确认稳定后）

## Impact
- Affected specs: group-model-unification（已完成的前置变更）
- Affected code:
  - `src/services/groupModel/types.js` — Group类型增加字段
  - `src/services/groupModel/enrichGroupModel.js` — 新文件
  - `src/services/groupModel/ColorCalculator.js` — 新文件
  - `src/services/groupModel/UnifiedRenderer.js` — 新文件
  - `src/stores/diagramConfigStore.js` — 新增feature flag
  - `src/views/AADiagramApp/composables/useDiagramData.js` — 新增统一渲染路径
  - `src/services/diagramDataBuilder.js` — Phase 5删除
  - `src/services/serviceModuleDiagramBuilder.js` — Phase 5删除
  - `src/composables/useMermaid/syntax/useBusinessObjectSyntax.js` — Phase 5删除
  - `src/composables/useMermaid/syntax/useServiceModuleSyntax.js` — Phase 5删除

## ADDED Requirements

### Requirement: GroupModel渲染增强
系统SHALL为GroupModel树的每个节点补充渲染所需信息（color、textColor、isCenter、annotationCategory、annotationContent），使GroupModel成为渲染的唯一数据源。

#### Scenario: enrichGroupModel为叶子节点补充颜色
- **WHEN** 调用enrichGroupModel(groupModel, chartType, { colorMap, centerCodes, annotationMap, nodeTextColor })
- **THEN** 叶子节点的group.color从colorMap读取，group.isCenter从centerCodes判断，group.annotationCategory/Content从annotationMap读取

#### Scenario: enrichGroupModel为容器节点补充颜色
- **WHEN** 调用enrichGroupModel并传入containerColorMap
- **THEN** 容器节点的group.color从containerColorMap读取

### Requirement: 统一颜色计算
系统SHALL提供ColorCalculator，统一BO图和SM图的颜色计算逻辑，输出colorMap（code→color映射）。

#### Scenario: ColorCalculator按colorGroupBy计算颜色
- **WHEN** 调用ColorCalculator.compute({ nodes, colorGroupBy, colorScheme, centerScopeColor, customColors })
- **THEN** 返回{ colorMap, groupColorMap }，其中colorMap中isCenter节点使用centerScopeColor，其他节点使用按colorGroupBy分组的baseColor

### Requirement: 统一渲染器
系统SHALL提供UnifiedRenderer，从enrichedGroupModel + links生成Mermaid代码，替代两个独立的Syntax文件。

#### Scenario: UnifiedRenderer渲染SM图（2层嵌套）
- **WHEN** 调用UnifiedRenderer.render(groupModel, links, ChartType.SERVICE_MODULE, options)
- **THEN** 生成正确的Mermaid代码，包含2层subgraph嵌套（领域→子领域）和SM叶子节点

#### Scenario: UnifiedRenderer渲染BO图（3层嵌套）
- **WHEN** 调用UnifiedRenderer.render(groupModel, links, ChartType.BUSINESS_OBJECT, options)
- **THEN** 生成正确的Mermaid代码，包含3层subgraph嵌套（领域→子领域→服务模块）和BO叶子节点

### Requirement: Feature Flag控制
系统SHALL提供useUnifiedRenderer feature flag，默认为false，允许新旧渲染器并行运行和即时切换。

#### Scenario: feature flag为false时使用旧渲染器
- **WHEN** configStore.useUnifiedRenderer === false
- **THEN** 使用现有的diagramDataBuilder/serviceModuleDiagramBuilder + Syntax文件渲染

#### Scenario: feature flag为true时使用统一渲染器
- **WHEN** configStore.useUnifiedRenderer === true
- **THEN** 使用enrichGroupModel + UnifiedRenderer渲染

## MODIFIED Requirements

### Requirement: Group类型定义
Group类型增加以下可选字段：
- color: string | null — 容器背景色或节点填充色
- textColor: string | null — 节点文字颜色（仅叶子节点）
- annotationCategory: string — 标注类别，默认'info'
- annotationContent: string — 标注内容，默认''

## REMOVED Requirements

### Requirement: 旧渲染器文件（Phase 5执行）
**Reason**: 被UnifiedRenderer替代
**Migration**: 通过feature flag渐进切换，确认稳定后删除旧文件：
- diagramDataBuilder.js
- serviceModuleDiagramBuilder.js
- useBusinessObjectSyntax.js
- useServiceModuleSyntax.js
- useMermaidColors.js

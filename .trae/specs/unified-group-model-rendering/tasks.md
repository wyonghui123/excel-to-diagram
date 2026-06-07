# 分组模型统一渲染 - 任务清单

## Phase 0: 基线建立（零风险）

- [x] **T0.1**: 录制当前渲染输出基线
  - 对BO图和SM图分别录制5个场景的截图和Mermaid代码输出
  - 场景A: 无中心范围，默认配色
  - 场景B: 选择中心范围(5个BO)，按领域配色
  - 场景C: 选择中心范围，按子领域配色
  - 场景D: 选择中心范围，按服务模块配色
  - 场景E: 禁用某个分组后

- [x] **T0.2**: 在diagramConfigStore.js中添加feature flag
  - 新增 `useUnifiedRenderer: false` 字段
  - 默认false，不影响任何现有逻辑

## Phase 1: 新建核心模块（纯新增，零风险）

- [x] **T1.1**: Group类型增加渲染字段
  - 文件: `src/services/groupModel/types.js`
  - 在createGroup函数返回值中增加: color(null), textColor(null), annotationCategory('info'), annotationContent('')
  - 不修改任何现有字段

- [x] **T1.2**: 新建enrichGroupModel函数
  - 文件: `src/services/groupModel/enrichGroupModel.js`（新文件）
  - 功能: 递归遍历GroupModel树，为叶子节点写入color/textColor/isCenter/annotation，为容器节点写入color
  - 输入: groupModel, chartType, { colorMap, containerColorMap, centerCodes, annotationMap, nodeTextColor }

- [x] **T1.3**: 新建ColorCalculator
  - 文件: `src/services/groupModel/ColorCalculator.js`（新文件）
  - 功能: 统一颜色计算，输出{ colorMap, groupColorMap }
  - 逻辑: 按colorGroupBy分组 → 为每组分配颜色 → isCenter用centerScopeColor，否则用baseColor
  - 复用现有COLOR_SCHEMES常量

- [x] **T1.4**: 新建UnifiedRenderer
  - 文件: `src/services/groupModel/UnifiedRenderer.js`（新文件）
  - 功能: 从enrichedGroupModel + links生成Mermaid代码
  - 核心算法: 递归遍历GroupModel树，isTerminal→渲染节点，!isTerminal→渲染subgraph
  - 连线渲染: 通过nodeIdMap(code→groupId)映射source/target

- [x] **T1.5**: 在groupModel/index.js中导出新模块
  - 导出enrichGroupModel, ColorCalculator, UnifiedRenderer

## Phase 2: SM图接入统一渲染（先验证简单场景）

- [x] **T2.1**: useDiagramData.js SM分支增加统一渲染路径
  - 在GroupModel构建完成后，增加if(configStore.useUnifiedRenderer)分支
  - 调用ColorCalculator.compute → enrichGroupModel → UnifiedRenderer.render
  - 旧代码保留，新代码只在flag=true时执行
  - diagramData.value增加_unifiedMermaidCode字段用于调试对比

- [ ] **T2.2**: 开启feature flag验证SM图
  - 在浏览器控制台设置configStore.useUnifiedRenderer = true
  - 对比5个场景的渲染结果与Phase 0基线
  - 重点检查: 节点颜色、连线、2层嵌套subgraph

- [ ] **T2.3**: 修复SM图统一渲染的差异
  - 根据T2.2对比结果调整UnifiedRenderer
  - 可能调整: 节点ID格式、subgraph标题、连线样式、容器背景色

## Phase 3: BO图接入统一渲染（验证复杂场景）

- [x] **T3.1**: useDiagramData.js BO分支增加统一渲染路径
  - 与T2.1类似，在BO分支中增加if(configStore.useUnifiedRenderer)分支
  - 调用ColorCalculator.compute → enrichGroupModel → UnifiedRenderer.render

- [ ] **T3.2**: 开启feature flag验证BO图
  - 对比5个场景的渲染结果与Phase 0基线
  - 重点检查: 3层嵌套subgraph、节点颜色、连线颜色

- [ ] **T3.3**: BO图节点id统一为code
  - 当前BO图节点id=bo.name，统一后id=bo.code
  - 修改UnifiedRenderer中BO节点的id生成逻辑
  - 修改连线映射: source/target从name改为code
  - **这是最大风险点**，需充分验证

- [ ] **T3.4**: 修复BO图统一渲染的差异
  - 根据T3.2/T3.3对比结果调整
  - 可能调整: 连线颜色逻辑、节点大小自适应、容器排序

## Phase 4: 切换默认渲染器

- [ ] **T4.1**: feature flag默认值改为true
  - 文件: diagramConfigStore.js
  - 将useUnifiedRenderer默认值从false改为true

- [ ] **T4.2**: 全面回归测试
  - BO图5个场景 + SM图5个场景
  - 切换图表类型、修改中心范围、修改配色、禁用/启用分组、自动分组
  - 配置页面颜色与图表颜色一致性

- [x] **T4.3**: 保留旧渲染器作为fallback
  - 在store中增加fallbackToLegacyRenderer()方法

## Phase 5: 清理旧代码（确认稳定后执行）

- [ ] **T5.1**: 删除旧渲染器文件
  - diagramDataBuilder.js
  - serviceModuleDiagramBuilder.js
  - useBusinessObjectSyntax.js
  - useServiceModuleSyntax.js
  - useMermaidColors.js

- [ ] **T5.2**: 清理useDiagramData.js
  - 移除if/else分支中的旧渲染路径
  - 移除旧import
  - 简化generateDiagram()为统一路径

- [ ] **T5.3**: 移除feature flag
  - 从diagramConfigStore中移除useUnifiedRenderer字段

- [ ] **T5.4**: 清理调试日志
  - 移除GroupModel.js、useDiagramData.js中的console.log

## Task Dependencies

```
T0.1, T0.2 (基线+flag) 
    ↓
T1.1-T1.5 (新建模块，可并行)
    ↓
T2.1 (SM图接入) → T2.2 (验证) → T2.3 (修复)
    ↓
T3.1 (BO图接入) → T3.2 (验证) → T3.3 (id统一) → T3.4 (修复)
    ↓
T4.1 (flag改true) → T4.2 (回归测试) → T4.3 (fallback)
    ↓
T5.1-T5.4 (清理，可并行)
```

T1.1-T1.5之间无依赖，可并行开发。
Phase 2和Phase 3必须顺序执行（先验证简单的SM图再验证复杂的BO图）。
Phase 5必须在Phase 4验证通过后执行。

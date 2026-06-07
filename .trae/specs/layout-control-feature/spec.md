# 布局控制功能 Spec

## Why

当前系统的布局控制能力有限，用户无法精确控制容器（子领域/服务模块）的相对位置和分组方式。通过引入分组控制功能，用户可以通过拖拽方式直观地配置布局结构，实现精确的位置控制。

## What Changes

* 新增布局控制模式，支持分组、嵌套、方向控制

* 新增分组配置 UI，支持拖拽容器到分组

* 新增分组样式控制（显示/隐藏边界）

* 优化布局引擎选择逻辑（dagre vs ELK）

* **新增** 自动虚拟分层功能，支持将分组按节点数量均匀分配到虚拟层

* **优化** ELK 分组 Info 图标显示逻辑，仅对"无外部关系"和"有外部关系"分组显示

* **BREAKING** 无破坏性变更，现有功能保持兼容

## Impact

* Affected specs: 服务模块图、对象关系图的布局功能

* Affected code:

  * `src/composables/useMermaid/layouts/` - 布局生成逻辑

  * `src/views/AADiagramApp/components/LayoutSelector.vue` - 布局选择器（新增虚拟分层按钮和对话框）

  * `src/views/AADiagramApp/components/LayoutControlPanel.vue` - 布局控制面板（新增 handleAutoVirtualLayering 方法）

  * `src/views/AADiagramApp/components/GroupItem.vue` - 分组项组件（新增虚拟层样式和 Info 图标条件显示）

  * `src/views/AADiagramApp/components/steps/StepConfig.vue` - 配置面板

  * 新增分组配置组件

## ADDED Requirements

### Requirement: 布局控制模式

系统应提供布局控制模式，允许用户通过分组方式精确控制容器的相对位置。

#### Scenario: 启用布局控制

* **WHEN** 用户在布局选择器中启用"布局控制"选项

* **THEN** 系统显示分组配置面板

#### Scenario: 创建分组

* **WHEN** 用户点击"添加分组"按钮

* **THEN** 系统创建一个新的分组，并分配唯一 ID

#### Scenario: 删除分组

* **WHEN** 用户点击分组的删除按钮

* **THEN** 系统删除该分组，分组内的容器移动到未分配列表

### Requirement: ELK 自动分组

系统应在 ELK 布局模式下自动将节点分为"无外部关系"和"有外部关系"两个子分组，以优化布局效果。

#### Scenario: 自动生成 ELK 分组

* **WHEN** 用户在配置阶段点击"自动分组"按钮

* **THEN** 系统自动创建两个子分组：
  - "无外部关系"：包含没有连接外部节点的业务对象
  - "有外部关系"：包含有连接外部节点的业务对象

#### Scenario: ELK 分组说明

* **WHEN** 用户将鼠标悬停在 ELK 分组的 Info 图标上

* **THEN** 系统显示 tooltip 说明：
  - "无外部关系"：此分组中的节点没有连接外部节点的边，需要与有外部关系的区分开，否则这些节点无法均匀布局
  - "有外部关系"：此分组中的节点有连接外部节点的边，需要与无外部关系的区分开，否则这些节点无法均匀布局

#### Scenario: ELK 分组嵌套

* **WHEN** 用户在 ELK 自动生成的分组上添加子分组

* **THEN** 系统允许添加子分组，并正常显示添加按钮

### Requirement: 分组嵌套

系统应支持分组嵌套，允许在分组内创建子分组。

#### Scenario: 创建嵌套分组

* **WHEN** 用户在分组内点击"添加子分组"

* **THEN** 系统在该分组内创建一个子分组

#### Scenario: 嵌套层级限制

* **WHEN** 用户尝试创建超过 8 层嵌套的分组

* **THEN** 系统提示"嵌套层级不能超过 8 层"

### Requirement: 分组方向控制

系统应支持为每个分组独立设置方向。

#### Scenario: 设置分组方向

* **WHEN** 用户选择分组的方向（TB/BT/LR/RL）

* **THEN** 系统更新分组的方向设置，并在预览中反映

#### Scenario: 默认方向

* **WHEN** 用户创建新分组但未设置方向

* **THEN** 系统使用默认方向 LR（从左到右）

### Requirement: 分组样式控制

系统应支持控制分组的显示样式。

#### Scenario: 显示分组边界

* **WHEN** 用户选择"显示边界"选项

* **THEN** 分组在图表中显示边框和背景

#### Scenario: 隐藏分组边界

* **WHEN** 用户选择"隐藏边界"选项

* **THEN** 分组在图表中不显示边框和背景，但仍控制布局

#### Scenario: 自定义分组样式

* **WHEN** 用户设置分组的填充色或边框色

* **THEN** 分组在图表中使用自定义样式

### Requirement: 容器拖拽分配

系统应支持通过拖拽方式将容器分配到分组。

#### Scenario: 拖拽容器到分组

* **WHEN** 用户将容器从列表拖拽到分组

* **THEN** 容器被添加到该分组，并从原位置移除

#### Scenario: 在分组间移动容器

* **WHEN** 用户将容器从一个分组拖拽到另一个分组

* **THEN** 容器从原分组移除，添加到新分组

#### Scenario: 调整容器顺序

* **WHEN** 用户在分组内拖拽容器调整顺序

* **THEN** 容器在分组内的顺序被更新

### Requirement: 布局引擎自动选择

系统应根据用户配置自动选择合适的布局引擎。

#### Scenario: 控制顺序时使用 dagre

* **WHEN** 用户配置了分组顺序控制

* **THEN** 系统使用 dagre 布局引擎

#### Scenario: 不控制顺序时使用 ELK

* **WHEN** 用户未配置分组顺序控制

* **THEN** 系统使用 ELK 布局引擎

### Requirement: 数据结构定义

系统应定义清晰的布局控制配置数据结构。

#### Scenario: 配置数据结构

* **WHEN** 系统保存布局控制配置

* **THEN** 配置包含分组列表、方向、样式、容器分配等信息

### Requirement: 自动虚拟分层

系统应支持自动将现有分组分配到虚拟层中，以优化 ELK 布局效果。

#### Scenario: 启用自动虚拟分层

* **WHEN** 用户在配置页面点击"虚拟分层"按钮

* **THEN** 系统弹出对话框让用户指定分层数量（1-10层，默认3层）

#### Scenario: 虚拟分层分配逻辑

* **WHEN** 用户确认虚拟分层

* **THEN** 系统执行以下逻辑：
  1. 收集所有启用的顶级分组（包括顶级 enabled 分组和顶级 disabled 分组的 enabled 子分组）
  2. 计算每个分组的节点数量（递归统计所有子节点）
  3. 基于节点数量均匀分配到各虚拟层（使用最小负载优先算法）
  4. 创建虚拟层分组（groupType: 'virtualLayer'，显示为"虚拟层 N"）
  5. 将收集的分组移动到对应的虚拟层下
  6. 从原位置移除已移动的分组
  7. 空的 disabled 分组被提升到顶层或移除

#### Scenario: 虚拟层显示

* **WHEN** 虚拟分层完成后

* **THEN** 分组控制面板中显示虚拟层结构：
  - 虚拟层分组显示为浅蓝色背景 + 虚线边框
  - 虚拟层分组标签显示为"虚拟层"
  - 原分组作为虚拟层的子分组显示

#### Scenario: 多层 disabled 分组处理

* **WHEN** 存在多层嵌套的 disabled 分组（如：供应链云(disabled) -> 采购供应(disabled) -> 采购管理(enabled)）

* **THEN** 系统正确处理：
  - 收集最内层的 enabled 分组（采购管理）
  - 将整个 enabled 分组（包括其子分组）作为整体移动到虚拟层
  - 中间层的 disabled 分组（采购供应）被提升或移除
  - 不会重复收集或显示分组

## MODIFIED Requirements

### Requirement: 布局选择器增强

布局选择器应支持布局控制模式的切换。

#### Scenario: 布局模式切换

* **WHEN** 用户切换布局模式（默认/布局控制）

* **THEN** 系统显示对应的配置界面

## REMOVED Requirements

无移除的需求。

## Technical Design

### 数据结构

```javascript
const layoutControlConfig = {
  enabled: true,
  groups: [
    {
      id: 'group-0',
      title: '第1行',
      direction: 'LR',
      visible: true,
      style: { fill: '#f5f5f5', stroke: '#999999' },
      containers: [0, 1],
      children: []
    },
    {
      id: 'virtual-layer-1',
      title: '虚拟层 1',
      elementCode: 'virtual_layer_1',
      groupType: 'virtualLayer',
      direction: 'TB',
      visible: true,
      enabled: true,
      style: {
        fill: '#f0f9ff',
        stroke: '#0284c7',
        strokeWidth: 1,
        strokeDasharray: '5,5'
      },
      containers: [],
      children: [
        // 分配到该虚拟层的分组
      ],
      parentId: null,
      _isVirtualLayer: true,
      _layerIndex: 0
    }
  ],
  engine: 'dagre',
  preserveOrder: true
}
```

### Mermaid 代码生成

```mermaid
graph TD
  subgraph Group0["第1行"]
    direction LR
    subgraph C1["容器A"] ... end
    subgraph C2["容器B"] ... end
  end
  style Group0 fill:#f5f5f5,stroke:#999999
```

## Acceptance Criteria

### AC-1: 布局控制模式启用

* **Given**: 用户在布局选择器中

* **When**: 用户启用"布局控制"选项

* **Then**: 系统显示分组配置面板

* **Verification**: `human-judgment`

### AC-2: 分组创建和管理

* **Given**: 布局控制模式已启用

* **When**: 用户创建、删除、编辑分组

* **Then**: 分组操作正确执行，配置数据正确更新

* **Verification**: `programmatic`

### AC-3: 容器拖拽分配

* **Given**: 分组已创建

* **When**: 用户拖拽容器到分组

* **Then**: 容器正确分配到分组，图表预览正确显示

* **Verification**: `human-judgment`

### AC-4: 分组方向控制

* **Given**: 分组已创建

* **When**: 用户设置分组方向

* **Then**: 图表中分组内元素按指定方向排列

* **Verification**: `human-judgment`

### AC-5: 分组样式控制

* **Given**: 分组已创建

* **When**: 用户设置分组样式（显示/隐藏边界）

* **Then**: 图表中分组按设置显示或隐藏边界

* **Verification**: `human-judgment`

### AC-6: 布局引擎自动选择

* **Given**: 用户配置了布局控制

* **When**: 系统生成图表

* **Then**: 系统根据配置自动选择 dagre 或 ELK 布局引擎

* **Verification**: `programmatic`

### AC-7: 向后兼容

* **Given**: 用户未启用布局控制

* **When**: 用户使用现有的布局模式

* **Then**: 系统功能与之前完全一致

* **Verification**: `programmatic`

### AC-8: 自动虚拟分层

* **Given**: 用户已创建分组并启用布局控制

* **When**: 用户点击"虚拟分层"按钮并确认

* **Then**: 系统正确将分组分配到虚拟层，分组控制面板显示虚拟层结构

* **Verification**: `human-judgment`

### AC-9: 虚拟层均匀分配

* **Given**: 用户执行虚拟分层操作

* **When**: 系统分配分组到虚拟层

* **Then**: 各虚拟层的节点数量相对均匀（基于最小负载优先算法）

* **Verification**: `programmatic`

### AC-10: ELK 分组 Info 图标显示

* **Given**: 存在 ELK 自动生成的分组

* **When**: 用户在分组控制面板查看

* **Then**: 只有"无外部关系"和"有外部关系"分组显示 Info 图标

* **Verification**: `human-judgment`

## Open Questions

* [x] 分组嵌套层级限制是否合理？（当前设计为 8 层）✅ 已确认

* [ ] 是否需要支持分组模板（预设布局）？

* [ ] 是否需要支持分组配置的导入/导出？


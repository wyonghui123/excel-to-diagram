# 分组排序按钮功能 Spec

## Why

当前虚拟分层对均匀分布的效果不理想，用户需要更灵活的排序控制：
1. **整体排序**：在自动分组后，优化所有分组的排列顺序
2. **层内排序**：在虚拟分层后，优化每个虚拟层内部的子分组顺序
3. **灵活性**：用户可以根据需要选择排序时机和范围

## What Changes

### 核心改动

- **新增两个排序按钮**：
  - "整体排序"：对所有顶层分组进行排序
  - "层内排序"：对每个虚拟层内部的子分组进行排序

- **排序策略支持**：
  - 按分组大小排序（节点多的在前）
  - 按连线密度排序（有连线的靠近）
  - 综合排序（默认，结合大小和连线密度）

### 具体实现

- **UI 层**：
  - 在 `LayoutSelector.vue` 或 `LayoutControlPanel.vue` 添加两个排序按钮
  - 按钮状态控制（有分组时可用整体排序，有虚拟分层时可用层内排序）

- **逻辑层**：
  - `handleOverallSort()`：整体排序函数
  - `handleInLayerSort()`：层内排序函数
  - 复用已有的排序函数：`sortVirtualContainersBySize`, `sortVirtualContainersByConnection`, `sortVirtualContainers`

## Impact

- Affected specs: 无
- Affected code:
  - `src/views/AADiagramApp/components/LayoutSelector.vue`
  - `src/views/AADiagramApp/components/LayoutControlPanel.vue`
  - `src/composables/useMermaid/syntax/useBusinessObjectSyntax.js`（复用已有函数）

## ADDED Requirements

### Requirement: 整体排序按钮

系统 SHALL 提供"整体排序"按钮，用于对所有顶层分组进行排序。

#### Scenario: 自动分组后整体排序

- **GIVEN** 用户已点击"基于领域自动分组"
- **AND** 存在多个顶层分组
- **WHEN** 用户点击"整体排序"按钮
- **THEN** 系统应按综合策略对所有顶层分组排序
- **AND** 分组的 children 顺序应被优化
- **AND** 布局应更均匀

#### Scenario: 无分组时按钮禁用

- **GIVEN** 没有任何分组
- **WHEN** 用户查看"整体排序"按钮
- **THEN** 按钮应显示为禁用状态

### Requirement: 层内排序按钮

系统 SHALL 提供"层内排序"按钮，用于对每个虚拟层内部的子分组进行排序。

#### Scenario: 虚拟分层后层内排序

- **GIVEN** 用户已点击"虚拟分层"
- **AND** 存在多个虚拟层
- **WHEN** 用户点击"层内排序"按钮
- **THEN** 系统应对每个虚拟层的 children 进行排序
- **AND** 每个虚拟层内部的子分组顺序应被优化
- **AND** 层内布局应更均匀

#### Scenario: 无虚拟分层时按钮禁用

- **GIVEN** 没有虚拟分层
- **WHEN** 用户查看"层内排序"按钮
- **THEN** 按钮应显示为禁用状态

### Requirement: 排序策略选择

系统 SHALL 支持选择排序策略。

#### Scenario: 默认使用综合策略

- **WHEN** 用户点击排序按钮
- **THEN** 系统应默认使用综合排序策略（sizeWeight=0.4, connectionWeight=0.6）

#### Scenario: 可选排序策略（可选扩展）

- **WHEN** 用户点击排序按钮旁的下拉箭头
- **THEN** 系统应显示策略选项：按大小、按连线密度、综合
- **AND** 用户可选择不同策略

## MODIFIED Requirements

无

## REMOVED Requirements

无

## 使用场景

### 场景 A：简单分组排序

```
自动分组 → 整体排序 → 完成
```
适用于分组较少，不需要分层的情况。

### 场景 B：分层后优化

```
自动分组 → 虚拟分层 → 层内排序 → 完成
```
适用于需要分层，且优化层内布局。

### 场景 C：完整优化流程

```
自动分组 → 整体排序 → 虚拟分层 → 层内排序 → 完成
```
适用于既要优化整体顺序，又要优化层内布局。

## 技术设计

### 排序函数复用

复用 `useBusinessObjectSyntax.js` 中已有的排序函数：

```javascript
// 分组大小排序
sortVirtualContainersBySize(containers)

// 连线密度排序
sortVirtualContainersByConnection(containers, links)

// 综合排序
sortVirtualContainers(containers, links, strategy)
```

### 整体排序逻辑

```javascript
function handleOverallSort() {
  const groups = localConfig.value.groups
  if (!groups || groups.length === 0) return
  
  // 收集所有分组信息
  const groupsWithStats = groups.map(group => ({
    group,
    nodeCount: countNodesInGroup(group),
    connectionDensity: calculateGroupConnectionDensity(group, links)
  }))
  
  // 按综合得分排序
  groupsWithStats.sort((a, b) => {
    const scoreA = a.nodeCount * 0.4 + a.connectionDensity * 0.6
    const scoreB = b.nodeCount * 0.4 + b.connectionDensity * 0.6
    return scoreB - scoreA
  })
  
  // 更新分组顺序
  localConfig.value.groups = groupsWithStats.map(item => item.group)
  emitUpdate()
}
```

### 层内排序逻辑

```javascript
function handleInLayerSort() {
  const groups = localConfig.value.groups
  if (!groups || groups.length === 0) return
  
  // 找到所有虚拟层
  const virtualLayers = groups.filter(g => g._isVirtualLayer)
  if (virtualLayers.length === 0) return
  
  // 对每个虚拟层的 children 排序
  virtualLayers.forEach(layer => {
    if (layer.children && layer.children.length > 1) {
      const childrenWithStats = layer.children.map(child => ({
        child,
        nodeCount: countNodesInGroup(child),
        connectionDensity: calculateGroupConnectionDensity(child, links)
      }))
      
      childrenWithStats.sort((a, b) => {
        const scoreA = a.nodeCount * 0.4 + a.connectionDensity * 0.6
        const scoreB = b.nodeCount * 0.4 + b.connectionDensity * 0.6
        return scoreB - scoreA
      })
      
      layer.children = childrenWithStats.map(item => item.child)
    }
  })
  
  emitUpdate()
}
```

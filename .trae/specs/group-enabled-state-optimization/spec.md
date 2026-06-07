# 分组启用状态优化 Spec

## Why

当前自动分组后，大分组（如领域、子领域）默认都是 enabled 状态，导致 ELK 布局时大分组"吞掉"大量空间，子分组无法灵活分布，布局不够均衡。通过将大分组设置为 disabled，可以让 ELK 直接布局子分组，从而获得更均衡的布局效果。

## What Changes

### 核心改动

- **新增"优化分组状态"按钮**：用户手动触发，不影响现有自动分组逻辑
- **分组启用状态优化规则**：
  1. 中心范围的领域分组：默认 disabled
  2. 非中心范围的领域分组：当子孙叶子节点数超过总节点数 20% 时，设置为 disabled
  3. 递归处理子分组，直到遇到：
     - 直接包含叶子节点的分组层级
     - 或包含"有外部关系"/"无外部关系"分组

- **配置项支持**：20% 阈值可配置

### 具体实现

- **UI 层**：
  - 在 LayoutSelector.vue 添加"优化分组状态"按钮
  - 在高级配置区域添加阈值配置项

- **逻辑层**：
  - `optimizeGroupEnabledState()` 函数
  - 递归计算分组节点数
  - 按规则设置 enabled 状态

## Impact

- Affected specs: 无
- Affected code:
  - `src/views/AADiagramApp/components/LayoutSelector.vue`
  - `src/views/AADiagramApp/components/LayoutControlPanel.vue`
  - `src/views/AADiagramApp/components/steps/StepConfig.vue`（配置项）

## ADDED Requirements

### Requirement: 优化分组状态按钮

系统 SHALL 提供"优化分组状态"按钮，用于自动调整分组的启用状态。

#### Scenario: 用户触发优化分组状态

- **GIVEN** 用户已完成自动分组
- **AND** 存在多个分组
- **WHEN** 用户点击"优化分组状态"按钮
- **THEN** 系统应按照规则调整分组的 enabled 状态
- **AND** 大分组（超过阈值）应被设置为 disabled
- **AND** 布局应更均衡

#### Scenario: 无分组时按钮禁用

- **GIVEN** 没有任何分组
- **WHEN** 用户查看"优化分组状态"按钮
- **THEN** 按钮应显示为禁用状态

### Requirement: 分组启用状态优化规则

系统 SHALL 按照以下规则优化分组的启用状态：

#### 规则 1：中心范围领域分组

- **WHEN** 领域分组属于中心范围
- **THEN** 从该领域分组开始递归向下设置 disabled
- **AND** 递归终止条件：
  - 该分组包含大于 1 个子分组（即有多个子分组需要分别布局）
  - 或该分组直接包含叶子节点（有 containers 或 directNodes）

#### 规则 2：非中心范围领域分组

- **WHEN** 领域分组属于非中心范围
- **AND** 该分组包含的子孙叶子节点数 > 总节点数 × 阈值
- **THEN** 该分组应设置为 disabled
- **AND** 继续递归处理其子分组

#### 规则 3：递归终止条件

递归处理应在以下情况停止：
- 遇到直接包含叶子节点的分组（即该分组有 containers 或 directNodes）
- 遇到"有外部关系"或"无外部关系"分组
- **对于中心范围**：遇到包含大于 1 个子分组的分组

### Requirement: 阈值配置项

系统 SHALL 支持配置分组节点数阈值。

#### Scenario: 默认阈值

- **WHEN** 用户未配置阈值
- **THEN** 系统应使用默认值 20%

#### Scenario: 自定义阈值

- **WHEN** 用户在高级配置中设置阈值
- **THEN** 系统应使用用户配置的阈值

## MODIFIED Requirements

无

## REMOVED Requirements

无

## 技术设计

### 函数签名

```javascript
/**
 * 优化分组的启用状态
 * @param {Array} groups - 分组数组
 * @param {number} totalNodes - 总节点数
 * @param {Set} centerScopeCodes - 中心范围节点编码集合
 * @param {number} threshold - 阈值百分比（默认 0.2）
 */
function optimizeGroupEnabledState(groups, totalNodes, centerScopeCodes, threshold = 0.2)
```

### 递归逻辑

```javascript
function processGroup(group, totalNodes, centerScopeCodes, threshold, isCenterPath) {
  // 检查是否是终止条件
  if (isLeafGroup(group) || hasSpecialGroup(group)) {
    return
  }
  
  // 中心范围特殊终止条件：包含大于1个子分组
  if (isCenterPath && group.children && group.children.length > 1) {
    return
  }
  
  // 判断是否需要 disable
  let shouldDisable = false
  
  if (isCenterPath) {
    // 中心范围：直接 disable
    shouldDisable = true
  } else {
    // 非中心范围：检查阈值
    const leafNodeCount = countLeafNodes(group)
    shouldDisable = leafNodeCount > totalNodes * threshold
  }
  
  if (shouldDisable) {
    group.enabled = false
    
    // 递归处理子分组
    if (group.children && group.children.length > 0) {
      group.children.forEach(child => {
        processGroup(child, totalNodes, centerScopeCodes, threshold, isCenterPath)
      })
    }
  }
}

function isLeafGroup(group) {
  // 直接包含叶子节点：有 containers 或 directNodes
  return (group.containers && group.containers.length > 0) ||
         (group.directNodes && group.directNodes.length > 0)
}

function hasSpecialGroup(group) {
  // 包含有外部关系/无外部关系分组
  if (group.title === '有外部关系' || group.title === '无外部关系') {
    return true
  }
  if (group.children) {
    return group.children.some(child => hasSpecialGroup(child))
  }
  return false
}

function isInCenterScope(group, centerScopeCodes) {
  // 检查分组是否属于中心范围
  if (group.elementCode && centerScopeCodes.has(group.elementCode)) {
    return true
  }
  if (group.children) {
    return group.children.some(child => isInCenterScope(child, centerScopeCodes))
  }
  return false
}
```

### 按钮位置

在 LayoutSelector.vue 中，放在"整体排序"按钮旁边：

```
[自动分组] [虚拟分层] [整体排序] [层内排序] [优化分组状态]
```

### 配置项位置

在 StepConfig.vue 的高级配置区域，添加：

```
高级选项 ▼
├── 分组优化阈值: [20]%
```

## 使用场景

### 场景 A：优化大分组布局

```
自动分组 → 优化分组状态 → 整体排序 → 完成
```

大分组被设置为 disabled，子分组直接参与布局，布局更均衡。

### 场景 B：配合虚拟分层

```
自动分组 → 优化分组状态 → 虚拟分层 → 层内排序 → 完成
```

先优化分组状态，再进行虚拟分层，获得最佳布局效果。

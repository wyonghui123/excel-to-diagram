# 优化虚拟容器排序以改善布局均匀性 Spec

## Why

当前 ELK 布局在处理虚拟容器时，容器定义顺序基于字母排序，导致：
1. **布局不均匀**：相关容器被分开，连线长度和交叉增加
2. **空间分配不合理**：大容器和小容器混合排列，空间利用不佳
3. **可读性差**：逻辑相关的容器在视觉上不相关

## What Changes

### 核心改动

- **优化虚拟容器排序策略**：
  - 按分组大小排序（节点多的容器在前）
  - 按连线密度排序（有连线的容器靠近在一起）
  - 组合策略（综合考虑两个因素）

### 具体实现

- **新增函数**：
  - `calculateContainerConnectionDensity()`：计算容器之间的连线密度
  - `calculateContainerScores()`：计算容器的综合得分
  - `sortVirtualContainers()`：排序虚拟容器

- **修改函数**：
  - `generateMermaidCode()`：集成容器排序逻辑

## Impact

- Affected specs: 无
- Affected code: 
  - `src/composables/useMermaid/syntax/useBusinessObjectSyntax.js`
  - `src/composables/useMermaid/syntax/useServiceModuleSyntax.js`

## ADDED Requirements

### Requirement: 虚拟容器排序优化

系统 SHALL 在生成 Mermaid 代码时，优化虚拟容器的定义顺序，以改善布局均匀性。

#### Scenario: 按分组大小排序

- **WHEN** 虚拟容器包含不同数量的节点
- **THEN** 节点多的容器应优先定义
- **AND** ELK 布局应更合理地分配空间

#### Scenario: 按连线密度排序

- **WHEN** 虚拟容器之间存在连线关系
- **THEN** 有连线的容器应靠近在一起
- **AND** 连线长度和交叉应减少

#### Scenario: 组合策略排序

- **WHEN** 同时考虑分组大小和连线密度
- **THEN** 系统应计算综合得分
- **AND** 按综合得分排序容器
- **AND** 布局应更均匀、可读性更好

## MODIFIED Requirements

### Requirement: Mermaid 代码生成

原有的 Mermaid 代码生成逻辑 SHALL 在构建虚拟容器后，增加排序步骤：

```javascript
// 原有逻辑
const virtualGroups = buildVirtualContainers(...)

// 新增逻辑
const sortedVirtualGroups = sortVirtualContainersByStrategy(virtualGroups, data.links, {
  strategy: 'combined',  // 'size' | 'connection' | 'combined'
  sizeWeight: 0.4,
  connectionWeight: 0.6
})

// 使用排序后的容器生成代码
```

## REMOVED Requirements

无

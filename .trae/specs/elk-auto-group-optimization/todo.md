# ELK 自动分组逻辑优化待办

## 背景

当前存在两套 inner/boundary 分组逻辑：

### 1. 分组控制中的自动分组 (LayoutControlPanel.vue)

```javascript
// 创建 ELK 子分组
const createElkSubGroup = (title, containers, elkType) => ({
  id: generateGroupId(),
  title,
  elementCode: `${smCode}_${elkType}`,
  groupType: 'custom',
  visible: false,  // 默认隐藏
  containers,
  _elkGroup: elkType  // 'inner' 或 'boundary'
})

// 内部子分组（无外部关系）
const innerGroup = createElkSubGroup('无外部关系', innerContainers, 'inner')
// 边界子分组（有外部关系）
const boundaryGroup = createElkSubGroup('有外部关系', boundaryContainers, 'boundary')
```

**特点**：
- 在**数据层**创建分组结构
- 每个节点被包装成**虚拟容器** (`isVirtual: true`)
- 分组 `visible: false`，但仍创建 subgraph 用于布局控制

### 2. ELK 自动分组逻辑 (groupedLayout.js:412-473)

```javascript
// ELK 自动分组：将有/无外部连线的节点分离
if (layoutEngine === 'elk' && links && links.length > 0 && containerNodeIds.length > 1) {
  // 创建 _inner 和 _boundary 两个子容器
  code += `subgraph ${actualContainerId}_inner[" "]\n`
  code += `subgraph ${actualContainerId}_boundary[" "]\n`
}
```

**特点**：
- 在**渲染层**创建 subgraph
- 直接将节点放入 subgraph
- 只对**非虚拟容器**生效

## 当前状态

| 场景 | 分组控制 | ELK 自动分组 | 结果 |
|------|----------|--------------|------|
| 使用分组控制 | ✅ 已处理 inner/boundary | ❌ 虚拟容器提前 return，不执行 | **冗余但无害** |
| 不使用分组控制 | ❌ 无 | ✅ 处理原始容器 | **有用** |

## 问题

1. **逻辑重复**：两套逻辑实现类似的功能
2. **维护成本**：需要同时维护两套代码
3. **潜在冲突**：如果两者同时生效可能导致问题

## 待办事项

- [ ] 分析 ELK 自动分组逻辑的使用场景
- [ ] 确认是否所有场景都通过分组控制处理
- [ ] 如果分组控制覆盖所有场景，考虑移除 ELK 自动分组逻辑
- [ ] 如果需要保留，考虑统一两套逻辑的实现方式

## 建议

### 方案 A：移除 ELK 自动分组逻辑

**条件**：如果分组控制已经覆盖所有使用场景

**优点**：
- 简化代码
- 避免重复逻辑
- 统一数据处理流程

**风险**：
- 可能影响不使用分组控制的场景

### 方案 B：保留但统一逻辑

**条件**：如果存在不使用分组控制的场景

**优点**：
- 保持兼容性
- 提供后备方案

**风险**：
- 需要维护两套代码

## 相关文件

- `src/views/AADiagramApp/components/LayoutControlPanel.vue` - 分组控制逻辑
- `src/composables/useMermaid/layouts/groupedLayout.js` - ELK 自动分组逻辑

## 创建时间

2026-04-12

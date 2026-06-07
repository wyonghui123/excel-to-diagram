# 分组模型重构分析

## 2026-04-05：filterGroupModelByScope 问题分析

---

## 1. 问题现象

`filterGroupModelByScope` 在服务模块图场景下会错误地过滤掉所有分组，导致返回空数组。

---

## 2. 代码分析

### 2.1 问题代码

```javascript
// architectureProcessor.js - filterGroupModelByScope
export function filterGroupModelByScope(groups, selectedCodes, chartType) {
  if (!selectedCodes || selectedCodes.size === 0) {
    return groups
  }

  const config = getChartTypeConfig(chartType)

  function filterGroup(group) {
    if (config.terminalTypes.includes(group.type)) {
      const code = group.elementRef?.code
      return selectedCodes.has(code) ? { ...group, children: [] } : null
    }
    // ...
  }

  return groups.map(filterGroup).filter(Boolean)
}
```

### 2.2 chartTypeConfig 配置

```javascript
// chartTypeConfig.js
[ChartType.SERVICE_MODULE]: {
  terminalTypes: [GroupType.SERVICE_MODULE],  // 服务模块图的终端类型
  // ...
}

[ChartType.BUSINESS_OBJECT]: {
  terminalTypes: [GroupType.BUSINESS_OBJECT],  // 业务对象图的终端类型
  // ...
}
```

### 2.3 核心问题

| 场景 | selectedCodes 来源 | 终端类型 | 匹配结果 |
|------|-------------------|----------|----------|
| 业务对象图 | 业务对象编码集合 | BUSINESS_OBJECT | ✅ 正确 |
| 服务模块图 | 业务对象编码集合 | SERVICE_MODULE | ❌ 无法匹配 |

服务模块图的 `selectedCodes` 仍然是**业务对象编码**，但终端类型是**服务模块编码**，两者不匹配，导致所有分组被过滤掉。

---

## 3. 重构方案

### 方案 A：在 filterGroupModelByScope 内部处理兼容

**思路**：根据 chartType 确定要匹配的终端类型，然后根据 selectedCodes 查找对应的终端编码。

```javascript
export function filterGroupModelByScope(groups, selectedCodes, chartType) {
  if (!selectedCodes || selectedCodes.size === 0) {
    return groups
  }

  const config = getChartTypeConfig(chartType)

  // 构建终端编码集合
  const terminalCodes = new Set()
  function collectTerminalCodes(g) {
    if (config.terminalTypes.includes(g.type)) {
      if (g.elementRef?.code) {
        terminalCodes.add(g.elementRef.code)
      }
    }
    if (g.children) {
      g.children.forEach(collectTerminalCodes)
    }
  }
  groups.forEach(collectTerminalCodes)

  // 检查 selectedCodes 是否与任何终端编码相关
  const hasRelevantSelection = [...selectedCodes].some(code => {
    // 业务对象图：直接匹配
    // 服务模块图：需要查找业务对象关联的服务模块
    return terminalCodes.has(code) || isRelatedToTerminal(code, chartType)
  })

  if (!hasRelevantSelection) {
    return groups  // 没有相关选择，保持所有分组
  }

  // ... 过滤逻辑
}
```

**问题**：引入了新的依赖关系判断逻辑，复杂度增加。

---

### 方案 B：拆分过滤函数

**思路**：为每种图表类型创建专门的过滤函数。

```javascript
// 业务对象图过滤
export function filterBusinessObjectGroups(groups, selectedBoCodes) {
  // ...
}

// 服务模块图过滤
export function filterServiceModuleGroups(groups, selectedBoCodes, businessObjects) {
  // 构建业务对象 -> 服务模块的映射
  const boToSm = new Map()
  businessObjects.forEach(bo => {
    if (bo.serviceModule) {
      boToSm.set(bo.code, bo.serviceModule)
    }
  })

  // 将业务对象编码转换为服务模块编码
  const selectedSmCodes = new Set()
  selectedBoCodes.forEach(boCode => {
    const smCode = boToSm.get(boCode)
    if (smCode) {
      selectedSmCodes.add(smCode)
    }
  })

  // 使用服务模块编码过滤
  // ...
}
```

**优点**：逻辑清晰，每种图表类型独立处理
**缺点**：代码重复，需要维护多个函数

---

### 方案 C：统一过滤接口（推荐）

**思路**：重新设计 GroupModel，让过滤逻辑更内聚。

```javascript
class GroupModel {
  constructor(groups, options = {}) {
    this.groups = new Map()
    this.rootIds = []
    this.options = options
    // ...
  }

  // 根据选中的终端编码过滤分组
  filterByTerminalCodes(selectedTerminalCodes) {
    if (!selectedTerminalCodes || selectedTerminalCodes.size === 0) {
      return this
    }

    // 深拷贝，避免修改原始数据
    const clonedGroups = this.cloneGroups()

    // 根据终端类型过滤
    const config = getChartTypeConfig(this.options.chartType)

    function filterGroup(group) {
      if (config.terminalTypes.includes(group.type)) {
        const code = group.elementRef?.code
        return selectedTerminalCodes.has(code) ? group : null
      }
      // ...
    }

    // 返回新的 GroupModel 实例
    return new GroupModel(filteredGroups, this.options)
  }
}
```

**优点**：
1. 过滤逻辑内聚在 GroupModel 类中
2. 可以链式调用
3. 返回新的实例，不影响原始数据

**缺点**：需要较大重构

---

## 4. 当前临时修复说明

当前采用临时修复：在 `useDiagramData.js` 中跳过服务模块图的 `filterGroupModelByScope` 调用。

```javascript
if (hasFilter && finalBoCodes) {
  if (chartType.value !== 'serviceModule') {  // 临时跳过
    architectureGroups = filterGroupModelByScope(architectureGroups, finalBoCodes, ChartType.SERVICE_MODULE)
  }
}
```

**风险**：
1. 服务模块图在有过滤场景下可能显示不正确
2. 代码逻辑不清晰

---

## 5. 推荐重构步骤

### 阶段 1：清理与文档化（低风险）
1. 清理所有调试 console.log
2. 添加函数文档注释
3. 记录当前的临时修复

### 阶段 2：提取通用过滤逻辑（中风险）
1. 在 `filterGroupModelByScope` 内部处理不同图表类型的兼容
2. 添加单元测试覆盖各种场景

### 阶段 3：重构 GroupModel 类（高风险）
1. 将过滤逻辑移入 GroupModel
2. 统一业务对象图和服务模块图的数据流
3. 全面测试验证

---

## 6. 关键教训

1. **类型意识**：过滤函数应该理解它处理的终端类型
2. **数据来源**：selectedCodes 的来源必须与目标终端类型匹配
3. **内聚性**：相关逻辑应该内聚在同一模块，避免分散在数据流各处

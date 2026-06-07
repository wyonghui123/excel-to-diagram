# 统一模型分析与现状差距报告

## 一、您的统一模型设计思想

### 1.1 核心设计原则

```
统一数据结构（4层，过滤后）
         │
         ▼
┌─────────────────────────────────────┐
│     分组模型构建（按图表类型区分）      │
├─────────────────────────────────────┤
│  业务对象图：Domain→SubDomain→SM→BO  │
│            → BO 作为节点，其余作为分组  │
│            → 自动分配 BO 到 SM        │
├─────────────────────────────────────┤
│  服务模块图：Domain→SubDomain→SM     │
│            → SM 作为节点，其余作为分组  │
│            → 自动分配 SM 到 SubDomain │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│         输出：统一分组模型              │
│  分组嵌套 + 节点 + 节点关联数据        │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│     分组模型 → 图表模型（统一）        │
│  容器 → 节点 → 关系                   │
└─────────────────────────────────────┘
```

### 1.2 统一模型的关键特点

1. **数据结构统一**：都是 4 层架构（Domain → SubDomain → SM → BO），只是不同图表类型取不同层作为"节点"
2. **分组构建灵活**：按图表类型决定节点层，其余作为分组层级
3. **输出格式统一**：分组 + 节点 + 节点关联数据
4. **图表渲染统一**：从分组模型到图表的转换逻辑应该是**一套**

---

## 二、现状分析：与统一模型的差距

### 2.1 关键发现：两套数据源

| 数据流 | 业务对象图 | 服务模块图 |
|--------|-----------|-----------|
| **控制面板数据源** | `props.containers` | `props.domainProducts` |
| **图表渲染数据源** | `buildBusinessObjectGroupModel` | `buildServiceModuleGroupModel` |
| **数据格式** | 扁平容器 + 嵌套 nodes | 层级 domainProducts |

**问题**：两套数据源，数据格式完全不同！

### 2.2 `handleServiceModuleAutoGroup` vs `handleBusinessObjectAutoGroup`

#### `handleBusinessObjectAutoGroup`（业务对象图）

```javascript
// 使用 props.containers 构建分组
props.containers.forEach(container => {
  // container 结构: { domain, name, nodes, serviceModuleMap }
  const domainGroup = { ... }
  const subDomainGroup = { ... }

  // 业务对象作为 containers
  boCodes.forEach(boCode => {
    subDomainGroup.containers.push({
      id: `bo_${boCode}`,
      name: codeToNameMap.get(boCode),
      elementCode: boCode,
      // ...
    })
  })
})
```

**特点**：
- 数据源：`props.containers`（扁平结构）
- 业务对象 → `containers`
- 服务模块 → 中间层分组

#### `handleServiceModuleAutoGroup`（服务模块图）

```javascript
// 使用 props.domainProducts 构建分组
props.domainProducts.forEach(domain => {
  domain.modules.forEach(subDomain => {
    subDomain.submodules.forEach(sm => {
      // 服务模块作为 children 分组
      subDomainGroup.children.push({
        id: createGroupId(GroupType.SERVICE_MODULE, smCode),
        type: GroupType.SERVICE_MODULE,
        // ...
      })
    })
  })
})
```

**特点**：
- 数据源：`props.domainProducts`（层级结构）
- 服务模块 → `children`（不是 containers）
- **没有 containers**（控制面板看不到服务模块列表）

### 2.3 核心差距分析

#### 差距 1：数据源不同

| 组件 | 业务对象图 | 服务模块图 |
|------|-----------|-----------|
| 控制面板 | `props.containers` | `props.domainProducts` |
| 图表渲染 | `buildBusinessObjectGroupModel` | `buildServiceModuleGroupModel` |

#### 差距 2：`containers` vs `children`

| 图表类型 | 节点放置位置 | 控制面板显示 | 图表渲染 |
|---------|------------|-------------|---------|
| 业务对象图 | `containers` | ✅ 显示节点列表 | ✅ 通过 `toMermaidConfig` 处理 |
| 服务模块图 | `children` | ❌ 无 containers | ✅ 通过 `UnifiedRenderer` 处理 |

#### 差距 3：数据格式转换缺失

**业务对象图**：
```
props.containers[i].nodes[] → subDomainGroup.containers[]
```
自动分配完成，节点在 `containers` 中。

**服务模块图**：
```
props.domainProducts[i].submodules[] → subDomainGroup.children[]
```
服务模块直接作为 `children` 分组，没有经过"分配到 containers"的步骤。

### 2.4 统一模型应该是怎样的

根据您的统一模型设计：

```
服务模块图的数据流应该是：
1. 数据源：filteredDomainProducts（4层结构，过滤后）
2. 分组构建：
   - Domain, SubDomain → 分组层级
   - SM → 节点（自动分配到 SubDomain.containers）
3. 输出：SubDomain.containers = [SM1, SM2, ...]
4. 控制面板：从 containers 渲染节点列表
5. 图表渲染：从 containers 渲染终端节点
```

**但现状是**：
- 服务模块直接放在 `children` 里，不是 `containers`
- 控制面板看不到服务模块节点列表
- 图表渲染也是从 `children` 取终端节点

---

## 三、为什么"分组展示正确，图表展示有问题"

### 3.1 问题现象

您说的问题是：
- **控制面板**：服务模块显示为分组树（children 递归）✅
- **图表渲染**：disabled 父分组时，服务模块提升不正确 ❌

### 3.2 原因分析

根据您的统一模型，两个图表类型的转换逻辑应该统一。但现状是：

| 转换阶段 | 业务对象图 | 服务模块图 |
|---------|-----------|-----------|
| **控制面板渲染** | `group.containers` | `group.children` 递归 |
| **合并用户配置** | 合并 `containers` | 合并 `children` |
| **disabled 提升** | 处理 `children` | 处理 `children` |
| **图表渲染** | `toMermaidConfig` 处理 `containers` | `UnifiedRenderer` 处理 `children` |

**关键问题**：
1. 业务对象图的 `containers` 在 `GroupItem.vue` 中直接渲染列表
2. 服务模块图的 `children` 在 `GroupItem.vue` 中递归渲染为分组

如果服务模块也在 `children` 中，那控制面板应该也能正确显示。但问题是：**服务模块既在 `children` 中（用于图表渲染），又在 `containers` 中吗？**

---

## 四、关键问题诊断

### 4.1 `handleServiceModuleAutoGroup` 应该怎么写

根据统一模型：

```javascript
function handleServiceModuleAutoGroup() {
  // 数据源：filteredDomainProducts（与业务对象图一致的数据结构）
  props.domainProducts.forEach(domain => {
    const domainGroup = { type: 'domain', ... }

    domain.modules.forEach(subDomain => {
      const subDomainGroup = { type: 'subDomain', parentId: domainGroup.id, containers: [], children: [] }

      // 服务模块作为节点，分配到 containers（与业务对象一致）
      subDomain.submodules.forEach(sm => {
        subDomainGroup.containers.push({
          id: createGroupId(GroupType.SERVICE_MODULE, smCode),
          name: smName,
          code: smCode,
          // ...
        })

        // 如果统一模型需要 SM 也作为分组（用于 disabled 提升）
        // 那应该同时添加到 children...
        // 但这会导致双重显示问题
      })

      domainGroup.children.push(subDomainGroup)
    })

    groups.push(domainGroup)
  })
}
```

### 4.2 `containers` 和 `children` 的用途混淆

根据代码分析：

| 用途 | 业务对象图 | 服务模块图（现状）|
|------|-----------|----------------|
| 控制面板显示 | `containers` | ❌ 空 |
| 控制面板分组 | `children` | `children` |
| 合并用户配置 | 处理 `containers` | 处理 `children` |
| 图表渲染终端 | `toMermaidConfig` 从 `containers` | `UnifiedRenderer` 从 `children` |

**问题**：
- 服务模块图的 `containers` 是空的
- 服务模块在 `children` 中
- 但 `toMermaidConfig` 从 `containers` 取终端节点（所以不会用 SM 作为终端）
- `UnifiedRenderer` 从 `children` 取终端节点（会用 SM 作为终端）

这导致两套渲染逻辑不一致！

---

## 五、建议的统一模型实现

### 5.1 核心原则

1. **数据结构统一**：都用 4 层 domainProducts
2. **节点统一放 `containers`**：无论是 BO 还是 SM，都放在 `containers`
3. **`children` 只用于分层结构**：Domain → SubDomain → ... → containers
4. **图表渲染统一**：都从 `containers` 取终端节点

### 5.2 统一的数据结构

```javascript
// Domain 分组
{
  id: 'D_xxx',
  type: 'DOMAIN',
  children: [SubDomain1, SubDomain2],  // 子分组
  containers: []  // Domain 层无终端节点
}

// SubDomain 分组
{
  id: 'SD_xxx',
  type: 'SUB_DOMAIN',
  parentId: 'D_xxx',
  children: [],  // 子领域下无更多分组层级
  containers: [SM1, SM2, ...]  // 服务模块作为终端节点
}

// ServiceModule 节点（容器）
{
  id: 'SM_xxx',
  name: '服务模块名称',
  code: 'SM_xxx',
  // ...
}
```

### 5.3 图表类型区分

| 图表类型 | 节点层 | containers 来源 |
|---------|-------|----------------|
| 业务对象图 | BO | `sm.businessObjects` |
| 服务模块图 | SM | `subDomain.submodules` |

### 5.4 渲染统一

`UnifiedRenderer` 或 `toMermaidConfig` 都从 `containers` 取终端节点，不再区分 `children` 和 `containers`。

---

## 六、当前架构评估

### 6.1 优势

1. `GroupModel`、`getFlattenedGroups`、`UnifiedRenderer` 是共用组件
2. 分组层级结构定义清晰
3. disabled 提升逻辑集中管理

### 6.2 问题

1. **服务模块图的 `containers` 为空**：
   - 控制面板看不到服务模块节点列表
   - 需要手动拖拽分配（但列表是空的！）

2. **两套渲染逻辑**：
   - `toMermaidConfig` 从 `containers` 渲染
   - `UnifiedRenderer` 从 `children` 渲染
   - 导致业务对象图和服务模块图行为不一致

3. **`children` vs `containers` 用途混淆**：
   - 业务对象图的 BO 在 `containers`
   - 服务模块图的 SM 在 `children`
   - 合并逻辑只处理 `children`

### 6.3 验证建议

请在浏览器控制台检查以下日志：

1. `[handleServiceModuleAutoGroup] Final groups count`
2. `[handleServiceModuleAutoGroup] Groups structure` - 检查 `containers` 是否为空
3. `[buildServiceModuleGroupModel]` - 检查 `architectureGroups` 结构
4. `[GroupModel.getFlattenedGroups]` - 检查 `children` vs `containers`

---

## 七、结论

根据您的统一模型思想，**服务模块图应该和服务模块图一样**：
1. 服务模块作为 `containers`
2. `children` 只用于分层结构
3. 图表渲染统一从 `containers` 取终端节点

**现状问题**：
- 服务模块在 `children` 中，不是 `containers`
- 导致控制面板显示分组树而不是节点列表
- 导致图表渲染逻辑与业务对象图不一致

**建议**：
按照统一模型重新实现 `handleServiceModuleAutoGroup`，使服务模块作为 `containers` 而非 `children`。

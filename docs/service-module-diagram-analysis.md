## 目录

1. [一、数据模型分析](#一-数据模型分析)
2. [二、数据流分析](#二-数据流分析)
3. [三、两图表差异分析](#三-两图表差异分析)
4. [四、问题诊断](#四-问题诊断)
5. [五、调试建议](#五-调试建议)
6. [六、结论](#六-结论)

---
# 服务模块图与业务对象图 - 代码现状深入分析

## 一、数据模型分析

### 1.1 核心类型定义 (`types.js`)

```javascript
const GroupType = {
  DOMAIN: 'DOMAIN',           // 领域
  SUB_DOMAIN: 'SUB_DOMAIN',   // 子领域
  SERVICE_MODULE: 'SERVICE_MODULE', // 服务模块
  BUSINESS_OBJECT: 'BUSINESS_OBJECT', // 业务对象
  LAYOUT: 'LAYOUT'            // 布局分组
}

function createGroupId(type, code) {
  // ID 格式：前缀_编码
  // DOMAIN → D_xxx
  // SUB_DOMAIN → SD_xxx
  // SERVICE_MODULE → SM_xxx
  // BUSINESS_OBJECT → BO_xxx
}
```

### 1.2 图表类型配置 (`chartTypeConfig.js`)

| 配置项 | 业务对象图 | 服务模块图 |
|--------|-----------|-----------|
| **groupHierarchy** | DOMAIN → SUB_DOMAIN → SM → BO | DOMAIN → SUB_DOMAIN → SM |
| **terminalTypes** | BUSINESS_OBJECT | SERVICE_MODULE |
| **visibleInControlPanel** | DOMAIN, SUB_DOMAIN, SM | DOMAIN, SUB_DOMAIN |
| **defaultExpandDepth** | 3 | 2 |

### 1.3 分组对象结构

```javascript
// 标准分组对象
{
  id: 'SM_001',                    // 唯一标识 (createGroupId 生成)
  type: 'SERVICE_MODULE',          // 分组类型
  title: '服务模块名称',            // 显示标题
  elementRef: {                    // 关联的架构元素
    type: 'SERVICE_MODULE',
    code: 'SM_001',
    name: '服务模块名称',
    parentCode: '子领域代码',
    grandparentCode: '领域代码'
  },
  parentId: 'SD_001',              // 父分组 ID
  children: [],                    // 子分组 (数组，元素是分组对象)
  containers: [],                  // 容器节点 (用于控制面板拖拽)
  layout: {
    direction: 'TB',              // 布局方向
    visible: true,
    enabled: true,
    style: { fill, stroke, strokeWidth, strokeDasharray }
  },
  // 以下为运行时属性
  _disabledAncestorPath: [],       // disabled 祖先路径
  _cachedDisabledPath: null,      // 缓存的路径
  color: null,                    // 颜色
  textColor: null                 // 文字颜色
}
```

### 1.4 两种图表的分组层级结构

**业务对象图**：
```
Domain (D_xxx)
└── SubDomain (SD_xxx)
    └── ServiceModule (SM_xxx) [非末端]
        └── BusinessObject (BO_xxx) [末端节点]
```

**服务模块图**：
```
Domain (D_xxx)
└── SubDomain (SD_xxx)
    └── ServiceModule (SM_xxx) [末端节点]
```

### 1.5 `containers` vs `children` 的用途

| 属性 | 用途 | 使用场景 |
|------|------|---------|
| **children** | 分组层级结构 | `GroupModel` 合并、`UnifiedRenderer` 渲染、`getFlattenedGroups` 处理 disabled 提升 |
| **containers** | 控制面板显示和拖拽 | `GroupItem.vue` 渲染可拖拽的容器项目 |

---

## 二、数据流分析

### 2.1 完整数据流图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           控制面板 (LayoutControlPanel)                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ handleServiceModuleAutoGroup() → userConfig.groups                    │   │
│  │   - 使用 props.domainProducts 构建分组                                 │   │
│  │   - 服务模块作为 children 分组                                         │   │
│  │   - 输出: { groups: [...], enabled: true }                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    ↓
                    diagramConfigStore.layoutControlConfig
                                    ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                      useDiagramData (generateDiagram)                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 1. buildGroupModelFromArchitecture(architectureData, chartType)       │   │
│  │    - 输出: architectureGroups (分组树)                                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 2. GroupModel.fromUserConfig(architectureGroups, userConfig, chartType)│   │
│  │    - 合并 userConfig 到 architectureGroups                           │   │
│  │    - 输出: GroupModel 实例                                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 3. enrichGroupModel(groupModel, chartType, colorConfig)              │   │
│  │    - 添加颜色、标注等信息                                             │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    ↓                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ 4. UnifiedRenderer.render(groupModel, links, chartType)             │   │
│  │    - 输出: Mermaid 代码                                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 关键函数分析

#### 2.2.1 `buildGroupModelFromArchitecture` (`architectureProcessor.js`)

根据 `chartType` 调用不同的构建函数：

- `ChartType.SERVICE_MODULE` → `buildServiceModuleGroupModel()`
- `ChartType.BUSINESS_OBJECT` → `buildBusinessObjectGroupModel()`

**服务模块图构建逻辑**：
```javascript
function buildServiceModuleGroupModel(domainProducts, serviceModules) {
  domainProducts.forEach(domain => {
    // 创建 Domain 分组
    const domainGroup = createGroup({ type: DOMAIN, ... })

    domain.modules.forEach(subDomain => {
      // 创建 SubDomain 分组
      const subDomainGroup = createGroup({ type: SUB_DOMAIN, parentId: domainGroup.id, ... })

      subDomain.submodules.forEach(sm => {
        // 创建 ServiceModule 分组 (末端)
        const smGroup = createGroup({
          type: SERVICE_MODULE,
          parentId: subDomainGroup.id,
          elementRef: { code: sm.code, name: sm.name, ... }
        })
        subDomainGroup.children.push(smGroup)  // ← 作为 children
      })

      domainGroup.children.push(subDomainGroup)
    })

    rootGroups.push(domainGroup)
  })
}
```

#### 2.2.2 `GroupModel.fromUserConfig` (`GroupModel.js`)

合并用户配置到架构分组模型：

```javascript
static fromUserConfig(architectureGroups, userConfig, chartType) {
  // 1. 从 architectureGroups 构建 GroupModel
  const model = new GroupModel(architectureGroups, { chartType })

  // 2. 递归合并 userConfig.groups
  function mergeUserGroupRecursive(userGroup) {
    model.mergeUserGroup(userGroup)  // 按 ID/elementCode/title 匹配

    // 递归处理 children
    if (userGroup.children?.length > 0) {
      userGroup.children.forEach(child => mergeUserGroupRecursive(child))
    }
    // ⚠️ 注意：不处理 containers！
  }

  userConfig.groups.forEach(g => mergeUserGroupRecursive(g))
  return model
}
```

**匹配逻辑** (`mergeUserGroup`)：
1. 按 `id` 查找
2. 按 `elementCode` 查找
3. 按 `title` 查找

#### 2.2.3 `GroupModel.getFlattenedGroups` (`GroupModel.js`)

将分组树扁平化，处理 disabled 提升：

```javascript
processGroup(groupId, disabledAncestorPath = [], depth = 0) {
  const group = this.groups.get(groupId)
  const isEnabled = this.isEnabled(groupId)
  const isTerminal = isTerminalGroup(group, chartType)
  const inheritedDisabledPath = disabledAncestorPath.length > 0 ? disabledAncestorPath : null

  // 判断是否应该显示为 disabled（有 disabled 祖先但本身启用）
  const shouldDisplayAsDisabled = inheritedDisabledPath !== null && isEnabled

  if (!isEnabled) {
    // 禁用分组：跳过本身，处理子节点（传递路径）
    if (isTerminal) {
      result.push({ ...group, _disabledAncestorPath: effectiveDisabledPath })
    } else {
      group.children.forEach(childId => processGroup(childId, effectiveDisabledPath))
    }
    return
  }

  if (shouldDisplayAsDisabled) {
    // 有 disabled 祖先的分组：创建空 children 容器
    const entry = { ...group, _disabledAncestorPath, enabled: false, children: [] }
    result.push(entry)
    // 处理子节点，但不传递 disabled 路径
    group.children.forEach(childId => {
      const childResult = processGroup(childId, [])
      if (childResult) entry.children.push(childResult)
    })
    return entry
  }

  if (isTerminal) {
    // 末端分组
    result.push({ ...group, _disabledAncestorPath })
    return entry
  }

  // 普通非末端分组
  const newGroup = { ...group, children: [] }
  group.children.forEach(childId => {
    const childResult = processGroup(childId, [], depth + 1)
    if (childResult) newGroup.children.push(childResult)
  })
  result.push(newGroup)
  return newGroup
}
```

#### 2.2.4 `UnifiedRenderer.render` (`UnifiedRenderer.js`)

渲染扁平化的分组为 Mermaid 代码：

```javascript
static render(groupModel, links, chartType, options = {}) {
  const flattenedGroups = groupModel.getFlattenedGroups()

  // 构建 childIds 集合（用于判断根分组）
  const childIds = new Set()
  flattenedGroups.forEach(g => {
    g.children?.forEach(c => { if (c.id) childIds.add(c.id) })
  })

  // 根分组 = 不在任何其他分组 children 中的分组
  const rootGroups = flattenedGroups.filter(g => !childIds.has(g.id))

  rootGroups.forEach(group => {
    if (!processedGroups.has(group.id)) {
      code += UnifiedRenderer.renderGroupFromFlattened(group, flattenedGroups, chartType, 0, processedGroups)
    }
  })

  // 添加链接
  links.forEach(link => {
    code += `  ${sourceId} -->${label} ${targetId}\n`
  })

  return code
}

static renderGroupFromFlattened(group, flattenedGroups, chartType, depth, processedGroups) {
  const isTerminal = isTerminalGroup(group, chartType)

  if (isTerminal) {
    // 末端分组：渲染为节点
    return `${indent}${group.id}["${group.title}"]\n`
  } else {
    // 非末端分组：渲染为 subgraph
    const displayTitle = group._disabledAncestorPath?.length > 0
      ? `${group.title}（${group._disabledAncestorPath.join(' / ')}）`
      : group.title

    code += `${indent}subgraph ${group.id}["${displayTitle}"]\n`
    group.children.forEach(childRef => {
      const child = childRef.id ? childRef : childrenMap.get(childRef)
      if (child && !processedGroups.has(child.id)) {
        code += renderGroupFromFlattened(child, flattenedGroups, chartType, depth + 1, processedGroups)
      }
    })
    code += `${indent}end\n`
  }
}
```

### 2.3 控制面板渲染 (`GroupItem.vue`)

```html
<!-- containers 渲染（可拖拽的容器项目）-->
<div v-if="group.containers?.length > 0" class="assigned-containers">
  <div v-for="container in group.containers" :key="container.id">
    {{ container.name }}
  </div>
</div>

<!-- children 递归渲染（子分组）-->
<div v-if="group.children?.length > 0" class="children-container">
  <GroupItem
    v-for="child in group.children"
    :key="child.id"
    :group="child"
    :depth="depth + 1"
  />
</div>
```

---

## 三、两图表差异分析

### 3.1 核心差异表

| 差异点 | 业务对象图 | 服务模块图 |
|--------|-----------|-----------|
| **末端节点类型** | BUSINESS_OBJECT | SERVICE_MODULE |
| **分组层级深度** | 4 层 | 3 层 |
| **服务模块角色** | 中间层（可展开） | 末端（直接渲染为节点）|
| **handleAutoGroup** | `handleBusinessObjectAutoGroup` | `handleServiceModuleAutoGroup` |
| **containers 来源** | 用户拖拽分配的业务对象 | **无（服务模块是 children）** |
| **ID 生成** | `SM_xxx` | `SM_xxx` |
| **elementRef.code** | BO 编码 | SM 编码 |

### 3.2 `handleServiceModuleAutoGroup` vs `handleBusinessObjectAutoGroup`

**`handleServiceModuleAutoGroup`**：
```javascript
// 服务模块作为 children 分组
subDomainGroup.children.push({
  id: createGroupId(GroupType.SERVICE_MODULE, smCode),
  type: GroupType.SERVICE_MODULE,
  title: smName,
  elementRef: { type: SERVICE_MODULE, code: smCode, name: smName },
  parentId: subDomainGroup.id,
  // 无 containers
})
```

**`handleBusinessObjectAutoGroup`**：
```javascript
// 业务对象作为 containers
subDomainGroup.containers.push({
  id: boCode,
  name: boName,
  code: boCode,
  // ...
})
```

### 3.3 关键问题：服务模块图的 containers 为空

**问题描述**：
- `handleServiceModuleAutoGroup` 把服务模块添加到 `children`
- `GroupItem.vue` 渲染 `group.containers` 显示容器列表
- 服务模块图的 `group.containers` 始终为空（因为自动生成不添加到 containers）
- **结果**：用户看不到服务模块节点，需要手动拖拽分配

**业务对象图正常的原因**：
- `handleBusinessObjectAutoGroup` 把业务对象添加到 `containers`
- `GroupItem.vue` 直接渲染 `group.containers`
- 用户在控制面板中能看到业务对象列表

---

## 四、问题诊断

### 4.1 当前问题现象

1. **控制面板**：服务模块显示为分组（children 递归渲染），不是容器列表
2. **图表渲染**：disabled 父分组时，子分组/服务模块不显示或提升不正确

### 4.2 可能的问题原因

#### 问题 1：数据结构不一致

| 来源 | 服务模块位置 | ID 格式 |
|------|-------------|---------|
| `handleServiceModuleAutoGroup` | children | `SM_xxx` |
| `buildServiceModuleGroupModel` | children | `SM_xxx` (通过 `createGroupId`) |

**检查点**：两处生成的 ID 是否一致？`elementRef.code` 是否匹配？

#### 问题 2：合并逻辑问题

`mergeUserGroupRecursive` 只处理 `children`，不处理 `containers`。如果 `userConfig.groups` 中的服务模块分组与 `architectureGroups` 中的 ID 不匹配，合并会失败。

**检查点**：控制台日志 `[mergeUserGroup] NO MATCH FOUND`

#### 问题 3：getFlattenedGroups 的 children 处理

在 `shouldDisplayAsDisabled` 分支中：
```javascript
const entry = { ...group, _disabledAncestorPath, enabled: false, children: [] }
result.push(entry)
group.children.forEach(childId => {
  const childResult = processGroup(childId, [])  // 空路径！
  if (childResult) entry.children.push(childResult)
})
```

子节点处理时传递了空路径 `[]`，这可能导致子节点没有被正确添加到 `entry.children`。

**检查点**：控制台日志 `[processGroup] Non-terminal xxx, children after processing: 0`

#### 问题 4：UnifiedRenderer 的 rootGroups 判断

```javascript
const childIds = new Set()
flattenedGroups.forEach(g => {
  g.children?.forEach(c => { if (c.id) childIds.add(c.id) })
})
const rootGroups = flattenedGroups.filter(g => !childIds.has(g.id))
```

如果服务模块分组被错误地添加到 `childIds` 集合，它会被排除在 `rootGroups` 之外，导致不会被渲染。

**检查点**：控制台日志 `[UnifiedRenderer] rootGroups count`

---

## 五、调试建议

### 5.1 关键日志位置

1. **`handleServiceModuleAutoGroup`**：
   - `[handleServiceModuleAutoGroup] Final groups count`
   - `[handleServiceModuleAutoGroup] Groups structure`

2. **`GroupModel.buildIndex`**：
   - `[GroupModel.buildIndex] All groups`

3. **`GroupModel.fromUserConfig`**：
   - `[fromUserConfig] userConfig.groups`
   - `[mergeUserGroup] NO MATCH FOUND`

4. **`GroupModel.getFlattenedGroups`**：
   - `[GroupModel.getFlattenedGroups] All groups`
   - `[processGroup] children after processing`

5. **`UnifiedRenderer.render`**：
   - `[UnifiedRenderer] rootGroups count`
   - `[UnifiedRenderer] flattenedGroups count`

### 5.2 建议的验证步骤

1. **验证 ID 一致性**：
   ```javascript
   // 在 handleServiceModuleAutoGroup 中
   console.log('SM ID:', smGroupId, 'elementRef.code:', smCode)

   // 在 buildServiceModuleGroupModel 中
   console.log('SM ID:', smGroup.id, 'elementRef.code:', smGroup.elementRef?.code)
   ```

2. **验证合并成功**：
   - 检查是否有 `[mergeUserGroup] NO MATCH FOUND` 日志

3. **验证 getFlattenedGroups 输出**：
   - 检查 `children after processing` 是否大于 0

4. **验证 UnifiedRenderer 输入**：
   - 检查 `rootGroups` 是否包含应该显示的分组

---

## 六、结论

### 6.1 当前架构评估

**统一模型的优势**：
- `GroupModel`、`getFlattenedGroups`、`UnifiedRenderer` 是共用的
- 分组层级结构定义清晰
- disabled 提升逻辑集中管理

**潜在问题点**：
- `handleServiceModuleAutoGroup` 和 `handleBusinessObjectAutoGroup` 结构不同
- `containers` 和 `children` 的用途混淆
- 服务模块图的 `containers` 为空，可能导致 UI 显示问题

### 6.2 需要确认的设计决策

1. **服务模块图的 containers 应该填什么？**
   - 方案 A：保持为空，用户手动分配
   - 方案 B：自动填充服务模块到 containers（与 BO 图一致）

2. **控制面板应该如何显示服务模块？**
   - 方案 A：作为分组树显示（children 递归）
   - 方案 B：作为容器列表显示（containers）

3. **disabled 提升的预期行为是什么？**
   - 禁用领域后，子领域应该提升到根级别？
   - 服务模块应该作为子领域的 children 还是提升到更高层级？

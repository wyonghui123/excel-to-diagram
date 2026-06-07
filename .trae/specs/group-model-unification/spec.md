# 服务模块图数据模型统一 - 安全变更方案

## 背景

当前服务模块图和业务对象图使用了不同的分组构建逻辑，导致 disabled 状态无法正确合并。

**问题根因**：
- `handleServiceModuleAutoGroup()` 使用 `props.containers`（扁平结构）构建分组
- `buildServiceModuleGroupModel()` 使用 `filteredDomainProducts`（层级结构）构建分组
- 两种结构不一致：子领域分组在 `userConfig` 中有 `containers`，但在 `architectureGroups` 中只有 `children`

## 变更目标

让服务模块图复用业务对象图的数据模型，确保：
1. `userConfig.groups` 和 `architectureGroups` 结构一致
2. disabled 状态能正确合并
3. 子领域（`全球司库`、`费控服务`等）在父领域（`财务云`）禁用时能正确提升显示

## 变更方案

### 核心思路

**不创建新的转换层**，而是让服务模块图直接使用 `filteredDomainProducts` 构建分组，与业务对象图保持一致。

### 具体变更

#### 变更 1：`useDiagramData.js` - 服务模块图使用相同的 ChartType

**文件**：`src/views/AADiagramApp/composables/useDiagramData.js`

**位置**：约 L996-1027

**现状**：
```javascript
let architectureGroups = buildGroupModelFromArchitecture(architectureData, ChartType.SERVICE_MODULE)
```

**变更后**：
```javascript
// 服务模块图和业务对象图使用相同的分组构建逻辑
let architectureGroups = buildGroupModelFromArchitecture(architectureData, ChartType.BUSINESS_OBJECT)
```

#### 变更 2：`LayoutControlPanel.vue` - 服务模块图分组构建使用 domainProducts

**文件**：`src/views/AADiagramApp/components/LayoutControlPanel.vue`

**函数**：`handleServiceModuleAutoGroup()`

**现状**：
```javascript
// 使用 props.containers（filteredContainers）构建分组
props.containers.forEach(container => {
  const domainName = container.domain || '未分类'
  // ...
})
```

**变更后**：
```javascript
// 直接使用 props.domainProducts 构建分组，与业务对象图一致
props.domainProducts.forEach(domain => {
  const domainGroup = {
    id: createGroupId(GroupType.DOMAIN, domain.code || domain.name),
    title: domain.name,
    elementCode: domain.code || domain.name,
    groupType: 'domain',
    children: []
  }

  domain.modules?.forEach(module => {
    const subDomainGroup = {
      id: createGroupId(GroupType.SUB_DOMAIN, module.code || module.name),
      title: module.name,
      elementCode: module.code || module.name,
      groupType: 'subDomain',
      children: []
    }

    module.submodules?.forEach(sm => {
      subDomainGroup.children.push({
        id: createGroupId(GroupType.SERVICE_MODULE, sm.code),
        title: sm.name,
        elementCode: sm.code,
        groupType: 'serviceModule'
      })
    })

    domainGroup.children.push(subDomainGroup)
  })

  groups.push(domainGroup)
})
```

#### 变更 3：统一 ID 生成逻辑

**确保**：
- 领域 ID：`D_财务云` (GroupType.DOMAIN + '财务云')
- 子领域 ID：`SD_全球司库` (GroupType.SUB_DOMAIN + '全球司库')
- 服务模块 ID：`SM_STWB` (GroupType.SERVICE_MODULE + 'STWB')

## 回滚方案

如果变更后出现问题，可以通过以下方式回滚：
1. 恢复 `ChartType.SERVICE_MODULE`
2. 恢复使用 `props.containers`

## 验证步骤

1. 生成服务模块图，禁用 `财务云`
2. 确认 `全球司库`、`费控服务` 等子领域正确提升显示
3. 确认控制台无错误

## 影响范围

- `useDiagramData.js`：服务模块图数据构建
- `LayoutControlPanel.vue`：服务模块图分组控制面板
- 无新增文件
- 无破坏性变更（保持回滚能力）

# 统一分组模型 - containers 与 children 分离方案

## Why

当前服务模块图和业务对象图存在以下问题：
1. **containers vs children 用途混淆**：业务对象图的 BO 在 `containers`，服务模块图的 SM 在 `children`
2. **控制面板显示不一致**：业务对象图显示节点列表，服务模块图显示分组树
3. **图表渲染逻辑不统一**：`toMermaidConfig` 从 `containers` 渲染，`UnifiedRenderer` 从 `children` 渲染

## 上一次 spec 失败原因分析

上一次 spec（第81行）把服务模块放入了 `children`：
```javascript
subDomainGroup.children.push({  // ← 问题在这里
  id: createGroupId(GroupType.SERVICE_MODULE, sm.code),
  ...
})
```

**这是错误的**，因为：
- 业务对象图：BO 在 `containers`，SM 在 `children`
- 上一次 spec 的方案：SM 在 `children`

这导致两个图表类型的节点位置不一致，控制面板显示不同。

## What Changes

### 核心设计原则

1. **节点统一放 `containers`**：无论是 BO 还是 SM，都放在 `containers`
2. **`children` 只用于分层结构**：Domain → SubDomain → ... → containers
3. **图表渲染统一**：从 `containers` 取终端节点

### 统一分组模型结构

**业务对象图**：
```
Domain (D_xxx)
├── children: [SubDomain]
└── containers: []  // 无终端节点

SubDomain (SD_xxx)
├── parentId: 'D_xxx'
├── children: [ServiceModule]
└── containers: []  // 无终端节点

ServiceModule (SM_xxx)
├── parentId: 'SD_xxx'
├── children: []  // 无子分组
└── containers: [BO_001, BO_002, ...]  // BO 作为终端节点

BusinessObject 节点 (BO_xxx)
└── parentId: 'SM_xxx'
```

**服务模块图**：
```
Domain (D_xxx)
├── children: [SubDomain]
└── containers: []  // 无终端节点

SubDomain (SD_xxx)
├── parentId: 'D_xxx'
├── children: []  // 无子分组
└── containers: [SM_001, SM_002, ...]  // SM 作为终端节点

ServiceModule 节点 (SM_xxx)
└── parentId: 'SD_xxx'
```

**关键差异**：服务模块图的 SM 是末端节点，没有子分组层级。

### 图表类型区分

| 图表类型 | 末端节点 | 节点位置 |
|---------|---------|---------|
| 业务对象图 | BO | SM 的 `containers` |
| 服务模块图 | SM | SubDomain 的 `containers` |

### 渲染统一

`UnifiedRenderer` 从 `containers` 取终端节点，不再区分 children 和终端节点。

## ADDED Requirements

### Requirement: buildServiceModuleGroupModel 修改

`buildServiceModuleGroupModel` SHALL 遵循统一模型：
- 服务模块作为 `containers` 添加到 SubDomain 分组
- 不再将服务模块作为 `children`

#### Scenario: 构建服务模块图架构分组
- **WHEN** 调用 buildServiceModuleGroupModel(domainProducts, serviceModules)
- **THEN** 创建 Domain → SubDomain 分层结构，SM 节点添加到 SubDomain 的 `containers`

### Requirement: handleServiceModuleAutoGroup 修改

`handleServiceModuleAutoGroup` SHALL 遵循统一模型：
- 服务模块作为 `containers` 分配到 SubDomain 分组
- `children` 仅用于 Domain → SubDomain 分层结构

#### Scenario: 自动生成服务模块图分组
- **WHEN** 调用 handleServiceModuleAutoGroup
- **THEN** 创建 Domain → SubDomain 分层结构，SM 节点添加到 SubDomain 的 `containers`

### Requirement: UnifiedRenderer 从 containers 取终端

`UnifiedRenderer` SHALL 从 `containers` 取终端节点：
- 不再从 `children` 判断终端
- 遍历 `containers` 找到末端节点

#### Scenario: UnifiedRenderer 渲染服务模块图
- **WHEN** 调用 UnifiedRenderer.render(groupModel, links, ChartType.SERVICE_MODULE)
- **THEN** 遍历 `group.containers` 找到 SM 终端节点并渲染为 Mermaid 节点

### Requirement: GroupItem.vue 从 containers 渲染

`GroupItem.vue` SHALL 从 `containers` 渲染节点列表：
- 服务模块图从 SubDomain.containers 渲染 SM 节点列表
- 业务对象图从 SM.containers 渲染 BO 节点列表

#### Scenario: 控制面板显示节点列表
- **WHEN** 渲染控制面板中的分组
- **THEN** 从 `group.containers` 渲染节点列表

## MODIFIED Requirements

### Requirement: getFlattenedGroups 处理 containers

`getFlattenedGroups` SHALL 处理 `containers` 中的终端节点：
- 当分组有 `containers` 时，`containers` 中的节点是末端
- 当分组无 `containers` 但有 `children` 时，递归处理 `children`

#### Scenario: 处理有 containers 的分组
- **WHEN** 处理 SubDomain 分组且其 `containers` 包含 SM 节点
- **THEN** SM 节点作为末端添加到结果，`enabled`/`disabled` 状态继承

## Implementation Plan

### 步骤 1：修改 buildServiceModuleGroupModel

修改 `src/services/groupModel/architectureProcessor.js` 中的 `buildServiceModuleGroupModel`：
- 将服务模块从 `children` 改为 `containers`

### 步骤 2：修改 handleServiceModuleAutoGroup

修改 `src/views/AADiagramApp/components/LayoutControlPanel.vue` 中的 `handleServiceModuleAutoGroup`：
- 将服务模块从 `children` 改为 `containers`
- 确保与 buildServiceModuleGroupModel 输出结构一致

### 步骤 3：修改 UnifiedRenderer / getFlattenedGroups

修改 `src/services/groupModel/GroupModel.js`：
- 从 `containers` 取终端节点，而不是从 `children`

### 步骤 4：验证

- [ ] 服务模块图的 containers 包含 SM 节点
- [ ] 控制面板显示 SM 节点列表
- [ ] 禁用父分组后，SM 节点正确提升
- [ ] 业务对象图和服务模块图渲染行为一致

## Impact

- Affected code:
  - `src/services/groupModel/architectureProcessor.js` — buildServiceModuleGroupModel
  - `src/views/AADiagramApp/components/LayoutControlPanel.vue` — handleServiceModuleAutoGroup
  - `src/services/groupModel/GroupModel.js` — getFlattenedGroups
  - `src/services/groupModel/UnifiedRenderer.js` — 渲染逻辑

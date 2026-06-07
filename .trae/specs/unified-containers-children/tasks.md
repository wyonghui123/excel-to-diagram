# Tasks - 统一 containers 与 children 分离方案

## 前置分析（已完成）

已分析上一次 spec 失败原因：把服务模块错误地放入了 `children` 而非 `containers`。

## 核心任务

### Task 1: 修改 buildServiceModuleGroupModel

修改 `src/services/groupModel/architectureProcessor.js` 中的 `buildServiceModuleGroupModel`：

**关键变更**：将 `subDomainGroup.children.push(smGroup)` 改为 `subDomainGroup.containers.push(smGroup)`

```javascript
// 修改前（第214行）
subDomainGroup.children.push(smGroup)

// 修改后
subDomainGroup.containers.push(smGroup)
```

### Task 2: 修改 handleServiceModuleAutoGroup

修改 `src/views/AADiagramApp/components/LayoutControlPanel.vue` 中的 `handleServiceModuleAutoGroup`：

**关键变更**：将服务模块从 `children` 改为 `containers`

```javascript
// 修改前
subDomainGroup.children.push({
  id: createGroupId(GroupType.SERVICE_MODULE, smCode),
  title: smName,
  type: GroupType.SERVICE_MODULE,
  // ...
})

// 修改后
subDomainGroup.containers.push({
  id: smCode,  // 与 buildServiceModuleGroupModel 一致
  name: smName,
  code: smCode,
  type: GroupType.SERVICE_MODULE,
  parentId: subDomainGroup.id,
  // ...
})
```

### Task 3: 修改 getFlattenedGroups

修改 `src/services/groupModel/GroupModel.js`：

**关键变更**：从 `containers` 取终端节点

- 判断是否为终端分组：检查 `group.containers?.length > 0`
- 终端节点在 `containers` 中，不在 `children` 中

### Task 4: 修改 UnifiedRenderer

修改 `src/services/groupModel/UnifiedRenderer.js`：

**关键变更**：从 `containers` 渲染终端节点

- 遍历 `group.containers` 找到终端节点
- 不再从 `children` 判断终端

### Task 5: 验证

- [ ] Task 5.1: 验证服务模块图的 containers 包含 SM 节点
- [ ] Task 5.2: 验证控制面板显示 SM 节点列表（从 containers）
- [ ] Task 5.3: 验证禁用父分组后 SM 正确提升
- [ ] Task 5.4: 验证业务对象图不受影响

## Task Dependencies

```
Task 1 (buildServiceModuleGroupModel) ─┐
                                       ├─→ Task 3 (getFlattenedGroups) ─→ Task 4 (UnifiedRenderer)
Task 2 (handleServiceModuleAutoGroup) ─┘
                                                  │
                                                  ↓
                                            Task 5 (验证)
```

## 详细步骤

### Task 1: 修改 buildServiceModuleGroupModel

1. 打开 `src/services/groupModel/architectureProcessor.js`
2. 找到第214行 `subDomainGroup.children.push(smGroup)`
3. 改为 `subDomainGroup.containers.push(smGroup)`
4. 确保 `smGroup` 对象的 `parentId` 设置为 `subDomainGroup.id`

### Task 2: 修改 handleServiceModuleAutoGroup

1. 打开 `src/views/AADiagramApp/components/LayoutControlPanel.vue`
2. 找到 `handleServiceModuleAutoGroup` 函数中的 `subDomainGroup.children.push({...})`
3. 改为 `subDomainGroup.containers.push({...})`
4. 确保 ID 格式与 buildServiceModuleGroupModel 一致

### Task 3: 修改 getFlattenedGroups

1. 打开 `src/services/groupModel/GroupModel.js`
2. 找到 `isTerminal` 判断逻辑
3. 修改为检查 `group.containers?.length > 0` 而非 `!group.children || group.children.length === 0`
4. 确保容器中的终端节点被正确处理

### Task 4: 修改 UnifiedRenderer

1. 打开 `src/services/groupModel/UnifiedRenderer.js`
2. 修改 `renderGroupFromFlattened` 方法
3. 从 `group.containers` 遍历渲染终端节点

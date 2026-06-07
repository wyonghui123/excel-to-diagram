# Checklist - 统一 containers 与 children 分离方案

## 代码变更检查

### buildServiceModuleGroupModel 变更

- [ ] 第214行 `subDomainGroup.children.push(smGroup)` 改为 `subDomainGroup.containers.push(smGroup)`
- [ ] `smGroup` 对象的 `parentId` 设置为 `subDomainGroup.id`

### handleServiceModuleAutoGroup 变更

- [ ] 服务模块添加到 `subDomainGroup.containers` 而不是 `children`
- [ ] ID 格式与 buildServiceModuleGroupModel 一致（使用 smCode 而不是 createGroupId）
- [ ] `parentId` 设置正确

### getFlattenedGroups 变更

- [ ] `isTerminal` 判断逻辑修改：检查 `group.containers?.length > 0`
- [ ] 终端节点从 `containers` 处理，不再从 `children` 判断
- [ ] disabled 状态正确传递给 containers 中的终端节点

### UnifiedRenderer 变更

- [ ] 从 `group.containers` 遍历渲染终端节点
- [ ] 不再从 `children` 判断终端

## 功能验证检查

### 服务模块图自动分组

- [ ] 自动分组后，Domain 和 SubDomain 在 `children` 中
- [ ] SM 节点在 SubDomain 的 `containers` 中（不是 children）
- [ ] 控制面板显示 SM 节点列表（从 containers 渲染）

### 禁用父分组

- [ ] 禁用 `财务云` 领域后，`全球司库` 等子领域正确提升
- [ ] SM 节点跟随子领域一起提升
- [ ] 提升后的 SM 节点正确显示

### 图表渲染

- [ ] `window.__configStore.useUnifiedRenderer = true` 时启用统一渲染
- [ ] SM 节点正确渲染为 Mermaid 节点
- [ ] 禁用分组的虚线样式正确显示

### 业务对象图不受影响

- [ ] 业务对象图的 BO 仍在 SM 的 `containers` 中
- [ ] 控制面板显示 BO 节点列表
- [ ] 禁用父分组后 BO 正确提升

## 回归测试

- [ ] 服务模块图自动分组功能正常
- [ ] 服务模块图禁用/启用分组功能正常
- [ ] 业务对象图自动分组功能正常
- [ ] 业务对象图禁用/启用分组功能正常
- [ ] 控制台无错误输出

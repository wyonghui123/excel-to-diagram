# 服务模块图数据模型统一 - 任务清单

## 任务列表

### 阶段一：备份和准备工作

- [x] **T1.1**: 备份当前 `useDiagramData.js` 中的服务模块图数据构建代码
  - 位置：约 L996-1027
  - 内容：`buildServiceModuleGroupModel()` 调用部分

- [x] **T1.2**: 备份当前 `LayoutControlPanel.vue` 中的 `handleServiceModuleAutoGroup()` 函数
  - 位置：约 L447-526
  - 记录原始实现的关键逻辑

### 阶段二：变更 `useDiagramData.js`

- [x] **T2.1**: 修改服务模块图的 `ChartType`
  - 文件：`src/views/AADiagramApp/composables/useDiagramData.js`
  - 位置：约 L996-1027
  - 变更：将 `ChartType.SERVICE_MODULE` 改为 `ChartType.BUSINESS_OBJECT`
  - 变更前：`let architectureGroups = buildGroupModelFromArchitecture(architectureData, ChartType.SERVICE_MODULE)`
  - 变更后：`let architectureGroups = buildGroupModelFromArchitecture(architectureData, ChartType.BUSINESS_OBJECT)`

- [x] **T2.2**: 验证 `buildGroupModelFromArchitecture()` 对 BUSINESS_OBJECT 的处理
  - 确认它调用的是 `buildBusinessObjectGroupModel()`
  - 确认返回的分组结构包含 SUB_DOMAIN 层级

### 阶段三：变更 `LayoutControlPanel.vue`

- [x] **T3.1**: 修改 `handleServiceModuleAutoGroup()` 使用 `props.domainProducts`
  - 文件：`src/views/AADiagramApp/components/LayoutControlPanel.vue`
  - 变更：使用 `props.domainProducts` 替代 `props.containers`
  - 确保 ID 生成使用 `createGroupId()` 与 `architectureGroups` 一致

- [x] **T3.2**: 验证分组结构与业务对象图一致
  - DOMAIN → SUB_DOMAIN → SERVICE_MODULE
  - 每个层级的 ID 格式正确

### 阶段四：验证和测试

- [ ] **T4.1**: 生成服务模块图，禁用 `财务云`
  - 预期：`全球司库`、`费控服务` 等子领域正确提升显示
  - 检查控制台日志

- [ ] **T4.2**: 验证 `mergeUserGroup` 日志
  - `[mergeUserGroup] Lookup by id: D_财务云 found: true`
  - `[mergeUserGroup] Set layout.enabled to: false for group: 财务云`

- [ ] **T4.3**: 验证 `toMermaidConfig` 日志
  - `[toMermaidConfig] 财务云 returned null, lifting its children to root level`
  - 子领域分组被正确提升

### 阶段五：回滚准备（仅在需要时）

- [ ] **T5.1**: 如果验证失败，恢复 `ChartType.SERVICE_MODULE`
- [ ] **T5.2**: 如果验证失败，恢复 `handleServiceModuleAutoGroup()` 使用 `props.containers`

## 任务依赖关系

```
T1.1, T1.2 (备份) ✓
    ↓
T2.1, T2.2 (变更 useDiagramData.js) ✓
    ↓
T3.1, T3.2 (变更 LayoutControlPanel.vue) ✓
    ↓
T4.1, T4.2, T4.3 (验证测试)
    ↓
T5.1, T5.2 (回滚，仅在需要时)
```

## 预计工作量

- 备份和准备：10 分钟 ✓
- 变更 useDiagramData.js：5 分钟 ✓
- 变更 LayoutControlPanel.vue：15 分钟 ✓
- 验证测试：10 分钟
- **总计**：约 40 分钟

## 关键检查点

1. **ID 匹配**：userConfig.groups 和 architectureGroups 的 ID 必须一致
2. **结构匹配**：两个数据源的分组结构必须一致
3. **合并成功**：mergeUserGroup 必须能正确匹配并合并 enabled 状态
4. **提升显示**：disabled 父分组的子分组必须能正确提升显示

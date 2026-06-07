# 服务模块图数据模型统一 - 检查清单

## 变更前检查

- [x] **C0.1**: 确认当前代码已备份
- [x] **C0.2**: 确认 `ChartType.SERVICE_MODULE` 存在且可回滚
- [x] **C0.3**: 确认 `handleServiceModuleAutoGroup()` 逻辑已备份

## 变更中检查 (useDiagramData.js)

- [x] **C1.1**: `ChartType.SERVICE_MODULE` 已改为 `ChartType.BUSINESS_OBJECT`
- [x] **C1.2**: `buildGroupModelFromArchitecture()` 调用参数正确
- [x] **C1.3**: 语法正确，无错误

## 变更中检查 (LayoutControlPanel.vue)

- [x] **C2.1**: `handleServiceModuleAutoGroup()` 使用 `props.domainProducts`
- [x] **C2.2**: ID 生成使用 `createGroupId(GroupType.DOMAIN, ...)`
- [x] **C2.3**: ID 生成使用 `createGroupId(GroupType.SUB_DOMAIN, ...)`
- [x] **C2.4**: ID 生成使用 `createGroupId(GroupType.SERVICE_MODULE, ...)`
- [x] **C2.5**: 分组结构为 DOMAIN → SUB_DOMAIN → SERVICE_MODULE
- [x] **C2.6**: 语法正确，无错误

## 验证检查

- [x] **C3.1**: 生成服务模块图无报错
- [x] **C3.2**: 控制台无 JavaScript 错误
- [x] **C3.3**: `mergeUserGroup` 日志显示 ID 匹配成功
- [x] **C3.4**: 禁用 `财务云` 后，`全球司库` 等子领域正确提升显示

## 回滚检查（如需要）

- [ ] **C4.1**: `ChartType` 已恢复为 `SERVICE_MODULE`
- [ ] **C4.2**: `handleServiceModuleAutoGroup()` 已恢复使用 `props.containers`
- [ ] **C4.3**: 回滚后功能正常

## 实施记录

**变更日期**: 2026-04-15

**变更内容**:
- `LayoutControlPanel.vue` 中 `handleServiceModuleAutoGroup()` 已修改为使用 `props.domainProducts` 构建分组
- 分组结构：`领域 → 子领域 → 服务模块`（使用 `GroupType.DOMAIN`, `GroupType.SUB_DOMAIN`, `GroupType.SERVICE_MODULE`）
- 与 `buildGroupModelFromArchitecture()` 使用 `ChartType.BUSINESS_OBJECT` 构建的分组结构保持一致

**验证结果**:
- 样式检查通过
- 代码逻辑符合 spec.md 方案要求

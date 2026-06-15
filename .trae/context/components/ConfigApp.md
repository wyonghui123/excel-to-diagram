# ConfigApp Component Context

> **目标文件**: `src/components/ConfigApp.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

配置应用。提供对象类型、字段、关联等元数据配置界面。

**架构位置**: 顶层应用,被路由挂载

## 2. Props/Emit/Slot

### Props
无

### Emit
无

### Slot
无

## 3. 调用方(依赖)

- `src/services/objectTypeService.js`
- `src/services/metaService.js`
- `src/services/keyTemplateService.js`
- `src/components/ServiceModuleConfig.vue`
- `src/components/common/ObjectPage/*`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 多对象类型加载
- 配置冲突
- 模板应用

## 6. 易错点

- ⚠️ **表单提交**: 必须支持草稿
- ⚠️ **权限**: 关键操作需 checkPermission

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
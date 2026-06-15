# AssignmentDialog Component Context

> **目标文件**: `src/components/common/AssignmentDialog/AssignmentDialog.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

分配对话框。将 BO 分配给指定用户/角色/部门。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | Boolean | `false` | 显隐 |
| `boIds` | String[] | `[]` | 要分配的 BO ID |
| `assignType` | String | `'user'` | user / role / department |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 显隐 |
| `success` | - | 成功 |

## 3. 调用方(依赖)

- `src/services/boService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 批量分配
- 已分配对象
- 权限校验

## 6. 易错点

- ⚠️ **通知**: 分配后必须通知被分配人
- ⚠️ **审计**: 必须写审计日志

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
# ObjectPageHeader Component Context

> **目标文件**: `src/components/common/ObjectPage/ObjectPageHeader.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

ObjectPage 头部。展示对象标题、状态、关键操作按钮。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `title` | String | `''` | 标题 |
| `subtitle` | String | `''` | 副标题 |
| `status` | String | `''` | 状态 |
| `actions` | Action[] | `[]` | 操作按钮 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `action` | `{action}` | 操作点击 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 自定义头部内容 |
| `actions` | 自定义操作区 |

## 3. 调用方(依赖)

- `src/components/bo/StateTransitionButton(s).vue`
- `src/components/common/AppButton.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 标题过长
- 操作按钮过多(>5)
- 状态变化闪烁

## 6. 易错点

- ⚠️ **权限**: 操作按钮按权限显示

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
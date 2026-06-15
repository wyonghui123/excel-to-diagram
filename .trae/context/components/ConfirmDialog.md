# ConfirmDialog Component Context

> **目标文件**: `src/components/common/ConfirmDialog.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **YonDesign**: [OK]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

确认对话框。基于 AppModal 二次封装,提供 OK/Cancel 确认操作。

**架构位置**: 通用交互组件

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | Boolean | `false` | v-model |
| `title` | String | `'确认'` | 标题 |
| `message` | String | `''` | 内容 |
| `type` | String | `'warning'` | warning / info / danger / success |
| `confirmText` | String | `'确定'` | 确认按钮 |
| `cancelText` | String | `'取消'` | 取消按钮 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 显隐 |
| `confirm` | - | 确认 |
| `cancel` | - | 取消 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 自定义内容 |

## 3. 调用方(依赖)

- `src/components/common/AppModal.vue`
- `src/components/common/AppAlert.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

**目标**: ≥ 90%

## 5. 边界场景

- 长内容滚动
- 危险操作二次确认

## 6. 易错点

- ⚠️ **danger**: 危险操作必须用红色按钮
- ⚠️ **二次确认**: 删除等高危操作必须

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
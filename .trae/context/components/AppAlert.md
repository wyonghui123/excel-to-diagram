# AppAlert Component Context

> **目标文件**: `src/components/common/AppAlert/AppAlert.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ✅ 100% (17 tests)

## 1. 职责 (What)

通用警告/提示。基于 Element Plus `<el-alert>` 封装。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `type` | String | `'info'` | success / warning / info / error |
| `title` | String | `''` | 标题 |
| `description` | String | `''` | 描述 |
| `closable` | Boolean | `false` | 可关闭 |
| `showIcon` | Boolean | `true` | 显示图标 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `close` | - | 关闭 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 内容 |
| `title` | 自定义标题 |

## 3. 调用方

- Element Plus `<el-alert>`
- `src/components/ValidationPanel.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ✅ 100% (17 tests) |
| E2E | [OK] 间接验证 |

**目标**: ≥ 90%(基础组件) ✅ 已达成

## 5. 边界场景

- 自动关闭(配合 Notification)
- 长描述滚动

## 6. 易错点

- ⚠️ **type**: 必须 YonDesign token

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
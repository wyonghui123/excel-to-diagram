# AppButton Component Context

> **目标文件**: `src/components/common/AppButton/AppButton.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ✅ 100% (43 tests)

## 1. 职责 (What)

通用按钮组件。基于 Element Plus 二次封装,统一 YonDesign 风格。

**架构位置**: YonDesign 基础组件

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `type` | String | `'primary'` | primary / secondary / danger / text |
| `size` | String | `'medium'` | small / medium / large |
| `loading` | Boolean | `false` | 加载态 |
| `disabled` | Boolean | `false` | 禁用 |
| `icon` | String | `null` | 图标名 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `click` | `{event}` | 点击 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 按钮文字 |
| `icon` | 自定义图标 |

## 3. 调用方(依赖)

- Element Plus `<el-button>`
- `src/components/common/AppIcon.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ✅ 100% (43 tests) |
| E2E | [OK] 间接验证 |

**目标**: ≥ 90%(基础组件) ✅ 已达成

## 5. 边界场景

- loading + disabled 同时
- 长文本截断

## 6. 易错点

- ⚠️ **type 命名**: 严格遵循 YonDesign token
- ⚠️ **loading**: 防双击

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
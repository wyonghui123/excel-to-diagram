# AppIcon Component Context

> **目标文件**: `src/components/common/AppIcon/AppIcon.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ✅ 100% (55 tests)

## 1. 职责 (What)

统一图标组件。封装 Iconify/Element Plus 图标,统一 YonDesign 图标 token。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `name` | String | `''` | 图标名(如 `ep:plus`)
| `size` | String/Number | `'16px'` | 大小 |
| `color` | String | `''` | 颜色 |

### Slot
无

## 3. 调用方

- `@iconify/vue` 或 `element-plus/icons-vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ✅ 100% (55 tests) |
| E2E | [OK] 间接验证 |

**目标**: ≥ 90%(基础组件) ✅ 已达成

## 5. 边界场景

- 图标不存在
- 自定义 SVG

## 6. 易错点

- ⚠️ **图标库**: 统一前缀(ep: / mdi:)
- ⚠️ **fallback**: 未知图标显示 ?

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
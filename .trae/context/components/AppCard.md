# AppCard Component Context

> **目标文件**: `src/components/common/AppCard/AppCard.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ✅ 100% (61 tests)

## 1. 职责 (What)

通用卡片。基于 Element Plus `<el-card>` 封装。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `shadow` | String | `'always'` | always / hover / never |
| `header` | String | `''` | 头部 |
| `bodyStyle` | Object | `{}` | 内容样式 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 内容 |
| `header` | 自定义头部 |

## 3. 调用方

- Element Plus `<el-card>`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ✅ 100% (61 tests) |
| E2E | [OK] 间接验证 |

**目标**: ≥ 90%(基础组件) ✅ 已达成

## 5. 边界场景

- 极长内容
- 嵌套卡片

## 6. 易错点

- ⚠️ **shadow**: 统一 token

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
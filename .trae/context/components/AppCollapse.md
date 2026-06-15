# AppCollapse Component Context

> **目标文件**: `src/components/common/AppCollapse/AppCollapse.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ✅ 100% (60 tests)

## 1. 职责 (What)

折叠面板。基于 Element Plus `<el-collapse>` 封装。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | String[] | `[]` | 展开项(v-model)
| `accordion` | Boolean | `false` | 手风琴模式 |
| `bordered` | Boolean | `true` | 显示边框 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 展开项变化 |
| `change` | `{value}` | 同上 |

### Slot
| Name | Description |
|------|-------------|
| `<item-name>` | 自定义每项内容 |

## 3. 调用方

- Element Plus `<el-collapse>`
- `src/components/common/CollapsiblePanel/`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ✅ 100% (60 tests) |
| E2E | [OK] 间接验证 |

**目标**: ≥ 90%(基础组件) ✅ 已达成

## 5. 边界场景

- 大量 panel(>20)
- 嵌套折叠

## 6. 易错点

- ⚠️ **手风琴**: activeNames 必须是单个

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
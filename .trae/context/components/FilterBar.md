# FilterBar Component Context

> **目标文件**: `src/components/common/FilterBar/FilterBar.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

筛选条。通用筛选条件输入区域,支持多种字段类型筛选。

**架构位置**: MetaListPage、MultiObjectManagementPage 等的标配

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `filters` | FilterField[] | `[]` | 筛选字段定义 |
| `modelValue` | FilterValue | `{}` | 当前值(v-model)
| `collapsible` | Boolean | `true` | 可折叠 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 筛选变化 |
| `search` | `{value}` | 搜索 |
| `reset` | - | 重置 |

### Slot
| Name | Description |
|------|-------------|
| `field-<key>` | 自定义筛选字段 |
| `extra` | 额外操作 |

## 3. 调用方(依赖)

- `src/components/common/AppInput.vue`
- `src/components/common/AppSelect.vue`
- `src/components/common/EnumSelect.vue`
- `src/components/common/AppDatePicker.vue`
- `src/services/filterService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

**目标**: ≥ 80%

## 5. 边界场景

- 大量筛选字段(>10)
- 字段类型多样性
- 折叠/展开动画

## 6. 易错点

- ⚠️ **空值**: null vs undefined vs ""
- ⚠️ **类型分发**: 各种字段类型正确渲染

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
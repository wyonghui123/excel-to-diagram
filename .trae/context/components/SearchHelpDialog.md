# SearchHelpDialog Component Context

> **目标文件**: `src/components/common/SearchHelpDialog.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

搜索帮助对话框。F4 帮助弹窗,基于指定对象类型显示候选列表,支持搜索与过滤。

**架构位置**: ValueHelpField 的底层实现

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | Boolean | `false` | 显隐 |
| `objectType` | String | `''` | 对象类型 |
| `multiple` | Boolean | `false` | 多选 |
| `filters` | Object | `{}` | 预过滤条件 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 显隐 |
| `confirm` | `{items}` | 确认选择 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 自定义内容 |
| `filter` | 自定义过滤 |
| `item` | 自定义列表项 |

## 3. 调用方(依赖)

- `src/components/common/AppModal.vue`
- `src/components/common/MetaTable.vue`
- `src/components/common/FilterBar.vue`
- `src/services/metaService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 ValueHelpField 验证 |

**目标**: ≥ 70%

## 5. 边界场景

- 大量候选(>1000)
- 远程搜索防抖
- 多选上限

## 6. 易错点

- ⚠️ **取消**: 必须可清空已选
- ⚠️ **预过滤**: 过滤条件影响结果

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
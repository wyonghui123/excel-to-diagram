# MetaListPage Component Context

> **目标文件**: `src/components/common/MetaListPage/MetaListPage.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

元数据列表页。组合 FilterBar + MetaTable + 分页 的标准列表页。

**架构位置**: 标准列表页模板

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `objectType` | String | `''` | 对象类型 |
| `defaultFilter` | Object | `{}` | 默认筛选 |
| `enableVariant` | Boolean | `true` | 启用筛选变体 |
| `enableInlineEdit` | Boolean | `false` | 启用内联编辑 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `row-click` | `{row}` | 行点击 |
| `selection-change` | `{rows}` | 选择变化 |

### Slot
| Name | Description |
|------|-------------|
| `toolbar-left` | 工具栏左侧 |
| `toolbar-right` | 工具栏右侧 |
| `cell-<key>` | 自定义单元格 |

## 3. 调用方(依赖)

- `src/components/common/FilterBar/`
- `src/components/common/MetaTable.vue`
- `src/components/common/FilterVariantSelector.vue`
- `src/components/common/MetaListPage/InlineEditCell.vue`
- `src/services/filterVariantService.js`
- `src/services/metaService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 空数据
- 大量数据
- 多个变体切换
- 内联编辑冲突

## 6. 易错点

- ⚠️ **变体切换**: 必须保留原数据状态
- ⚠️ **URL 同步**: 筛选条件应可分享

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
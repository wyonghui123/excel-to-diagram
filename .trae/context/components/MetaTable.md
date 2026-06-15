# MetaTable Component Context

> **目标文件**: `src/components/common/MetaTable.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

元数据表格。通用表格组件,支持列定义、排序、筛选、分页、内联编辑。

**架构位置**: 通用数据展示组件,被 MetaListPage 等使用

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `columns` | Column[] | `[]` | 列定义 |
| `data` | Any[] | `[]` | 数据 |
| `loading` | Boolean | `false` | 加载状态 |
| `pagination` | Object | `null` | 分页配置 |
| `selectable` | Boolean | `false` | 是否可选 |
| `editable` | Boolean | `false` | 是否可内联编辑 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `row-click` | `{row, index}` | 行点击 |
| `sort-change` | `{column, order}` | 排序变化 |
| `selection-change` | `{rows}` | 选择变化 |
| `cell-edit` | `{row, column, value}` | 单元格编辑 |

### Slot
| Name | Description |
|------|-------------|
| `cell-<columnKey>` | 自定义单元格 |
| `toolbar` | 工具栏 |
| `empty` | 空状态 |

## 3. 调用方(依赖)

- `src/services/metaService.js`
- `src/services/columnOrderService.js`
- `src/components/common/MetaListPage/`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

**目标**: ≥ 80%

## 5. 边界场景

- 空数据
- 大量数据(>1000 行)虚拟滚动
- 多列排序
- 跨页选择

## 6. 易错点

- ⚠️ **列宽**: 应可拖拽调整
- ⚠️ **列顺序**: 必须支持 columnOrderService
- ⚠️ **性能**: 大数据必须虚拟滚动

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
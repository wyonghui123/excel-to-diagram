# ExportDialog Component Context

> **目标文件**: `src/components/common/ExportDialog/ExportDialog.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

导出对话框。配置导出参数(格式、字段过滤、目标),生成可下载文件。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | Boolean | `false` | 显隐 |
| `objectType` | String | `''` | 对象类型 |
| `defaultFilters` | Object | `{}` | 默认过滤 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 显隐 |
| `export` | `{format, options}` | 导出 |

### Slot
| Name | Description |
|------|-------------|
| `field` | 自定义字段选择 |

## 3. 调用方(依赖)

- `src/services/archDataConverter.js`
- `src/services/metaService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 大量数据导出(分批)
- 多种格式(xlsx/csv/json)

## 6. 易错点

- ⚠️ **异步**: 大数据导出必须异步
- ⚠️ **下载**: 必须触发浏览器下载

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
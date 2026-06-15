# DataPreview Component Context

> **目标文件**: `src/components/DataPreview.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

数据预览。在导入前预览数据(Excel/CSV/JSON),支持字段映射。

**架构位置**: 数据导入流程

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `data` | Sheet\|Object | `null` | 预览数据 |
| `targetObjectType` | String | `''` | 目标对象类型 |
| `showMapping` | Boolean | `true` | 显示字段映射 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `confirm` | `{mapping}` | 确认导入 |
| `cancel` | - | 取消 |

### Slot
| Name | Description |
|------|-------------|
| `cell-<key>` | 自定义单元格 |

## 3. 调用方(依赖)

- `src/components/common/MetaTable.vue`
- `src/components/common/ImportDialog/`
- `src/services/excelParser.js`
- `src/services/objectTypeService.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 ImportDialog 验证 |

## 5. 边界场景

- 大文件预览(>10000 行,显示前 N 行)
- 字段类型推断错误
- 必填字段缺失

## 6. 易错点

- ⚠️ **性能**: 不全加载,只预览前 N 行
- ⚠️ **类型转换**: 失败要明确提示
- ⚠️ **必填校验**: 导入前必须提示

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
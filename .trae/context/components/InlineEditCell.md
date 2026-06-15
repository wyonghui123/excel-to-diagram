# InlineEditCell Component Context

> **目标文件**: `src/components/common/MetaListPage/InlineEditCell.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

表格内联编辑单元格。点击单元格进入编辑态,失焦自动保存。

**架构位置**: MetaListPage 内联编辑模式

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `value` | Any | `null` | 值 |
| `type` | String | `'text'` | text / number / select / date |
| `options` | Option[] | `[]` | 选项(枚举/选择) |
| `readonly` | Boolean | `false` | 只读 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `change` | `{value}` | 值变化 |
| `save` | `{value}` | 保存 |

## 3. 调用方

- `src/components/common/MetaListPage/MetaListPage.vue`
- `src/components/common/MetaTable.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 快速连续编辑
- 编辑中切换行
- 校验失败回退

## 6. 易错点

- ⚠️ **乐观更新**: 立即更新 UI,失败回滚
- ⚠️ **防抖保存**: 避免频繁请求

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
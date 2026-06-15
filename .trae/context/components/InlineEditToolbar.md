# InlineEditToolbar Component Context

> **目标文件**: `src/components/common/MetaListPage/InlineEditToolbar.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

内联编辑工具栏。提供"全部保存"、"撤销"、"重做"等批量操作。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `dirtyCount` | Number | `0` | 待保存条数 |
| `canUndo` | Boolean | `false` | 可撤销 |
| `canRedo` | Boolean | `false` | 可重做 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `save-all` | - | 全部保存 |
| `undo` | - | 撤销 |
| `redo` | - | 重做 |
| `cancel` | - | 取消所有编辑 |

## 3. 调用方

- `src/components/common/MetaListPage/MetaListPage.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 大量待保存(>100)
- 部分保存失败

## 6. 易错点

- ⚠️ **保存策略**: 全部成功才提交
- ⚠️ **取消确认**: 提示用户

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
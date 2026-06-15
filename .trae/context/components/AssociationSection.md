# AssociationSection Component Context

> **目标文件**: `src/components/common/ObjectPage/AssociationSection.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

关联项区域。在 ObjectPage 中展示对象的所有关联(出向 + 入向)。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `objectId` | String | `''` | 当前对象 ID |
| `associations` | Assoc[] | `[]` | 关联定义 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `add` | - | 添加关联 |
| `remove` | `{assocId}` | 删除关联 |

### Slot
| Name | Description |
|------|-------------|
| `item` | 自定义关联项 |

## 3. 调用方(依赖)

- `src/services/associationService.js`
- `src/components/bo/AssociationCell.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 大量关联(>100)
- 双向关联展示
- 关联权限

## 6. 易错点

- ⚠️ **循环检测**: 防止 A→B→A
- ⚠️ **删除确认**: 必须二次确认

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
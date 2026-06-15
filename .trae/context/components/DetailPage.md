# DetailPage Component Context

> **目标文件**: `src/components/common/DetailPage/DetailPage.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

详情页标准组件。展示对象的只读详情,支持自定义 Section。

**架构位置**: 与 ObjectPage 区别:DetailPage 强调"查看",ObjectPage 强调"编辑"

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `objectId` | String | `''` | 对象 ID |
| `objectType` | String | `''` | 对象类型 |
| `sections` | Section[] | `[]` | 自定义分区 |

### Slot
| Name | Description |
|------|-------------|
| `section-<key>` | 自定义分区 |
| `field-<key>` | 自定义字段 |

## 3. 调用方(依赖)

- `src/services/metaService.js`
- `src/components/common/DetailPage/DetailSection.vue`
- `src/components/common/DetailPage/AssociationSection.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 自定义 Section 渲染
- 大量字段分页

## 6. 易错点

- ⚠️ **只读**: 不暴露编辑入口

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
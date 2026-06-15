# DetailSection Component Context

> **目标文件**: `src/components/common/DetailPage/DetailSection.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

详情页分区。展示一组相关字段。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `title` | String | `''` | 分区标题 |
| `data` | Object | `{}` | 数据 |
| `fields` | Field[] | `[]` | 字段定义 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 自定义内容 |
| `field-<key>` | 自定义字段 |

## 3. 调用方

- `src/components/common/DetailPage/DetailPage.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 空字段
- 字段类型分发

## 6. 易错点

- ⚠️ **值格式化**: 日期/枚举需展示态格式化

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
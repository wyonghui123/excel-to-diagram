# FieldGroupSection Component Context

> **目标文件**: `src/components/common/ObjectPage/FieldGroupSection.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

字段分组区域。将相关字段归类展示(如"基本信息"、"扩展信息")。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `title` | String | `''` | 分组标题 |
| `fields` | Field[] | `[]` | 字段定义 |
| `data` | Object | `{}` | 数据 |
| `collapsible` | Boolean | `true` | 可折叠 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `change` | `{key, value}` | 字段变化 |

### Slot
| Name | Description |
|------|-------------|
| `field-<key>` | 自定义字段 |
| `extra` | 分组额外内容 |

## 3. 调用方(依赖)

- `src/components/common/AppCollapse.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 空分组
- 大量字段(>20)

## 6. 易错点

- ⚠️ **分组顺序**: 按业务重要性

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
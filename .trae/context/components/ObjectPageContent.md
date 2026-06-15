# ObjectPageContent Component Context

> **目标文件**: `src/components/common/ObjectPage/ObjectPageContent.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

ObjectPage 内容区。展示字段分组、Tab 容器、关联项。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `data` | Object | `{}` | 对象数据 |
| `fields` | Field[] | `[]` | 字段定义 |
| `readonly` | Boolean | `false` | 只读 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `field-change` | `{key, value}` | 字段变化 |

### Slot
| Name | Description |
|------|-------------|
| `field-<key>` | 自定义字段 |

## 3. 调用方(依赖)

- `src/components/common/FieldGroupSection.vue`
- `src/components/common/MetaForm.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 嵌套字段组
- 隐藏字段
- 只读字段

## 6. 易错点

- ⚠️ **字段依赖**: A 字段变化触发 B 字段显示/隐藏

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
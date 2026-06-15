# RelationScopeTree Component Context

> **目标文件**: `src/components/common/RelationScopeTree/RelationScopeTree.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

关系域树。展示"关系范围"层级结构,支持多维分类(对象类型 + 关系类型)。

**架构位置**: 高级筛选核心组件

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `scopes` | Scope[] | `[]` | 关系范围 |
| `selected` | String[] | `[]` | 选中项 |
| `multiple` | Boolean | `true` | 多选 |
| `lazy` | Boolean | `true` | 懒加载 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:selected` | `{value}` | 选中变化 |
| `change` | `{value}` | 同上 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 自定义节点 |

## 3. 调用方(依赖)

- `src/services/hierarchyService.js`
- `src/services/associationService.js`
- `src/components/common/RelationScopeTree/*`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

**目标**: ≥ 70%

## 5. 边界场景

- 大树(>1000 节点)懒加载
- 多维过滤
- 树搜索

## 6. 易错点

- ⚠️ **懒加载**: 子节点必须按需加载
- ⚠️ **半选状态**: 父子联动

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
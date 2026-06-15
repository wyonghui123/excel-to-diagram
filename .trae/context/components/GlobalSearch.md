# GlobalSearch Component Context

> **目标文件**: `src/components/common/GlobalSearch/GlobalSearch.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

全局搜索。跨对象类型的统一搜索入口(类似 Cmd+K)。

**架构位置**: AppHeader 内的核心组件

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `shortcut` | String | `'Cmd+K'` | 快捷键 |
| `scope` | String[] | `[]` | 搜索范围(对象类型) |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `select` | `{item}` | 选择结果 |
| `search` | `{query}` | 搜索 |

### Slot
| Name | Description |
|------|-------------|
| `item` | 自定义结果项 |
| `empty` | 空结果 |

## 3. 调用方(依赖)

- `src/services/metaService.js`
- `src/services/searchService.js`(可能)

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

**目标**: ≥ 70%

## 5. 边界场景

- 无结果
- 大量结果(>100)
- 快捷键冲突

## 6. 易错点

- ⚠️ **快捷键**: 必须全局 Cmd/Ctrl+K
- ⚠️ **防抖**: 搜索必须防抖(300ms)
- ⚠️ **权限**: 结果需按权限过滤

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
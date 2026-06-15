# GlobalToolbar Component Context

> **目标文件**: `src/components/common/GlobalToolbar/GlobalToolbar.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P2
> **YonDesign**: [OK]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

全局工具栏。提供跨页面通用操作(新建、导入、导出等)。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `actions` | Action[] | `[]` | 操作定义 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `action` | `{action}` | 触发操作 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 自定义操作 |

## 3. 调用方

- `src/components/common/MetaListPage/`
- `src/components/common/AppHeader.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 操作按钮过多(>5)
- 操作权限

## 6. 易错点

- ⚠️ **权限**: 必须按用户权限过滤操作

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
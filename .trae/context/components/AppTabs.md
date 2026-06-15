# AppTabs Component Context

> **目标文件**: `src/components/common/AppTabs/AppTabs.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ✅ 100% (42 tests)

## 1. 职责 (What)

通用 Tabs。基于 Element Plus `<el-tabs>` 封装,支持多种 Tab 样式与拖拽。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `modelValue` | String | `''` | 当前激活 key |
| `tabs` | Tab[] | `[]` | Tab 定义 |
| `type` | String | `'card'` | card / border-card |
| `closable` | Boolean | `false` | 可关闭 |
| `draggable` | Boolean | `false` | 可拖拽 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `update:modelValue` | `{value}` | 激活变化 |
| `close` | `{key}` | 关闭 Tab |
| `tab-drop` | `{from, to}` | 拖拽结束 |

### Slot
| Name | Description |
|------|-------------|
| `<key>` | 每个 Tab 内容 |
| `default` | 自定义 |

## 3. 调用方

- `src/components/common/ObjectPage/`
- `src/components/common/AppShell.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ✅ 100% (42 tests) |
| E2E | [OK] 间接验证 |

**目标**: ≥ 90%(基础组件) ✅ 已达成

## 5. 边界场景

- 大量 Tab(>10)
- 拖拽顺序持久化
- 关闭最后一个

## 6. 易错点

- ⚠️ **持久化**: Tab 顺序可入 store

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
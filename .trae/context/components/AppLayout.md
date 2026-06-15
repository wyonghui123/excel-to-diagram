# AppLayout Component Context

> **目标文件**: `src/components/common/AppLayout/AppLayout.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [OK]
> **测试覆盖**: ✅ 100% (23 tests)

## 1. 职责 (What)

应用 Layout。提供 YonDesign 标准页面布局(顶栏 + 内容区 + 可选侧栏)。

**架构位置**: YonDesign 体系 Layout 组件,被 AADiagramApp、ConfigApp 包裹

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `mode` | String | `'standard'` | standard / fullscreen / minimal |
| `showSidebar` | Boolean | `true` | 是否显示侧栏 |

### Slot
| Name | Description |
|------|-------------|
| `topbar` | 顶栏 |
| `sidebar` | 侧栏 |
| `default` | 内容 |

## 3. 调用方(依赖)

- `src/components/common/AppShell.vue`
- `src/components/common/AppHeader.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ✅ 100% (23 tests) |
| E2E | [OK] 间接验证 |

**目标**: ≥ 90%(基础组件) ✅ 已达成

## 5. 边界场景

- 全屏模式
- 内容溢出滚动

## 6. 易错点

- ⚠️ **mode 切换**: 状态必须保留

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
# AppShell Component Context

> **目标文件**: `src/components/common/AppShell/AppShell.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [OK]
> **测试覆盖**: ✅ 100% (17 tests)

## 1. 职责 (What)

应用 Shell。提供统一的"顶栏+侧栏+内容"布局框架。

**架构位置**: YonDesign 体系 Layout 组件

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `headerHeight` | String | `'56px'` | 顶栏高度 |
| `sidebarWidth` | String | `'220px'` | 侧栏宽度 |
| `collapsed` | Boolean | `false` | 侧栏是否折叠 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `toggle-sidebar` | - | 侧栏折叠切换 |

### Slot
| Name | Description |
|------|-------------|
| `header` | 顶栏内容 |
| `sidebar` | 侧栏内容 |
| `default` | 主内容 |

## 3. 调用方(依赖)

- `src/components/common/AppHeader.vue`
- `src/components/common/AppSideNav.vue`
- `src/stores/user.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ✅ 100% (17 tests) |
| E2E | [OK] 间接验证 |

**目标**: ≥ 80% ✅ 已达成

## 5. 边界场景

- 超长内容溢出
- 极窄屏幕(<768px)
- 侧栏折叠动画

## 6. 易错点

- ⚠️ **响应式**: 必须支持移动端
- ⚠️ **状态同步**: 折叠状态建议存 store

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
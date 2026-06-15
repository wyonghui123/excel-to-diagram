# ObjectPageShell Component Context

> **目标文件**: `src/components/common/ObjectPage/ObjectPageShell.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

ObjectPage 的 Shell 容器。提供 Tab 容器、分区布局、加载状态。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `tabs` | Tab[] | `[]` | Tab 配置 |
| `loading` | Boolean | `false` | 加载中 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `tab-change` | `{key}` | Tab 切换 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 主内容 |
| `tab-<key>` | 每个 Tab |

## 3. 调用方(依赖)

- `src/components/common/AppTabs.vue`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 单 Tab 隐藏 Tab bar
- 大量 Tab 横向滚动

## 6. 易错点

- ⚠️ **URL 同步**: Tab 状态应同步 URL

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
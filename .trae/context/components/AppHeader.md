# AppHeader Component Context

> **目标文件**: `src/components/common/AppHeader.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

应用顶栏。Logo、面包屑、全局搜索、用户菜单、通知。

**架构位置**: YonDesign 标准顶栏

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `title` | String | `''` | 应用名 |
| `showBreadcrumb` | Boolean | `true` | 显示面包屑 |
| `showGlobalSearch` | Boolean | `true` | 全局搜索 |

### Slot
| Name | Description |
|------|-------------|
| `left` | 左侧 Logo 区 |
| `center` | 中间内容 |
| `right` | 右侧操作区 |

## 3. 调用方(依赖)

- `src/components/common/UserMenu/`
- `src/components/common/GlobalSearch/`
- `src/components/common/BreadcrumbNav/`
- `src/stores/user.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 无用户状态
- 大量通知
- 移动端

## 6. 易错点

- ⚠️ **响应式**: 移动端折叠
- ⚠️ **权限**: 操作按钮按权限显示

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
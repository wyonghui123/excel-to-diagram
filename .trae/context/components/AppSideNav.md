# AppSideNav Component Context

> **目标文件**: `src/components/common/AppSideNav/AppSideNav.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ✅ 100% (21 tests)

## 1. 职责 (What)

应用侧栏导航。基于 Element Plus `<el-menu>` 封装。

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `items` | NavItem[] | `[]` | 导航项 |
| `collapse` | Boolean | `false` | 折叠 |
| `defaultActive` | String | `''` | 默认选中 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `select` | `{index, indexPath}` | 选中 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 自定义菜单项 |

## 3. 调用方(依赖)

- Element Plus `<el-menu>`
- `src/router/index.ts`
- `src/services/permissionService.js`(权限过滤)

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ✅ 100% (21 tests) |
| E2E | [OK] 间接验证 |

**目标**: ≥ 90%(基础组件) ✅ 已达成

## 5. 边界场景

- 深层嵌套
- 多级折叠
- 移动端(转为抽屉)

## 6. 易错点

- ⚠️ **权限过滤**: 必须按用户权限过滤菜单
- ⚠️ **active state**: 与路由同步

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
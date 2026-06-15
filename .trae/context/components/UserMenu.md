# UserMenu Component Context

> **目标文件**: `src/components/common/UserMenu/UserMenu.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P1
> **YonDesign**: [OK]
> **测试覆盖**: ⚠️ 0%

## 1. 职责 (What)

用户菜单。展示当前用户头像、姓名、登出、设置入口。

**架构位置**: AppHeader 右上角

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `user` | User | `null` | 当前用户 |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `logout` | - | 登出 |
| `settings` | - | 设置 |

### Slot
| Name | Description |
|------|-------------|
| `default` | 自定义菜单项 |

## 3. 调用方(依赖)

- `src/services/authService.js`
- `src/stores/user.js`

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |

## 5. 边界场景

- 无头像
- 未登录状态
- 移动端折叠

## 6. 易错点

- ⚠️ **登出确认**: 可选
- ⚠️ **权限**: 菜单项按权限显示

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
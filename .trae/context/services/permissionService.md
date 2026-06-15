# permissionService Context

> **目标文件**: `src/services/permissionService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **测试覆盖**: ⚠️ 0%
> **Healer**: **deny**(鉴权敏感模块)

## 1. 职责 (What)

权限规则查询与角色校验。基于 RBAC 模型,管理"角色-权限"映射。

**架构位置**: 中间 service,被 store、组件、路由守卫调用

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `getPermissionRules` | `() => Promise<Rule[]>` | 查询所有权限规则 |
| `getRulesByRole` | `(roleId) => Promise<Rule[]>` | 按角色查询权限 |
| `checkPermission` | `(permissionCode) => boolean` | 前端本地校验 |
| `hasRole` | `(roleId) => boolean` | 检查是否拥有某角色 |

## 3. 调用方

预期调用方:
- `src/stores/permission.js`
- `src/router/`(beforeEach 守卫)
- `src/components/common/`(条件渲染)
- `src/components/bo/ActionExecutor.vue`(操作前置校验)

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 间接验证 |
| 覆盖率 | 0% |

## 5. 边界场景

- 角色未配置权限
- 用户多角色(取并集)
- 权限规则缓存失效
- 越权访问前端绕过

## 6. 易错点

- ⚠️ **前端校验仅辅助**: 后端必须独立校验,前端不可信
- ⚠️ **角色变更实时性**: 切换角色后必须刷新缓存
- ⚠️ **通配权限**: `*` 权限需特殊处理

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 Context | AI |
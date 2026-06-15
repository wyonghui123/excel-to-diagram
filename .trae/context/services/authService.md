# authService Context

> **目标文件**: `src/services/authService.js`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **测试覆盖**: ⚠️ 0%
> **Healer**: **deny**(鉴权敏感模块)

## 1. 职责 (What)

用户身份认证与会话管理。包括登录、登出、token 刷新、当前用户信息查询。

**架构位置**: 中间 service,被 `LoginPage.vue`、`AppHeader.vue`、`Permission` 等模块调用

## 2. 关键函数

| 函数 | 签名 | 用途 |
|------|------|------|
| `login` | `(username, password) => Promise<Session>` | 用户登录 |
| `logout` | `() => Promise<void>` | 用户登出 |
| `getCurrentUser` | `() => Promise<User>` | 获取当前登录用户 |
| `refreshToken` | `() => Promise<string>` | 刷新 access token |
| `changePassword` | `(oldPwd, newPwd) => Promise<void>` | 修改密码 |

## 3. 调用方

实施时通过源码扫描补充:

```bash
grep -r "from.*authService" src/ --include="*.js" --include="*.vue" -l
```

预期调用方:
- `src/components/LoginPage.vue`
- `src/components/ChangePasswordDialog.vue`
- `src/components/common/AppHeader.vue` / `UserMenu`
- `src/router/`(路由守卫)
- `src/utils/api.js`(注入 Authorization header)

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 LoginPage 间接验证 |
| 覆盖率 | 0% |

**目标**: ≥ 80%,鉴权核心函数 100%

## 5. 边界场景

- 空用户名/密码
- 错误密码(连续失败锁定)
- Token 过期(401 自动刷新)
- 多端登录(踢出旧 session)
- 并发登录请求(去重)

## 6. 易错点

- [OK] **必须走 httpClient**: 禁止直接 fetch
- [X] **禁止在 store 中存储密码明文**
- [X] **禁止日志输出 token/密码**
- ⚠️ **401 处理**: 必须调用 `onUnauthorized` 回调,触发全局登出
- ⚠️ **CSRF**: 必须使用 cookie 鉴权,后端 CORS 配置

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 Context | AI |

---

## 相关链接

- [源文件](file:///d:/filework/excel-to-diagram/src/services/authService.js)
- [permissionService](./permissionService.md)
- [httpClient Context](../utilities/httpClient.md)
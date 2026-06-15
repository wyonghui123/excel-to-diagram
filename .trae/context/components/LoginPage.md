# LoginPage Component Context

> **目标文件**: `src/components/LoginPage.vue`
> **版本**: 0.1.0 (2026-06-13)
> **优先级**: P0
> **YonDesign**: [X]
> **测试覆盖**: ⚠️ 0%
> **Healer**: **deny**(鉴权页)

## 1. 职责 (What)

登录页。用户输入凭证、调用 authService 登录。

**架构位置**: 路由 `/login`

## 2. Props/Emit/Slot

### Props
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `redirect` | String | `'/'` | 登录后跳转 URL |

### Emit
| Event | Payload | Description |
|-------|---------|-------------|
| `login-success` | `{user}` | 登录成功 |

### Slot
无

## 3. 调用方(依赖)

- `src/services/authService.js`
- `src/router/index.ts`(跳转)

## 4. 测试覆盖现状

| 维度 | 现状 |
|------|------|
| 单元测试 | ⚠️ 0% |
| E2E | [OK] 通过 auth flow 验证 |

## 5. 边界场景

- 登录失败提示
- 账号锁定
- 验证码
- 记住密码
- 自动登录

## 6. 易错点

- ⚠️ **密码安全**: 不入 store、不入日志
- ⚠️ **CSRF**: 必须走 cookie 鉴权
- ⚠️ **错误信息**: 区分用户不存在 vs 密码错误

## 7. 变更历史

| 版本 | 日期 | 变更 | Author |
|------|------|------|--------|
| 0.1.0 | 2026-06-13 | 初版 | AI |
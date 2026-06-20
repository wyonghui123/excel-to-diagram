---
alwaysApply: false
description: "前端测试认证规范：httpOnly cookie、dev-login、Session 管理"
globs: "meta/tests/**/*,tests/e2e/**/*"
---

# 前端测试认证规范（单一事实源）

> [!!!] 本文件是前端测试认证的唯一规范来源
> [!!!] 任何智能体编写前端自动化测试（Playwright / MCP / 其他）时必须遵守
> 最后更新: 2026-06-02

---

## 〇、可测试性铁律（Testability Iron Rules）

> **DOM 存在 ≠ 视觉可见**
>
> 任何前端 UI 测试，必须用 `assert_visible` 做 5 步视觉验证，不能只看 DOM 存在。
> 详见 [可测试性铁律完整文档](../../../docs/lessons-learned/testing/testability-iron-rules.md)

### 5 步视觉验证（缺一不可）

| # | 检查项 | 检查方法 | 失败表现 |
|---|--------|---------|---------|
| 1 | `exists` | `querySelector` 找到 | DOM 里没创建 |
| 2 | `sized` | `rect.width > 0 && rect.height > 0` | 0x0 隐藏元素 |
| 3 | `notHidden` | `display/visibility/opacity` 都不是隐藏 | CSS display:none |
| 4 | `inViewport` | rect 在 viewport 内 | 弹窗在屏幕外 |
| 5 | `notObscured` | `elementFromPoint(centerX, centerY)` 是元素自己或后代 | 被 modal 盖住 |

### 标准用法

```python
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True)
result = cli.assert_visible('.el-select-dropdown', screenshot_path='d:/fail.png')
assert result['ok'], f"下拉框视觉不可见: {result['reason']}"
```

**任何 UI 验证断言前必须配 `screenshot_path` 失败截图。**

---

## 一、核心问题

本项目的认证架构决定了直接 `page.goto(受保护页面)` 不可行：

```
认证链: httpOnly Cookie (auth_token) → restoreSession() → Pinia Store → Vue Router Guard

问题: SPA 每次 page.goto() 都是整页刷新 → restoreSession() 异步不等待 → 路由守卫先执行
     → isLoggedIn=false → 重定向 /?reason=not_logged_in
```

**结论：禁止在测试中通过 UI 表单登录（填用户名→点按钮→等跳转），效率低且不稳定。**

---

## 二、解决方案：后端 dev-login 端点

### 2.1 原理

```
Step 1: GET /api/v1/auth/dev-login?username=admin
         → 后端查询用户 → 生成 JWT → Set-Cookie: auth_token (httpOnly)
         → 浏览器存储 cookie（与正常登录完全一致）

Step 2: page.goto(首页) → SPA 初始化 → restoreSession() → GET /api/v1/auth/me (自动带cookie)
         → 认证成功 → Pinia store populated → isLoggedIn=true

Step 3: router.push(目标页面) → SPA 内部导航 → 复用已有 store → 零竞态
```

### 2.2 为什么不用其他方案

| 方案 | 问题 |
|------|------|
| `context.addCookies()` 手动注入 | 需要知道 JWT secret，仍需要处理竞态 |
| `page.route()` mock API | 需要 mock 所有受保护 API，太重 |
| `localStorage` 注入 token | 本项目用 httpOnly cookie，JS 无法读写 |
| 前端 test mode 绕过 | 改动大，安全风险 |
| UI 表单登录 | 慢、不稳定、登录页 UI 变化会破坏测试 |

### 2.3 端点详情

```
GET /api/v1/auth/dev-login?username=<用户名>

- 仅开发环境可用（FLASK_ENV != 'production'）
- 无需密码，按用户名查库生成合法 JWT
- Set-Cookie: auth_token (httpOnly, SameSite=Lax, 7天)
- 返回: { success: true, data: { user: {...} } }
```

代码位置：[auth_api.py:L167-L218](file:///d:/filework/excel-to-diagram/meta/api/auth_api.py#L167-L218)

---

## 三、Python Helper 模块（推荐方式）

### 3.1 文件位置

`test_helpers/browser_auth.py`

### 3.2 API 速查

| 函数 | 类型 | 说明 |
|------|------|------|
| `authenticated_page(username, target_url, headless)` | 异步上下文管理器 | **推荐。** yield 已认证 page，自动管理 browser 生命周期 |
| `get_authenticated_page(browser, username)` | 异步函数 | 用已有 browser 创建已认证 page |
| `go_to(page, path)` | 异步函数 | SPA 内部导航到受保护页面 |

### 3.3 使用方式

**方式 A：一步到位（最推荐）**

```python
from test_helpers.browser_auth import authenticated_page

async with authenticated_page(target_url='/system/archdata') as page:
    # 已在目标页面，已认证，直接测试！
    await page.wait_for_load_state('networkidle')
    await page.screenshot(path='result.png')
```

**方式 B：两步（灵活切换页面）**

```python
from test_helpers.browser_auth import authenticated_page, go_to

async with authenticated_page() as page:
    await go_to(page, '/system/archdata')
    # 测试页面 A...
    await page.screenshot(path='page_a.png')

    await go_to(page, '/user-permission?tab=users')
    # 测试页面 B...（同一 session，无需重新认证）
    await page.screenshot(path='page_b.png')
```

**方式 C：自管 browser 生命周期**

```python
from test_helpers.browser_auth import get_authenticated_page, go_to
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.launch(headless=False)
    page = await get_authenticated_page(browser, username='admin')
    await go_to(page, '/system/archdata')
    # ... 测试 ...
    await browser.close()
```

### 3.4 完整 API

```python
@asynccontextmanager
async def authenticated_page(
    username: str = 'admin',         # 登录用户名
    target_url: Optional[str] = None, # 认证后导航到的目标页面（可选）
    base_url: str = 'http://localhost:3004',
    headless: bool = False,           # 是否无头模式
    viewport: dict = None,            # 默认 1920x1080
    timeout: int = 15000,             # 等待超时 ms
) -> Page: ...

async def get_authenticated_page(
    browser: Browser,                # 已有 browser 实例
    username: str = 'admin',
    base_url: str = 'http://localhost:3004',
    timeout: int = 15000,
) -> Page: ...

async def go_to(
    page: Page,                      # 已认证 page
    path: str,                       # 目标路径，如 '/system/archdata'
): ...
```

---

## 四、MCP DevTools 测试专用流程

MCP 工具（`navigate_page` / `evaluate_script` 等）无法直接调用 Python helper。使用以下流程：

### 4.1 MCP 认证流程（3 步）

```
Step 1: SET COOKIE — 导航到 dev-login 端点设置 cookie
  navigate_page → http://localhost:3010/api/v1/auth/dev-login?username=admin

Step 2: LOAD APP — 导航到前端首页，等待 SPA 初始化
  navigate_page → http://localhost:3004/
  evaluate_script → 等待 store 就绪（见下方模板）

Step 3: NAVIGATE — SPA 内部导航到目标页面
  evaluate_script → router.push('/system/archdata')
```

### 4.2 等待 store 就绪脚本（evaluate_script）

```javascript
() => new Promise((resolve) => {
    const maxWait = 15000, start = Date.now()
    const check = () => {
        const app = document.querySelector('#app')?.__vue_app__
        if (!app) { setTimeout(check, 300); return }
        const pinia = app.config.globalProperties.$pinia
        const store = pinia._s.get('auth')
        if (store && store.sessionReady && store.user) {
            resolve({ ready: true, username: store.user.username, elapsed: Date.now() - start })
        } else if (Date.now() - start > maxWait) {
            resolve({ ready: false, elapsed: Date.now() - start })
        } else {
            setTimeout(check, 300)
        }
    }
    check()
})
```

### 4.3 SPA 内部导航脚本（evaluate_script）

```javascript
(path) => {
    const router = document.querySelector('#app').__vue_app__
        .config.globalProperties.$router
    router.push(path)
}
```

### 4.4 完整 MCP 示例（伪代码）

```
# 1. 设置认证 cookie
mcp: navigate_page → http://localhost:3010/api/v1/auth/dev-login?username=admin

# 2. 加载 SPA，等待就绪
mcp: navigate_page → http://localhost:3004/
mcp: evaluate_script → 等待 store 就绪（4.2 脚本）
# 预期返回: { ready: true, username: 'admin', elapsed: 1234 }

# 3. 导航到目标页面
mcp: evaluate_script → router.push('/system/archdata')  （4.3 脚本）
mcp: wait_for_timeout → 2000

# 4. 开始测试
mcp: take_snapshot → 获取页面结构
mcp: click → 操作页面元素
```

---

## 五、禁止事项（Anti-Patterns）

| # | 禁止 | 后果 | 正确做法 |
|---|------|------|---------|
| 1 | **用 UI 登录**（填表单 + 点按钮） | 慢、不稳定、依赖登录页 UI | 用 dev-login 端点 |
| 2 | **直接 `page.goto(受保护URL)`** | 必然被重定向到 `/` | 先用 dev-login 设置 cookie |
| 3 | **用 `page.addInitScript` 设置 localStorage** | httpOnly cookie 无法被 JS 读写 | 用 dev-login 让后端 Set-Cookie |
| 4 | **等待 `networkidle` 后直接 goto** | `networkidle` 在 SPA 中永不完成 | 用 `domcontentloaded` + store 就绪等待 |
| 5 | **重复调用 dev-login 设置 cookie** | 浪费，cookie 有效期 7 天 | 整个测试 session 只需一次 |
| 6 | **遗忘等待 store 就绪就 router.push** | 路由守卫仍可能未通过 | 必须等 `sessionReady && user` |
| 7 | **页面白屏后盲猜原因或盲等** | 错误被忽略，Agent 进入无限推断循环 | 先 `cli.check_health()`，`PageHealthError` 出现即 Fail-Fast |

---

## 六、设计决策记录

| 决策 | 日期 | 原因 |
|------|------|------|
| 采用后端 dev-login 端点而非 JWT 注入 | 2026-06-01 | 更简单、不依赖 JWT secret、cookie 由后端规范设置 |
| `router.push` 而非 `page.goto` 用于受保护页面导航 | 2026-06-01 | 避免 SPA 整页刷新导致的竞态 |
| `authenticated_page` 使用异步上下文管理器 | 2026-06-01 | 自动管理 browser 生命周期，防止资源泄漏 |
| 等待 `sessionReady && user` 而非仅 `isLoggedIn` | 2026-06-01 | `sessionReady` 标志位确保 `restoreSession()` 已完成 |
| PlaywrightCLI 自动监听 pageerror/console/crash + _guard_health() Fail-Fast | 2026-06-02 | 四层可观测性体系，页面崩溃时立即终止而非盲猜 |

---

## 七、文件索引

| 文件 | 说明 |
|------|------|
| `test_helpers/browser_auth.py` | Python 认证 helper 模块（推荐入口） |
| `test_helpers/verify_auth.py` | 认证方案验证脚本（4 tests） |
| `meta/api/auth_api.py#L167-L218` | dev-login 端点实现 |
| `.trae/rules/mcp-testing.md` | MCP DevTools 测试规则 |
| `.trae/rules/e2e-testing.md` | Playwright E2E 测试规则 |

---

## 八、Python API 测试登录参考（常见踩坑）

当编写 Python 脚本通过 `requests` 库调用后端 API 时，登录是一个高频踩坑点。
以下是**唯一正确**的调用方式：

### 8.1 确定性 API 契约

```
方法:   GET（不是 POST！）
路径:   /api/v1/auth/dev-login（只在 v1，v2 不存在！）
参数:   ?username=admin（URL query 参数，不是 JSON body！）
返回:   200 + Set-Cookie: auth_token=<jwt>; HttpOnly（cookie 在 response header，不是 body！）
```

### 8.2 正确示例（Python requests）

```python
import requests

session = requests.Session()
# [OK] 唯一正确调用
resp = session.get('http://localhost:3010/api/v1/auth/dev-login?username=admin')
assert resp.status_code == 200, f'Login failed: {resp.status_code}'
# 之后所有请求自动带 cookie
data = session.get('http://localhost:3010/api/v2/bo/role').json()
```

### 8.3 常见错误速查

| 错误尝试 | 状态码 | 原因 |
|---------|--------|------|
| `POST /api/v2/auth/dev-login` | 404/500 | v2 不存在此路由 |
| `POST /api/v1/auth/dev-login` | 405 | 只支持 GET |
| `GET /api/v1/auth/dev-login` 不带 username | 400 | 缺少必填参数 |
| 用 `requests.get(...).json()['token']` 取 token | — | cookie 在 response header，不在 body |
| `GET /api/v2/bo/role` 不带 cookie | 401 | 需先 dev-login 建立 session |

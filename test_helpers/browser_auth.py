"""
前端测试自动化 - 一行认证模块

解决问题：智能体测试前端功能时，不再需要手动登录（填表单→点按钮→等跳转）。
通过后端 dev-login 端点设置 httpOnly cookie，一行代码完成认证。

核心原理：
  1. 后端 GET /api/v1/auth/dev-login?username=admin → Set-Cookie: auth_token (httpOnly)
  2. 浏览器自动存储 cookie
  3. 导航到前端首页 → Vue 初始化 → restoreSession() → GET /api/v1/auth/me → 认证成功
  4. 使用 router.push 进行 SPA 内部导航（避免 page.goto 全页刷新导致竞态）

使用示例：

    from test_helpers.browser_auth import authenticated_page, go_to

    async with authenticated_page() as page:
        await go_to(page, '/system/archdata')
        await page.wait_for_load_state('networkidle')
        await page.screenshot(path='test_result.png')

    # 或者一步到位：
    from test_helpers.browser_auth import authenticated_page

    async with authenticated_page(target_url='/system/archdata') as page:
        # 已经在目标页面，直接测试！
        await page.screenshot(path='test_result.png')
"""

from contextlib import asynccontextmanager
from typing import Optional
from urllib.parse import urlparse

from playwright.async_api import async_playwright, Page, Browser

BASE_URL = 'http://localhost:3004'
API_URL = 'http://localhost:3010'
DEV_LOGIN_URL = f'{API_URL}/api/v1/auth/dev-login'

_STORE_READY_SCRIPT = """
() => {
    const app = document.querySelector('#app')?.__vue_app__;
    if (!app) return false;
    const pinia = app.config.globalProperties.$pinia;
    const store = pinia._s.get('auth');
    return store && store.sessionReady && store.user != null;
}
"""

_ROUTER_PUSH_SCRIPT = """
(path) => {
    const router = document.querySelector('#app').__vue_app__
        .config.globalProperties.$router;
    router.push(path);
}
"""


@asynccontextmanager
async def authenticated_page(
    username: str = 'admin',
    target_url: Optional[str] = None,
    base_url: str = BASE_URL,
    headless: bool = False,
    viewport: dict = None,
    timeout: int = 60000,
):
    """
    异步上下文管理器，yield 一个已认证的 Playwright Page。

    Args:
        username: 登录用户名（默认 admin）
        target_url: 可选，认证后自动导航到的目标页面
        base_url: 前端地址
        headless: 是否无头模式（默认 False，方便调试）
        viewport: 视口大小，默认 {'width': 1920, 'height': 1080}
        timeout: 等待超时 ms

    Yields:
        Playwright Page (已认证，已加载首页)

    Example:
        async with authenticated_page(target_url='/system/archdata') as page:
            await page.screenshot(path='result.png')
    """
    if viewport is None:
        viewport = {'width': 1920, 'height': 1080}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        context = await browser.new_context(viewport=viewport)
        page = await context.new_page()

        await page.goto(f'{DEV_LOGIN_URL}?username={username}')
        await page.goto(base_url, wait_until='domcontentloaded', timeout=timeout)

        await page.wait_for_function(_STORE_READY_SCRIPT, timeout=timeout)

        if target_url:
            target_path = urlparse(target_url).path
            if urlparse(target_url).query:
                target_path += '?' + urlparse(target_url).query
            await page.evaluate(_ROUTER_PUSH_SCRIPT, target_path)
            await page.wait_for_timeout(2000)

        yield page
        await browser.close()


async def get_authenticated_page(
    browser: Browser,
    username: str = 'admin',
    base_url: str = BASE_URL,
    timeout: int = 15000,
) -> Page:
    """
    使用已有 browser 创建已认证的 Page（需自行管理 browser 生命周期）。

    Args:
        browser: Playwright Browser 实例
        username: 登录用户名
        base_url: 前端地址
        timeout: 等待超时 ms

    Returns:
        Playwright Page (已认证，已加载首页，store 已就绪)
    """
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080}
    )
    page = await context.new_page()

    await page.goto(f'{DEV_LOGIN_URL}?username={username}')
    await page.goto(base_url, wait_until='domcontentloaded', timeout=timeout)
    await page.wait_for_function(_STORE_READY_SCRIPT, timeout=timeout)

    return page


async def go_to(page: Page, path: str):
    """
    SPA 内部导航到受保护页面（避免 page.goto 的全页刷新竞态）。

    适用场景：在 authenticated_page() 之后，跳转到具体的目标页面。

    Args:
        page: 已认证的 Playwright Page
        path: 目标路径，如 '/system/archdata' 或 '/system/archdata?id=1'

    Example:
        async with authenticated_page() as page:
            await go_to(page, '/system/archdata')
            # 开始测试目标页面
    """
    await page.evaluate(_ROUTER_PUSH_SCRIPT, path)
    await page.wait_for_timeout(2000)

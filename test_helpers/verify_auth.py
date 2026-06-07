"""
验证新认证方案。

运行：
  python d:/filework/excel-to-diagram/test_helpers/verify_auth.py
"""

import asyncio
import sys

from playwright.async_api import async_playwright

API_URL = 'http://localhost:3010'
APP_URL = 'http://localhost:3004'

_STORE_READY = """
() => {
    const app = document.querySelector('#app')?.__vue_app__;
    if (!app) return false;
    const pinia = app.config.globalProperties.$pinia;
    const store = pinia._s.get('auth');
    return store && store.sessionReady && store.user != null;
}
"""


async def test_1_dev_login_endpoint():
    """Test 1: 验证 dev-login 端点设置 cookie"""
    print('=' * 60)
    print('Test 1: dev-login 端点')
    print('=' * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print('[1] GET /api/v1/auth/dev-login?username=admin ...')
        resp = await page.goto(f'{API_URL}/api/v1/auth/dev-login?username=admin')
        body = await resp.text()
        print(f'    Status: {resp.status}')
        print(f'    Body: {body[:150]}')

        cookies = await context.cookies()
        auth = [c for c in cookies if c['name'] == 'auth_token']
        ok = resp.status == 200 and len(auth) > 0 and auth[0]['httpOnly']
        print(f'    Cookie: {"OK (httpOnly)" if ok else "FAIL"}')
        print(f'[{"PASS" if ok else "FAIL"}]')

        await browser.close()
        return ok


async def test_2_root_then_router_push():
    """Test 2: 先加载首页等待 store 就绪，再 router.push 导航"""
    print('\n' + '=' * 60)
    print('Test 2: 首页等待 + router.push')
    print('=' * 60)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        print('[1] dev-login ...')
        await page.goto(f'{API_URL}/api/v1/auth/dev-login?username=admin')

        print('[2] 加载首页 ...')
        await page.goto(APP_URL, wait_until='domcontentloaded', timeout=15000)

        print('[3] 等待 store 就绪 (sessionReady + user) ...')
        await page.wait_for_function(_STORE_READY, timeout=10000)
        print('    Store 已就绪')

        print('[4] router.push /system/archdata ...')
        await page.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router;
                router.push('/system/archdata');
            }
        """)
        await page.wait_for_timeout(2000)

        url = page.url
        is_protected = 'archdata' in url or '/system' in url
        is_redirect = 'not_logged_in' in url or 'login' in url
        print(f'    URL: {url}')

        if is_protected:
            print('[PASS] 成功进入受保护页面!')
            await page.screenshot(path='test_helpers/test_router_push.png')
        elif is_redirect:
            print('[FAIL] 被重定向')
        else:
            print(f'[WARN] {url}')

        await browser.close()
        return is_protected


async def test_3_helper_module_with_target():
    """Test 3: 使用 authenticated_page(target_url=...) 一步到位"""
    print('\n' + '=' * 60)
    print('Test 3: authenticated_page(target_url=...)')
    print('=' * 60)

    sys.path.insert(0, '.')
    from test_helpers.browser_auth import authenticated_page

    async with authenticated_page(
        username='admin', target_url='/system/archdata', headless=False
    ) as page:
        url = page.url
        is_protected = 'archdata' in url or '/system' in url

        auth = await page.evaluate("""
            () => {
                const app = document.querySelector('#app')?.__vue_app__;
                if (!app) return {ready: false};
                const pinia = app.config.globalProperties.$pinia;
                const store = pinia._s.get('auth');
                return {
                    ready: true,
                    isLoggedIn: store?.isLoggedIn,
                    username: store?.user?.username,
                };
            }
        """)
        print(f'    URL: {url}')
        print(f'    Auth: {auth}')

        ok = auth.get('isLoggedIn') and is_protected
        print(f'[{"PASS" if ok else "FAIL"}]')
        if ok:
            await page.screenshot(path='test_helpers/test_one_step.png')

    return ok


async def test_4_helper_module_then_go_to():
    """Test 4: authenticated_page() + go_to() 两步"""
    print('\n' + '=' * 60)
    print('Test 4: authenticated_page() + go_to()')
    print('=' * 60)

    sys.path.insert(0, '.')
    from test_helpers.browser_auth import authenticated_page, go_to

    async with authenticated_page(username='admin', headless=False) as page:
        print('[1] 首页已加载，store 已就绪')
        print(f'    当前 URL: {page.url}')

        print('[2] go_to /system/archdata ...')
        await go_to(page, '/system/archdata')

        url = page.url
        is_protected = 'archdata' in url
        print(f'    URL: {url}')
        ok = is_protected
        print(f'[{"PASS" if ok else "FAIL"}]')

    return ok


async def main():
    results = {}

    results['dev_login_endpoint'] = await test_1_dev_login_endpoint()
    results['root+router_push'] = await test_2_root_then_router_push()
    results['helper_one_step'] = await test_3_helper_module_with_target()
    results['helper_two_step'] = await test_4_helper_module_then_go_to()

    print('\n' + '=' * 60)
    print('RESULTS')
    print('=' * 60)
    for name, ok in results.items():
        print(f'  {name:.<40} {"PASS" if ok else "FAIL"}')

    all_pass = all(results.values())
    print(f'\n{"ALL PASS" if all_pass else "SOME FAILED"}')
    return 0 if all_pass else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))

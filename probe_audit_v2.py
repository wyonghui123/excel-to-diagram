"""
用 Playwright + 直接注入 cookie 验证 domain 详情页操作日志 tab
"""
import asyncio
import requests
from playwright.async_api import async_playwright

async def main():
    base = 'http://localhost:3010'

    # 1. dev-login 拿 cookie
    r = requests.get(f'{base}/api/v1/auth/dev-login?username=admin', timeout=5)
    cookies = dict(r.cookies)
    print(f'Got cookies: {list(cookies.keys())}')

    # 2. 找到正确路由
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        # 注入 cookie
        for name, value in cookies.items():
            await context.add_cookies([{
                'name': name, 'value': value,
                'domain': 'localhost', 'path': '/',
                'httpOnly': True, 'secure': False
            }])

        page = await context.new_page()

        # 收集 API 请求
        api_calls = []
        page.on('request', lambda req: api_calls.append((req.method, req.url[:200])) if '/audit/logs' in req.url else None)

        # 收集 console 错误
        console_errors = []
        page.on('console', lambda msg: console_errors.append((msg.type, msg.text)) if msg.type == 'error' else None)

        # 3. 尝试不同路径
        for url in [
            'http://localhost:3004/',
            'http://localhost:3004/data-model/domains/683',
            'http://localhost:3004/business-object/domain/683',
        ]:
            print(f'\n3. try: {url}')
            try:
                await page.goto(url, timeout=10000)
                await page.wait_for_load_state('domcontentloaded', timeout=5000)
                await page.wait_for_timeout(2000)
                body = await page.text_content('body')
                snippet = body[:200].replace('\n', ' ') if body else 'empty'
                print(f'   body[:200]: {snippet[:200]}')
            except Exception as e:
                print(f'   error: {e}')

        # 4. 看路由
        import subprocess
        result = subprocess.run(
            ['powershell', '-Command', "Get-Content d:\\filework\\excel-to-diagram\\src\\router\\modules\\business.js -ErrorAction SilentlyContinue"],
            capture_output=True, text=True
        )
        print(f'\n4. business.js routes:')
        print(result.stdout[:1500])

        await page.screenshot(path='audit_tab_v2.png', full_page=True)
        print('\nScreenshot saved')

        print(f'\n=== API calls ({len(api_calls)}) ===')
        for m, u in api_calls[:10]:
            print(f'  {m} {u}')

        print(f'\n=== Console errors ({len(console_errors)}) ===')
        for t, txt in console_errors[:10]:
            print(f'  [{t}] {txt[:200]}')

        await browser.close()

asyncio.run(main())

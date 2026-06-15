"""
用 dev-login 验证 domain 详情页操作日志 tab
"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 收集网络请求
        api_calls = []
        page.on('request', lambda req: api_calls.append((req.method, req.url[:120])) if any(k in req.url for k in ['/audit/logs', '/audit/', '/bo/domain', '/bo/sub_domain', '/bo/relationship']) else None)

        # 1. dev-login
        print('1. dev-login...')
        await page.goto('http://localhost:3004/dev-login?username=admin')
        await page.wait_for_timeout(2000)
        print(f'   Current URL: {page.url}')

        # 看下登录状态
        cookies = await context.cookies()
        print(f'   cookies: {[c["name"] for c in cookies]}')

        # 2. 尝试 domain 详情页 — 寻找真实路由
        print('\n2. 寻找 domain 详情页路由...')
        # 从 router 文件找路径
        import subprocess
        result = subprocess.run(
            ['powershell', '-Command', "Get-ChildItem d:\\filework\\excel-to-diagram\\src\\router -Recurse -ErrorAction SilentlyContinue | Select-Object FullName"],
            capture_output=True, text=True
        )
        print('   router files:')
        print(result.stdout[:500])

        # 尝试常见路径
        urls = [
            'http://localhost:3004/',
            'http://localhost:3004/domains',
            'http://localhost:3004/data-model',
            'http://localhost:3004/data-model/domain/683',
            'http://localhost:3004/admin',
        ]
        for url in urls:
            print(f'\n   try: {url}')
            try:
                await page.goto(url, timeout=10000)
                await page.wait_for_load_state('domcontentloaded', timeout=5000)
                await page.wait_for_timeout(1500)
                # 看页面内容
                body_text = await page.text_content('body')
                snippet = body_text[:200].replace('\n', ' ') if body_text else 'empty'
                print(f'   body[:200]: {snippet[:150]}')
            except Exception as e:
                print(f'   error: {e}')

        # 看 API 调用
        print(f'\n=== API calls captured ({len(api_calls)}) ===')
        for m, u in api_calls[:20]:
            print(f'  {m} {u}')

        await page.screenshot(path='audit_tab_after_dev_login.png', full_page=True)
        print('\nScreenshot saved')

        await browser.close()

asyncio.run(main())

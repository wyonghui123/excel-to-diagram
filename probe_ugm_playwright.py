"""用 Playwright 验证用户组详情页操作日志 tab 看到成员变更"""
import asyncio
import requests
from playwright.async_api import async_playwright

async def main():
    base = 'http://localhost:3010'
    r = requests.get(f'{base}/api/v1/auth/dev-login?username=admin', timeout=5)
    cookies = dict(r.cookies)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        for name, value in cookies.items():
            await context.add_cookies([{
                'name': name, 'value': value,
                'domain': 'localhost', 'path': '/',
                'httpOnly': True, 'secure': False
            }])
        page = await context.new_page()

        api_calls = []
        page.on('request', lambda req: api_calls.append((req.method, req.url[:200])) if '/audit/logs' in req.url else None)

        url = 'http://localhost:3004/detail/user_group/8217'
        print(f'访问: {url}')
        await page.goto(url, timeout=15000)
        await page.wait_for_load_state('domcontentloaded', timeout=5000)
        await page.wait_for_timeout(3000)

        # 找"操作日志" tab
        for tab_text in ['操作日志', '变更历史']:
            tab = page.locator(f'text={tab_text}').first
            if await tab.count() > 0:
                await tab.click()
                await page.wait_for_timeout(2000)
                section = page.locator('.op-audit-log-section').first
                if await section.count() > 0:
                    text = await section.text_content()
                    print(f'section text[:400]: {text[:400]}')
                await page.screenshot(path='user_group_8217_audit.png', full_page=True)
                print('截图: user_group_8217_audit.png')
                break

        # 看 API calls
        print(f'\n=== API calls ({len(api_calls)}) ===')
        for m, u in api_calls[:5]:
            print(f'  {m} {u}')

        await browser.close()

asyncio.run(main())

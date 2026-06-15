"""
用 Playwright + cookie 注入, 访问 /detail/domain/683, 验证操作日志 tab
"""
import asyncio
import requests
from playwright.async_api import async_playwright

async def main():
    base = 'http://localhost:3010'

    r = requests.get(f'{base}/api/v1/auth/dev-login?username=admin', timeout=5)
    cookies = dict(r.cookies)
    print(f'Got cookies: {list(cookies.keys())}')

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

        console_msgs = []
        page.on('console', lambda msg: console_msgs.append((msg.type, msg.text[:200])))
        page.on('pageerror', lambda err: console_msgs.append(('pageerror', str(err)[:200])))

        for ot, oid in [('domain', 683), ('sub_domain', 68), ('relationship', 35)]:
            url = f'http://localhost:3004/detail/{ot}/{oid}'
            print(f'\n=== 访问 {url} ===')
            try:
                await page.goto(url, timeout=15000)
                await page.wait_for_load_state('domcontentloaded', timeout=5000)
                await page.wait_for_timeout(3000)

                # 看页面内容
                body = await page.text_content('body')
                snippet = body[:300].replace('\n', ' ') if body else 'empty'
                print(f'  body[:300]: {snippet[:300]}')

                # 查找"操作日志" tab
                for tab_text in ['操作日志', '变更历史', '历史', '历史记录', '日志']:
                    tab = page.locator(f'text={tab_text}').first
                    if await tab.count() > 0:
                        print(f'  找到 tab: "{tab_text}"')
                        await tab.click()
                        await page.wait_for_timeout(2000)
                        # 看 audit log section
                        section = page.locator('.op-audit-log-section, [class*="audit-log-section"]').first
                        section_count = await page.locator('.op-audit-log-section').count()
                        print(f'  op-audit-log-section count: {section_count}')
                        if section_count > 0:
                            text = await page.locator('.op-audit-log-section').first.text_content()
                            print(f'  section text[:300]: {text[:300]}')
                        # 截图
                        safe = f'{ot}_{oid}_audit.png'
                        await page.screenshot(path=safe, full_page=True)
                        print(f'  截图: {safe}')
                        break
                else:
                    print(f'  未找到操作日志 tab, 截图')
                    await page.screenshot(path=f'{ot}_{oid}_notab.png', full_page=True)
            except Exception as e:
                print(f'  error: {e}')

        # 看 API 调用
        print(f'\n=== /audit/logs API calls ({len(api_calls)}) ===')
        for m, u in api_calls[:20]:
            print(f'  {m} {u}')

        # 看 console 错误
        print(f'\n=== Console messages ({len(console_msgs)}) ===')
        for t, txt in console_msgs[:20]:
            print(f'  [{t}] {txt}')

        await browser.close()

asyncio.run(main())

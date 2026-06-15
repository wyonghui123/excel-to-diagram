"""完整复现 v5: 用 UTF-8 + 简单选择器"""
# -*- coding: utf-8 -*-
import asyncio
import requests
import sys
sys.stdout.reconfigure(encoding='utf-8')

from playwright.async_api import async_playwright

async def main():
    base = 'http://localhost:3010'
    r = requests.get(f'{base}/api/v1/auth/dev-login?username=TEST888', timeout=5)
    cookies = dict(r.cookies)
    print(f'dev-login: {r.status_code}')

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        for n, v in cookies.items():
            await context.add_cookies([{
                'name': n, 'value': v,
                'domain': 'localhost', 'path': '/',
                'httpOnly': True, 'secure': False
            }])

        page = await context.new_page()
        bad_responses = []
        async def handle_response(resp):
            if resp.status >= 400:
                try:
                    body = await resp.body()
                    body_text = body.decode('utf-8', errors='replace')[:500]
                except Exception:
                    body_text = '<binary>'
                bad_responses.append({
                    'status': resp.status,
                    'url': resp.url,
                    'method': resp.request.method,
                    'body': body_text,
                })
        page.on('response', handle_response)
        console_errors = []
        page.on('console', lambda m: console_errors.append((m.type, m.text[:500])) if m.type == 'error' else None)

        url = 'http://localhost:3004/system/archdata'
        await page.goto(url, timeout=30000, wait_until='domcontentloaded')
        await page.wait_for_timeout(3000)

        # 选产品 V007V2_RO
        print('\n[step1] select product')
        await page.locator('.el-select__wrapper').nth(0).click()
        await page.wait_for_timeout(1500)
        await page.locator('.el-select-dropdown__item:has-text("BUGV007_AUDIT_V007")').first.click()
        print('  [OK] BUGV007_AUDIT_V007')
        await page.wait_for_timeout(2500)

        # 选版本
        print('\n[step2] select version')
        await page.locator('.el-select__wrapper').nth(1).click()
        await page.wait_for_timeout(1500)
        items = await page.locator('.el-select-dropdown__item:visible').all()
        print(f'  version items: {len(items)}')
        if items:
            text = await items[0].text_content()
            await items[0].click()
            print(f'  [OK] {text[:30]}')
            await page.wait_for_timeout(15000)

        # 报告
        print(f'\n=== 4xx/5xx 响应 ({len(bad_responses)}) ===')
        for r in bad_responses[:30]:
            print(f'  {r["status"]} {r["method"]} {r["url"][:200]}')
            print(f'    body: {r["body"]}')

        print(f'\n=== Console errors ({len(console_errors)}) ===')
        for t, msg in console_errors[:30]:
            print(f'  ERR: {msg[:500]}')

        await page.screenshot(path='archdata_v5.png', full_page=True)
        await browser.close()

asyncio.run(main())

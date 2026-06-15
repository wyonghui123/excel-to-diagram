# -*- coding: utf-8 -*-
"""复现 400 错误: TEST888 选 供应链管理系统 / v1.0"""
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
                    body_text = body.decode('utf-8', errors='replace')[:800]
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
        page.on('console', lambda m: console_errors.append((m.type, m.text[:600])) if m.type == 'error' else None)

        url = 'http://localhost:3004/system/archdata'
        await page.goto(url, timeout=30000, wait_until='domcontentloaded')
        await page.wait_for_timeout(3000)

        # 选产品
        print('[step1] select 供应链管理系统')
        await page.locator('.el-select__wrapper').nth(0).click()
        await page.wait_for_timeout(1500)
        await page.locator('.el-select-dropdown__item:has-text("供应链管理系统")').first.click()
        print('  [OK] 供应链管理系统')
        await page.wait_for_timeout(2500)

        # 选版本 v1.0
        print('[step2] select v1.0')
        await page.locator('.el-select__wrapper').nth(1).click()
        await page.wait_for_timeout(1500)
        items = await page.locator('.el-select-dropdown__item:visible').all()
        print(f'  version items: {len(items)}')
        for i, it in enumerate(items):
            text = (await it.text_content() or '').strip()
            print(f'  [{i}] {text!r}')
        # 选 v1.0
        v1 = page.locator('.el-select-dropdown__item:has-text("v1.0")').first
        if await v1.count() > 0:
            await v1.click()
            print('  [OK] v1.0')
            await page.wait_for_timeout(20000)  # 等列表加载
        else:
            print('  [FAIL] 没找到 v1.0')

        # 报告
        print(f'\n=== 4xx/5xx 响应 ({len(bad_responses)}) ===')
        for r in bad_responses[:30]:
            print(f'\n  {r["status"]} {r["method"]} {r["url"][:200]}')
            print(f'    body: {r["body"]}')

        print(f'\n=== Console errors ({len(console_errors)}) ===')
        for t, msg in console_errors[:30]:
            print(f'  ERR: {msg[:500]}')

        await page.screenshot(path='archdata_v6.png', full_page=True)
        await browser.close()

asyncio.run(main())

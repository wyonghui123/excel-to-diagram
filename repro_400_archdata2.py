"""
完整复现: TEST888 选产品+版本, 触发列表加载, 看 4xx 错误
"""
import asyncio
import requests
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
        console_msgs = []
        bad_responses = []  # 详细记录 4xx/5xx
        async def handle_response(resp):
            if resp.status >= 400:
                try:
                    body = await resp.body()
                    body_text = body.decode('utf-8', errors='replace')[:500]
                except Exception:
                    body_text = '<binary or unavailable>'
                bad_responses.append({
                    'status': resp.status,
                    'url': resp.url,
                    'method': resp.request.method,
                    'body': body_text,
                })
        page.on('response', handle_response)
        page.on('console', lambda m: console_msgs.append((m.type, m.text[:500])))

        url = 'http://localhost:3004/system/archdata'
        print(f'\n=== 访问: {url} ===')
        await page.goto(url, timeout=30000, wait_until='domcontentloaded')
        await page.wait_for_timeout(3000)

        # 步骤 1: 选产品 (RACE3)
        print('\n=== 选产品 RACE3 ===')
        # 找"产品"下拉
        product_dropdown = page.locator('text=请选择库').first
        if await product_dropdown.count() > 0:
            await product_dropdown.click()
            await page.wait_for_timeout(1500)
            # 选 RACE3_1781437973
            race3_opt = page.locator('text=RACE3_1781437973').first
            if await race3_opt.count() > 0:
                await race3_opt.click()
                await page.wait_for_timeout(1500)
                print('  选中产品 RACE3_1781437973')

        # 步骤 2: 选版本
        print('\n=== 选版本 ===')
        version_dropdown = page.locator('text=请选择').first
        if await version_dropdown.count() > 0:
            await version_dropdown.click()
            await page.wait_for_timeout(1500)
            # 选 version 764 或 v1
            for label in ['v1.0.0', 'v1', 'V1', '1.0.0', 'RACE3_v1', 'v2.0', '默认版本']:
                v_opt = page.locator(f'text={label}').first
                if await v_opt.count() > 0:
                    await v_opt.click()
                    print(f'  选中版本 {label}')
                    break
            await page.wait_for_timeout(3000)

        # 等列表加载
        print('\n=== 等待列表加载 (10s) ===')
        await page.wait_for_timeout(10000)

        # 报告
        print(f'\n=== 4xx/5xx 响应 ({len(bad_responses)}) ===')
        for r in bad_responses:
            print(f'\n  {r["status"]} {r["method"]} {r["url"][:200]}')
            print(f'  body: {r["body"]}')

        errs = [m for m in console_msgs if m[0] == 'error']
        print(f'\n=== Console errors ({len(errs)}) ===')
        for t, msg in errs[:20]:
            print(f'  ERR: {msg[:300]}')

        await page.screenshot(path='archdata_with_data.png', full_page=True)
        print('\n截图: archdata_with_data.png')

        await browser.close()

asyncio.run(main())

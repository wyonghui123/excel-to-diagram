"""
完整复现 v4: 强制点击 dropdown 用 Element Plus 标准 selector
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
        page.on('console', lambda m: console_msgs.append((m.type, m.text[:500])))

        url = 'http://localhost:3004/system/archdata'
        await page.goto(url, timeout=30000, wait_until='domcontentloaded')
        await page.wait_for_timeout(3000)

        # 1. 点击第一个 el-select 的 .el-select__wrapper
        print('\n=== 找产品下拉 ===')
        selects = await page.locator('.el-select__wrapper').all()
        print(f'  找到 {len(selects)} 个 el-select')
        if selects:
            # 第一个是产品
            await selects[0].click()
            await page.wait_for_timeout(1500)
            # 看下拉
            await page.screenshot(path='archdata_step1.png', full_page=True)
            # 找 V007V2_RO 选项
            item = page.locator('.el-select-dropdown__item:has-text("V007V2_RO")').first
            if await item.count() > 0:
                await item.click()
                print('  ✓ 选 V007V2_RO')
                await page.wait_for_timeout(2500)

                # 选版本（第二个 el-select）
                print('\n=== 选版本 ===')
                selects2 = await page.locator('.el-select__wrapper').all()
                if len(selects2) >= 2:
                    await selects2[1].click()
                    await page.wait_for_timeout(1500)
                    # 选第一个版本
                    items_v = await page.locator('.el-select-dropdown__item:visible').all()
                    print(f'  版本选项数: {len(items_v)}')
                    if items_v:
                        text = await items_v[0].text_content()
                        await items_v[0].click()
                        print(f'  ✓ 选版本: {text[:30]}')
                        await page.wait_for_timeout(15000)  # 等列表加载

        # 报告
        print(f'\n=== 4xx/5xx 响应 ({len(bad_responses)}) ===')
        for r in bad_responses[:30]:
            print(f'\n  {r["status"]} {r["method"]} {r["url"][:200]}')
            print(f'  body: {r["body"]}')

        errs = [m for m in console_msgs if m[0] == 'error']
        print(f'\n=== Console errors ({len(errs)}) ===')
        for t, msg in errs[:30]:
            print(f'  ERR: {msg[:500]}')

        await page.screenshot(path='archdata_final.png', full_page=True)
        print('\n截图: archdata_final.png')

        await browser.close()

asyncio.run(main())

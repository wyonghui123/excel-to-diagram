"""
完整复现 v3: 选 RACE3 类似产品 + 版本, 触发列表加载, 看 4xx 错误
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

        # 选产品
        print('\n=== 选产品: V007V2_RO_1781437377_590BB ===')
        product_dropdown = page.locator('text=请选择库').first
        await product_dropdown.click()
        await page.wait_for_timeout(1500)
        await page.locator('text=V007V2_RO_1781437377_590BB').first.click()
        await page.wait_for_timeout(2000)
        print('  ✓ 已选产品')

        # 选版本
        print('\n=== 选版本 ===')
        # 等版本下拉可用
        version_dropdown = page.locator('text=请选择').first
        await version_dropdown.click()
        await page.wait_for_timeout(1500)
        # 截图看版本选项
        await page.screenshot(path='archdata_versions.png', full_page=True)
        # 尝试选 v1 或 v2
        for label in ['v1.0', 'v2.0', 'V1', 'V2', 'v1', 'v2', 'v3', '1.0.0', '1.0', '默认', '默认版本']:
            v_opt = page.locator(f'text={label}').first
            if await v_opt.count() > 0:
                await v_opt.click()
                print(f'  ✓ 已选版本 {label}')
                break
        else:
            # 选第一个非空版本
            print('  尝试选第一个版本')
            try:
                items = page.locator('.el-select-dropdown__item').all()
                if items:
                    for it in items:
                        text = await it.text_content()
                        if text and text.strip():
                            await it.click()
                            print(f'  ✓ 已选: {text[:30]}')
                            break
            except Exception as e:
                print(f'  err: {e}')

        # 等列表加载
        print('\n=== 等待列表加载 (15s) ===')
        await page.wait_for_timeout(15000)

        # 报告
        print(f'\n=== 4xx/5xx 响应 ({len(bad_responses)}) ===')
        for r in bad_responses[:20]:
            print(f'\n  {r["status"]} {r["method"]} {r["url"][:200]}')
            print(f'  body: {r["body"]}')

        errs = [m for m in console_msgs if m[0] == 'error']
        print(f'\n=== Console errors ({len(errs)}) ===')
        for t, msg in errs[:30]:
            print(f'  ERR: {msg[:400]}')

        await page.screenshot(path='archdata_after_select.png', full_page=True)
        print('\n截图: archdata_after_select.png')

        await browser.close()

asyncio.run(main())

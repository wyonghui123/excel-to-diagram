"""
复现 TEST888 用户在 /system/archdata 的 400 错误
捕获浏览器控制台 + 网络响应 (含 400 response body)
"""
import asyncio
import requests
from playwright.async_api import async_playwright

async def main():
    base = 'http://localhost:3010'
    # 1. dev-login TEST888
    r = requests.get(f'{base}/api/v1/auth/dev-login?username=TEST888', timeout=5)
    print(f'dev-login: {r.status_code}')
    if r.status_code != 200:
        # 普通登录路径
        r2 = requests.post(f'{base}/api/v1/auth/login',
            json={'username': 'TEST888', 'password': 'TEST888'}, timeout=5)
        print(f'normal login: {r2.status_code} {r2.text[:200]}')
        if r2.status_code != 200:
            return
    cookies = dict(r.cookies)

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

        # 收集所有 console 消息
        console_msgs = []
        page.on('console', lambda m: console_msgs.append((m.type, m.text[:500])))

        # 收集所有 4xx 响应
        bad_responses = []
        def handle_response(resp):
            if resp.status >= 400:
                body = ''
                try:
                    # 不能直接 await, 但能拿到 url
                    bad_responses.append({
                        'status': resp.status,
                        'url': resp.url,
                        'method': resp.request.method,
                    })
                except Exception as e:
                    pass
        page.on('response', handle_response)

        # 收集失败的 request
        failed_reqs = []
        def handle_failed(req):
            failed_reqs.append({
                'url': req.url,
                'method': req.method,
                'failure': req.failure,
            })
        page.on('requestfailed', handle_failed)

        # 访问页面
        url = 'http://localhost:3004/system/archdata'
        print(f'\n=== 访问: {url} ===')
        try:
            await page.goto(url, timeout=30000, wait_until='domcontentloaded')
        except Exception as e:
            print(f'goto err: {e}')

        # 等所有列表加载完
        await page.wait_for_timeout(10000)

        # 报告
        print(f'\n=== 4xx/5xx 响应 ({len(bad_responses)}) ===')
        for r in bad_responses:
            print(f'  {r["status"]} {r["method"]} {r["url"][:150]}')

        print(f'\n=== Failed requests ({len(failed_reqs)}) ===')
        for r in failed_reqs[:10]:
            print(f'  {r["method"]} {r["url"][:150]} failure={r["failure"]}')

        # 看 console error
        errs = [m for m in console_msgs if m[0] == 'error']
        print(f'\n=== Console errors ({len(errs)}) ===')
        for t, msg in errs[:20]:
            print(f'  ERR: {msg[:300]}')

        # 看完整 console
        print(f'\n=== Console warnings ({len([m for m in console_msgs if m[0] == "warning"])}) ===')
        for t, msg in [m for m in console_msgs if m[0] == 'warning'][:10]:
            print(f'  WARN: {msg[:300]}')

        # 截图
        await page.screenshot(path='archdata_400_repro.png', full_page=True)
        print('\n截图: archdata_400_repro.png')

        await browser.close()

asyncio.run(main())

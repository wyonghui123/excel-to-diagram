"""
网络请求拦截测试：查看前端实际调用了哪些 audit log API
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

import asyncio
from playwright.async_api import async_playwright

BASE_URL = 'http://localhost:3010/api/v2'

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 收集所有 API 请求
        audit_requests = []
        all_requests = []

        def on_request(request):
            url = request.url
            if 'audit' in url.lower() or 'log' in url.lower():
                audit_requests.append({
                    'url': url,
                    'method': request.method,
                })
            all_requests.append({
                'url': url,
                'method': request.method,
            })

        def on_response(response):
            if 'audit' in response.url.lower() or 'log' in response.url.lower():
                print(f"  → [{response.status}] {response.url}")

        page.on('request', on_request)
        page.on('response', on_response)

        # dev-login
        await page.goto('http://localhost:3004/')
        await page.evaluate("fetch('http://localhost:3010/api/v1/auth/dev-login?username=admin', {credentials: 'include'})")

        # 导航到枚举类型详情页
        print("导航到枚举类型详情页...")
        await page.goto('http://localhost:3004/detail/enum_type/annotation_category')
        await page.wait_for_load_state('domcontentloaded')
        await page.wait_for_timeout(3000)

        print("\n=== Audit 相关请求 ===")
        for req in audit_requests:
            print(f"  {req['method']} {req['url']}")

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())

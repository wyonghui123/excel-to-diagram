"""
精确验证：监听所有 API 请求并等待 AuditLog 加载完成
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        api_requests = []

        def on_request(request):
            url = request.url
            if 'localhost:3010' in url:
                api_requests.append({
                    'method': request.method,
                    'url': url,
                })
                print(f"  [REQ] {request.method} {url}")

        def on_response(response):
            url = response.url
            if 'localhost:3010' in url:
                print(f"  [RES] {response.status} {url[:120]}")

        page.on('request', on_request)
        page.on('response', on_response)

        # dev-login
        await page.goto('http://localhost:3004/')
        await page.evaluate("fetch('http://localhost:3010/api/v1/auth/dev-login?username=admin', {credentials: 'include'})")

        print("\n导航到枚举类型详情页...")
        await page.goto('http://localhost:3004/detail/enum_type/annotation_category')
        await page.wait_for_load_state('domcontentloaded')
        await page.wait_for_timeout(3000)

        # 截图看实际页面
        await page.screenshot(path='d:/filework/excel-to-diagram/test_enum_page_full.png')

        # 尝试点击变更历史标签
        print("\n尝试点击变更历史...")
        for sel in ['.el-tabs__item:has-text("变更历史")', 'text=变更历史', '[class*="tab"]:has-text("变更历史")']:
            tabs = page.locator(sel)
            if await tabs.count() > 0:
                for i in range(await tabs.count()):
                    tab = tabs.nth(i)
                    text = (await tab.text_content() or '').strip()
                    if '变更历史' in text:
                        await tab.click()
                        print(f"  点击: {text}")
                        await page.wait_for_timeout(3000)
                        break

        # 检查空状态 vs 表格
        print("\n页面检查:")
        empty = await page.locator('text=缺少 objectType').count()
        print(f"  空状态消息: {empty}")

        tables = await page.locator('.el-table').count()
        print(f"  .el-table 数量: {tables}")

        for i in range(tables):
            el = page.locator('.el-table').nth(i)
            visible = await el.is_visible()
            rows = await el.locator('tbody tr').count()
            print(f"    Table[{i}]: visible={visible}, rows={rows}")

        await page.screenshot(path='d:/filework/excel-to-diagram/test_enum_page_final.png')

        # 统计 API 请求
        print(f"\n所有 API 请求 ({len(api_requests)} 个):")
        for r in api_requests:
            if 'audit' in r['url'].lower() or 'log' in r['url'].lower():
                print(f"  ★ {r['method']} {r['url']}")
            else:
                print(f"    {r['method']} {r['url'][:100]}")

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())

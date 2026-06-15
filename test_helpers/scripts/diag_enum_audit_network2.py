"""
精确网络拦截测试：监听所有 API 请求，特别关注 audit log 相关
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        # 监听所有到 localhost:3010 的请求
        api_requests = []

        def on_request(request):
            url = request.url
            if 'localhost:3010' in url and ('audit' in url.lower() or 'log' in url.lower()):
                api_requests.append(f"  {request.method} {url}")

        def on_response(response):
            url = response.url
            if 'localhost:3010' in url and ('audit' in url.lower() or 'log' in url.lower()):
                try:
                    body = response.text()
                    log_line = f"  → [{response.status}] {url[:100]}"
                    if response.status >= 400:
                        log_line += f" | {body[:100]}"
                    print(log_line)
                except Exception:
                    print(f"  → [{response.status}] {url[:100]}")

        page.on('request', on_request)
        page.on('response', on_response)

        # dev-login
        await page.goto('http://localhost:3004/')
        await page.evaluate("fetch('http://localhost:3010/api/v1/auth/dev-login?username=admin', {credentials: 'include'})")

        # 导航到枚举类型详情页
        print("导航到枚举类型详情页...")
        await page.goto('http://localhost:3004/detail/enum_type/annotation_category')
        await page.wait_for_load_state('domcontentloaded')
        await page.wait_for_timeout(2000)

        # 尝试点击"变更历史"标签
        print("\n尝试点击'变更历史'标签...")
        tab_clicked = False

        # 尝试各种可能的标签选择器
        selectors = [
            'text=变更历史',
            '.el-tabs__item:has-text("变更历史")',
            '[class*="tab"]:has-text("变更历史")',
            '.op-tabs__item:has-text("变更历史")',
        ]
        for sel in selectors:
            try:
                tabs = page.locator(sel)
                count = await tabs.count()
                if count > 0:
                    print(f"  找到 {count} 个: {sel}")
                    for i in range(count):
                        tab = tabs.nth(i)
                        text = await tab.text_content()
                        print(f"    [{i}] {text.strip()}")
                        if '变更历史' in text:
                            await tab.click()
                            tab_clicked = True
                            print(f"  点击了: {text.strip()}")
                            await page.wait_for_timeout(3000)
                            break
            except Exception as e:
                print(f"  选择器 {sel} 出错: {e}")

        # 打印所有捕获的 API 请求
        print(f"\n捕获到 {len(api_requests)} 个 audit/log 相关请求:")
        for r in api_requests:
            print(r)

        # 检查页面当前内容
        print("\n页面检查:")
        empty_state = await page.locator('text=缺少 objectType').count()
        print(f"  空状态消息: {empty_state} 个")

        table_count = await page.locator('.el-table').count()
        print(f"  .el-table 数量: {table_count}")

        # 截图
        await page.screenshot(path='d:/filework/excel-to-diagram/test_enum_page_detail.png')
        print("  截图: test_enum_page_detail.png")

        await browser.close()

if __name__ == '__main__':
    asyncio.run(main())

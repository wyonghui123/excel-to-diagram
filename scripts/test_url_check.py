#!/usr/bin/env python3
"""[BMRD 2026-06-14] 检查新建 product UI 真实行为"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 收集网络
        network_log = []
        page.on('request', lambda req: network_log.append(f'{req.method} {req.url}') if '/api/' in req.url or '/detail' in req.url else None)
        page.on('console', lambda msg: print(f'  [console.{msg.type}] {msg.text}'))

        # 1. dev-login
        await page.goto('http://localhost:3010/api/v1/auth/dev-login?username=admin')
        await page.wait_for_timeout(1000)

        # 2. 试 list 页面
        print('=== A. /product-management (列表) ===')
        await page.goto('http://localhost:3010/product-management')
        await page.wait_for_timeout(3000)
        print('  最终 URL:', page.url)
        print('  标题:', await page.title())

        # 3. 试 /detail/product/new
        print('\n=== B. /detail/product/new?mode=add ===')
        await page.goto('http://localhost:3010/detail/product/new?mode=add')
        await page.wait_for_timeout(3000)
        print('  最终 URL:', page.url)
        print('  标题:', await page.title())

        # 4. 试 /product-management/new?mode=add (列表+new)
        print('\n=== C. /product-management/new?mode=add ===')
        await page.goto('http://localhost:3010/product-management/new?mode=add')
        await page.wait_for_timeout(3000)
        print('  最终 URL:', page.url)
        print('  标题:', await page.title())

        # 5. 看 body 文本
        body_text = await page.locator('body').text_content()
        print('\n  body 前 200 字:', body_text[:200] if body_text else '(空)')

        # 6. 看 child sections
        child_count = await page.locator('[data-testid="odp-child-sections"]').count()
        print(f'  child sections: {child_count}')

        # 7. 打印所有网络请求
        print('\n=== 网络请求 ===')
        for log in network_log[:30]:
            print(f'  {log}')

        await browser.close()

asyncio.run(main())

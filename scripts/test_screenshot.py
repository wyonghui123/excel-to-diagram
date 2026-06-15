#!/usr/bin/env python3
"""[BMRD 2026-06-14] 真实测试 - 截图保存"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto('http://localhost:3004/api/v1/auth/dev-login?username=admin')
        await page.wait_for_timeout(1000)

        await page.goto('http://localhost:3004/detail/product/new?mode=add')
        await page.wait_for_timeout(5000)

        # 1. 截图 - 新建页面
        await page.screenshot(path='d:/filework/excel-to-diagram/test-results/add-1.png', full_page=True)
        print('截图 1: add-1.png')

        # 填主表单
        all_inputs = await page.locator('input').all()
        if len(all_inputs) >= 2:
            await all_inputs[0].fill('TEST888122_BROWSER')
            await all_inputs[1].fill('TEST888122_BROWSER')

        # 2. 点击子表"新增"
        new_btn = page.locator('[data-testid="odp-child-sections"] button:has-text("新增")').first
        await new_btn.click(force=True, timeout=5000)
        await page.wait_for_timeout(3000)

        # 截图 - 弹窗打开
        await page.screenshot(path='d:/filework/excel-to-diagram/test-results/add-2-drawer.png', full_page=True)
        print('截图 2: add-2-drawer.png (弹窗打开后)')

        # 看所有 el-drawer
        drawers = await page.locator('.el-drawer').all()
        print(f'  drawer 总数: {len(drawers)}')
        for i, d in enumerate(drawers):
            try:
                txt = await d.inner_text()
                vis = await d.is_visible()
                print(f'  drawer[{i}] visible={vis} text 前 200: {txt[:200]}')
            except Exception as e:
                print(f'  drawer[{i}] err: {e}')

        # 看 el-drawer__body 内部
        bodies = await page.locator('.el-drawer__body').all()
        print(f'\n  drawer body 数: {len(bodies)}')
        for i, b in enumerate(bodies):
            try:
                html = await b.inner_html()
                vis = await b.is_visible()
                print(f'  body[{i}] visible={vis} html 前 500: {html[:500]}')
            except Exception as e:
                print(f'  body[{i}] err: {e}')

        await browser.close()

asyncio.run(main())

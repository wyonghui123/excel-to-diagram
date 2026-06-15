#!/usr/bin/env python3
"""[BMRD 2026-06-14] 真实测试 v4 - 看弹窗详情"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto('http://localhost:3004/api/v1/auth/dev-login?username=admin')
        await page.wait_for_timeout(1000)

        print('=== 打开 /detail/product/new?mode=add ===')
        await page.goto('http://localhost:3004/detail/product/new?mode=add')
        await page.wait_for_timeout(5000)

        # 点击子表"新增"
        new_btn = page.locator('[data-testid="odp-child-sections"] button:has-text("新增")').first
        await new_btn.click(force=True, timeout=5000)
        await page.wait_for_timeout(3000)

        # 弹窗的 body 文本
        dialog_body = await page.locator('.el-dialog__body').first.text_content()
        print(f'  弹窗 body text (前 500): {dialog_body[:500] if dialog_body else "(空)"}')

        # 弹窗的 input
        dialog_inputs = await page.locator('.el-dialog input').all()
        print(f'  弹窗 input 数: {len(dialog_inputs)}')

        # 弹窗的 form
        dialog_forms = await page.locator('.el-dialog form, .el-dialog .el-form').count()
        print(f'  弹窗 form 数: {dialog_forms}')

        # 弹窗的 el-form-item
        items = await page.locator('.el-dialog .el-form-item').count()
        print(f'  弹窗 form-item 数: {items}')

        # 看弹窗内的所有元素
        dialog_html = await page.locator('.el-dialog__body').first.inner_html()
        print(f'\n  弹窗 HTML (前 1000): {dialog_html[:1000]}')

        await browser.close()

asyncio.run(main())

#!/usr/bin/env python3
"""[BMRD 2026-06-14] 真实测试 v5 - 找弹窗"""
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

        new_btn = page.locator('[data-testid="odp-child-sections"] button:has-text("新增")').first
        await new_btn.click(force=True, timeout=5000)
        await page.wait_for_timeout(3000)

        # 找所有 dialog 类
        for sel in ['.el-dialog', '.el-drawer', '[role="dialog"]', '.ocs-dialog', '.ocs-detail-dialog']:
            cnt = await page.locator(sel).count()
            if cnt:
                print(f'  {sel}: {cnt}')
                # 第一个的 inner_text
                txt = await page.locator(sel).first.inner_text()
                print(f'    text 前 500: {txt[:500]}')

        # 看 ocs 内部所有 detail 元素
        ocs_detail = await page.locator('.ocs-detail, .ocs-drawer, .ocs-create-form').count()
        print(f'  ocs 内部 detail 类: {ocs_detail}')

        # 找所有 visible inputs
        all_in = await page.locator('input:visible').count()
        print(f'\n  所有可见 input: {all_in}')

        # 找所有 visible dialog
        vis_dialog = await page.locator('.el-dialog:visible').count()
        print(f'  visible el-dialog: {vis_dialog}')

        await browser.close()

asyncio.run(main())

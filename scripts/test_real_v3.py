#!/usr/bin/env python3
"""[BMRD 2026-06-14] 真实测试 v3 - 处理 dialog 弹窗"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        network_log = []
        page.on('request', lambda req: network_log.append({
            'method': req.method,
            'url': req.url,
            'post_data': req.post_data,
        }) if '/api/' in req.url else None)

        await page.goto('http://localhost:3004/api/v1/auth/dev-login?username=admin')
        await page.wait_for_timeout(1000)

        print('=== 打开 /detail/product/new?mode=add ===')
        await page.goto('http://localhost:3004/detail/product/new?mode=add')
        await page.wait_for_timeout(5000)

        # 填主表单
        all_inputs = await page.locator('input').all()
        if len(all_inputs) >= 2:
            await all_inputs[0].fill('TEST888122_BROWSER')
            await all_inputs[1].fill('TEST888122_BROWSER')
            print('  ✅ 填 code + name')

        # 点击子表"新增" 打开 dialog
        new_btn = page.locator('[data-testid="odp-child-sections"] button:has-text("新增")').first
        await new_btn.click(force=True, timeout=5000)
        print('  ✅ 点击新增')
        await page.wait_for_timeout(2000)

        # 看是否有 dialog
        dialogs = await page.locator('.el-dialog, .el-drawer').count()
        print(f'  弹窗数: {dialogs}')

        # 找弹窗内 inputs
        dialog_inputs = await page.locator('.el-dialog input, .el-drawer input').all()
        print(f'  弹窗 input 数: {len(dialog_inputs)}')
        for i, inp in enumerate(dialog_inputs[:5]):
            ph = await inp.get_attribute('placeholder')
            print(f'    弹窗 input[{i}]: placeholder={ph}')

        # 填 V10
        if dialog_inputs:
            # 第一个通常是 name
            await dialog_inputs[0].fill('V10_BROWSER')
            print('  ✅ 弹窗填 V10 name')
            # 第二个是 value
            if len(dialog_inputs) > 1:
                await dialog_inputs[1].fill('V10_BROWSER')
                print('  ✅ 弹窗填 V10 value')
            await page.wait_for_timeout(500)

        # 找弹窗的保存按钮
        dialog_save = page.locator('.el-dialog button:has-text("保存"), .el-drawer button:has-text("保存")').first
        if await dialog_save.count():
            await dialog_save.click(force=True, timeout=5000)
            print('  ✅ 弹窗点击保存')
            await page.wait_for_timeout(3000)

        # 弹窗关了, 关闭后看主页面是否有子表行
        await page.wait_for_timeout(2000)
        rows = await page.locator('[data-testid="odp-child-sections"] .el-table__row, [data-testid="odp-child-sections"] .ocs-table-wrapper tr').count()
        print(f'\n  弹窗关闭后, 主页面子表行数: {rows}')

        # 主页面保存
        main_save = page.locator('button:has-text("保存")').first
        is_vis = await main_save.is_visible()
        print(f'  主保存按钮 visible: {is_vis}')
        await main_save.click(force=True, timeout=5000)
        await page.wait_for_timeout(5000)

        # POST 请求
        print('\n=== POST 请求 ===')
        for log in network_log:
            if log['method'] in ('POST', 'PUT', 'PATCH'):
                print(f'  {log["method"]} {log["url"]}')
                if log['post_data']:
                    d = log['post_data']
                    if len(d) > 300:
                        d = d[:300] + '...'
                    print(f'    data: {d}')

        print(f'\n  最终 URL: {page.url}')

        await browser.close()

asyncio.run(main())

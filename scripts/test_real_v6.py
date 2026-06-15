#!/usr/bin/env python3
"""[BMRD 2026-06-14] 真实测试 v6 - 用 el-drawer"""
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

        # 点击子表"新增"
        new_btn = page.locator('[data-testid="odp-child-sections"] button:has-text("新增")').first
        await new_btn.click(force=True, timeout=5000)
        print('  ✅ 点击新增 (打开 version drawer)')
        await page.wait_for_timeout(3000)

        # 在 el-drawer 填 V10
        drawer_inputs = await page.locator('.el-drawer input').all()
        print(f'  drawer input 数: {len(drawer_inputs)}')
        for i, inp in enumerate(drawer_inputs[:5]):
            ph = await inp.get_attribute('placeholder')
            print(f'    drawer input[{i}]: placeholder={ph}')

        if drawer_inputs:
            # 第一个通常是版本名称
            await drawer_inputs[0].fill('V10_BROWSER')
            print('  ✅ 填 V10 name')
            # product_id 是 select, 跳过
            await page.wait_for_timeout(500)

        # 找 drawer 的保存按钮
        drawer_save = page.locator('.el-drawer button:has-text("保存")').first
        is_vis = await drawer_save.is_visible()
        print(f'  drawer 保存按钮 visible: {is_vis}')
        if is_vis:
            await drawer_save.click(force=True, timeout=5000)
            print('  ✅ drawer 点击保存')
            await page.wait_for_timeout(3000)

        # 关闭 drawer 后
        await page.wait_for_timeout(2000)

        # 找 ocs-content 是否有数据
        ocs_table = await page.locator('[data-testid="odp-child-sections"] .ocs-table-wrapper').count()
        print(f'\n  ocs-table-wrapper 数: {ocs_table}')

        # 看 product_id select 是否有值
        # 看 .el-table__row 数量
        rows = await page.locator('[data-testid="odp-child-sections"] .el-table__row').count()
        print(f'  el-table row 数: {rows}')

        # 主页面保存
        main_save = page.locator('button:has-text("保存")').first
        is_vis = await main_save.is_visible()
        print(f'  主保存按钮 visible: {is_vis}')
        if is_vis:
            await main_save.click(force=True, timeout=5000)
            print('  ✅ 主点击保存')
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

        # 错误
        errs = await page.locator('.el-message--error, .el-form-item__error').all()
        for e in errs[:3]:
            t = await e.text_content()
            if t and t.strip():
                print(f'  错误: {t.strip()}')

        await browser.close()

asyncio.run(main())

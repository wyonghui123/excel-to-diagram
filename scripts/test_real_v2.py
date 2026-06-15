#!/usr/bin/env python3
"""[BMRD 2026-06-14] 真实测试 v2 - 用 force click"""
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

        # 打开新建页
        print('=== 打开 /detail/product/new?mode=add ===')
        await page.goto('http://localhost:3004/detail/product/new?mode=add')
        await page.wait_for_timeout(5000)

        # 检查 child sections + 输入框
        child_count = await page.locator('[data-testid="odp-child-sections"]').count()
        inputs = await page.locator('input').count()
        print(f'  child sections 容器: {child_count}')
        print(f'  输入框数: {inputs}')

        # 填主表单
        all_inputs = await page.locator('input').all()
        if inputs >= 2:
            await all_inputs[0].fill('TEST888122_BROWSER')
            await all_inputs[1].fill('TEST888122_BROWSER')
            print('  ✅ 填了 code + name')

        # 找子表新增按钮 - 用 force + 第一个匹配
        print('\n=== 找 新增 按钮 ===')
        new_btn = page.locator('[data-testid="odp-child-sections"] button:has-text("新增")').first
        is_visible = await new_btn.is_visible()
        print(f'  新增按钮 visible: {is_visible}')
        # 强制 click (跳过 visibility/stability)
        await new_btn.click(force=True, timeout=5000)
        print('  ✅ 点击新增 (force)')
        await page.wait_for_timeout(2000)

        # 找子表新行 inputs
        new_inputs = await page.locator('[data-testid="odp-child-sections"] input').all()
        print(f'  子表 input 数: {len(new_inputs)}')
        for i, inp in enumerate(new_inputs[:3]):
            ph = await inp.get_attribute('placeholder')
            print(f'    [{i}] placeholder={ph}')

        # 填 V10
        if len(new_inputs) >= 1:
            await new_inputs[0].fill('V10_BROWSER')
            print('  ✅ 填 V10 name')
        await page.wait_for_timeout(1000)

        # 保存
        print('\n=== 保存 ===')
        save_btn = page.locator('button:has-text("保存")').first
        is_visible = await save_btn.is_visible()
        print(f'  保存按钮 visible: {is_visible}')
        await save_btn.click(force=True, timeout=5000)
        print('  ✅ 点击保存')
        await page.wait_for_timeout(5000)

        # 打印 POST 请求
        print('\n=== POST 请求 ===')
        for log in network_log:
            if log['method'] in ('POST', 'PUT', 'PATCH'):
                print(f'  {log["method"]} {log["url"]}')
                if log['post_data']:
                    d = log['post_data']
                    if len(d) > 250:
                        d = d[:250] + '...'
                    print(f'    data: {d}')

        print(f'\n  最终 URL: {page.url}')

        # 错误信息
        errs = await page.locator('.el-message--error, .el-form-item__error').all()
        for e in errs[:3]:
            t = await e.text_content()
            if t and t.strip():
                print(f'  错误: {t.strip()}')

        await browser.close()

asyncio.run(main())

#!/usr/bin/env python3
"""[BMRD 2026-06-14] 真实模拟用户手动 UI: TEST888122 + V10"""
import asyncio
import time
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

        # 1. dev-login
        await page.goto('http://localhost:3004/api/v1/auth/dev-login?username=admin')
        await page.wait_for_timeout(1000)

        # 2. 打开新建页
        print('=== 打开 /detail/product/new?mode=add ===')
        await page.goto('http://localhost:3004/detail/product/new?mode=add')
        await page.wait_for_timeout(5000)

        # 3. 检查 child sections
        child_count = await page.locator('[data-testid="odp-child-sections"]').count()
        print(f'  child sections 容器: {child_count}')

        # 4. 检查输入框
        inputs = await page.locator('input').count()
        print(f'  输入框数: {inputs}')

        # 5. 填主表单
        print('\n=== 填主表单 ===')
        # 通常 code 在第一个 input, name 在第二个
        all_inputs = await page.locator('input').all()
        for i, inp in enumerate(all_inputs[:5]):
            ph = await inp.get_attribute('placeholder')
            print(f'  input[{i}]: placeholder={ph}')

        # 填 code + name
        if inputs >= 2:
            await all_inputs[0].fill('TEST888122_BROWSER')
            await page.wait_for_timeout(300)
            await all_inputs[1].fill('TEST888122_BROWSER')
            print('  ✅ 填了 code + name')

        # 6. 检查子表 - 找 新增 按钮
        print('\n=== 检查子表 新增 按钮 ===')
        new_btns = await page.locator('[data-testid="odp-child-sections"] button:has-text("新增")').all()
        print(f'  新增按钮数: {len(new_btns)}')

        if new_btns:
            await new_btns[0].click()
            print('  ✅ 点击新增')
            await page.wait_for_timeout(2000)

            # 7. 找新行的 name input
            new_inputs = await page.locator('[data-testid="odp-child-sections"] input').all()
            print(f'  子表 input 数: {len(new_inputs)}')
            for i, inp in enumerate(new_inputs):
                ph = await inp.get_attribute('placeholder')
                v = await inp.input_value()
                print(f'    子 input[{i}]: placeholder={ph} value={v}')

            # 填 V10 name
            if len(new_inputs) >= 1:
                await new_inputs[0].fill('V10_BROWSER')
                print('  ✅ 填 V10 name')
                # 填 V10 value 字段
                if len(new_inputs) >= 2:
                    await new_inputs[1].fill('V10_BROWSER')
                    print('  ✅ 填 V10 value')
            await page.wait_for_timeout(1000)
        else:
            print('  ❌ 没有找到 新增 按钮')

        # 8. 找主表单 保存 按钮
        print('\n=== 点保存 ===')
        save_btns = await page.locator('button:has-text("保存")').all()
        print(f'  保存按钮数: {len(save_btns)}')
        for b in save_btns:
            text = await b.text_content()
            print(f'    button: {text}')

        # 找主表单最外层保存按钮
        # 通常 DetailPage 内部保存按钮
        if save_btns:
            await save_btns[0].click()
            print('  ✅ 点击保存')
            await page.wait_for_timeout(5000)

        # 9. 打印所有 API 请求
        print('\n=== API 请求 (POST/PUT/PATCH) ===')
        for log in network_log:
            if log['method'] in ('POST', 'PUT', 'PATCH'):
                print(f'  {log["method"]} {log["url"]}')
                if log['post_data']:
                    data = log['post_data']
                    if len(data) > 300:
                        data = data[:300] + '...'
                    print(f'    data: {data}')

        # 10. 当前 URL + 错误信息
        print(f'\n  最终 URL: {page.url}')

        # 11. 看页面是否有错误提示
        errors = await page.locator('.el-message--error, .el-notification--error, .el-form-item__error').all()
        for e in errors[:5]:
            t = await e.text_content()
            if t and t.strip():
                print(f'  错误提示: {t.strip()}')

        await browser.close()

asyncio.run(main())

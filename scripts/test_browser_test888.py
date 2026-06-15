#!/usr/bin/env python3
"""[BMRD 2026-06-14] 用 Playwright 真实模拟用户手动 UI 操作
看实际 endpoint + payload
"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # 可见, 让用户能看到
        context = await browser.new_context()
        page = await context.new_page()

        # 收集所有网络请求
        network_log = []

        async def on_request(request):
            if '/api/' in request.url:
                network_log.append({
                    'method': request.method,
                    'url': request.url,
                    'post_data': request.post_data,
                })

        page.on('request', on_request)

        # 1. 打开新建 product 页面
        print('=== 1. 打开 /detail/product/new?mode=add ===')
        await page.goto('http://localhost:3010/detail/product/new?mode=add')
        await page.wait_for_timeout(3000)

        # 2. 检查页面内容 - child sections 是否显示
        child_sections = await page.locator('[data-testid="odp-child-sections"]').count()
        print(f'  child sections 容器: {child_sections}')

        # 3. 检查所有表单字段
        inputs = await page.locator('input').count()
        print(f'  输入框数: {inputs}')

        # 4. 打印所有 button 文本
        buttons = await page.locator('button').all()
        for b in buttons:
            text = await b.text_content()
            if text and ('save' in text.lower() or '保存' in text or '取消' in text):
                print(f'  button: {text.strip()}')

        # 5. 截图
        await page.screenshot(path='d:/filework/excel-to-diagram/test-results/test888122-ui-1.png', full_page=True)
        print('  截图保存: test-results/test888122-ui-1.png')

        # 6. 尝试填表单
        print('\n=== 2. 填表单 (模拟用户操作) ===')
        # 找 code 字段
        code_input = page.locator('input').first
        if await code_input.count():
            await code_input.fill('TEST888122_BROWSER')

        name_input = page.locator('input').nth(1)
        if await name_input.count():
            await name_input.fill('TEST888122_BROWSER')

        # 找子表
        print('\n=== 3. 检查 child section ===')
        # 找 "新增" 按钮
        add_btns = page.locator('button:has-text("新增")')
        add_count = await add_btns.count()
        print(f'  新增按钮数: {add_count}')

        # 找版本名输入
        if add_count > 0:
            await add_btns.first.click()
            await page.wait_for_timeout(1500)
            # 找新行的 name 输入
            ver_name = page.locator('input[placeholder*="名称"], input[placeholder*="name"]').last()
            if await ver_name.count():
                await ver_name.fill('V10')
            await page.screenshot(path='d:/filework/excel-to-diagram/test-results/test888122-ui-2.png', full_page=True)
            print('  截图保存: test-results/test888122-ui-2.png (添加 V10 后)')

        # 7. 点保存
        print('\n=== 4. 点保存 ===')
        save_btn = page.locator('button:has-text("保存"), button:has-text("Save")').first
        if await save_btn.count():
            await save_btn.click()
            await page.wait_for_timeout(3000)
        await page.screenshot(path='d:/filework/excel-to-diagram/test-results/test888122-ui-3.png', full_page=True)
        print('  截图保存: test-results/test888122-ui-3.png (保存后)')

        # 8. 打印所有 API 请求
        print('\n=== 5. 所有 API 请求 ===')
        for log in network_log:
            if log['method'] in ('POST', 'PUT', 'PATCH'):
                print(f'  {log["method"]} {log["url"]}')
                if log['post_data']:
                    data = log['post_data']
                    if len(data) > 200:
                        data = data[:200] + '...'
                    print(f'    data: {data}')

        await browser.close()

asyncio.run(main())

#!/usr/bin/env python3
"""复现: add 模式下 TEST888888 + V10 deep_insert"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 监听 console
        page.on('console', lambda msg: print(f'  [console.{msg.type}] {msg.text}') 
                if 'BUG-V007' in msg.text or 'Deep insert' in msg.text or 'deep_insert' in msg.text.lower()
                or 'error' in msg.text.lower() or 'Error' in msg.text else None)

        network_log = []
        page.on('request', lambda req: network_log.append({
            'method': req.method, 'url': req.url, 'post_data': req.post_data,
        }) if '/api/' in req.url else None)

        response_log = []
        page.on('response', lambda res: response_log.append({
            'status': res.status, 'url': res.url,
        }) if '/api/v2/bo/' in res.url or 'deep_insert' in res.url else None)

        # 1. 登录 admin
        await page.goto('http://localhost:3004/api/v1/auth/dev-login?username=admin')
        await page.wait_for_timeout(1000)

        # 2. 访问 add 页面
        print('=== 访问 /detail/product?mode=add ===')
        await page.goto('http://localhost:3004/detail/product?mode=add')
        await page.wait_for_timeout(3000)

        # 3. 截图看页面状态
        await page.screenshot(path='d:/filework/excel-to-diagram/scripts/add_page_loaded.png', full_page=True)
        print('  截图: add_page_loaded.png')

        # 4. 检查 inline draft 区
        inline_draft = await page.locator('[data-testid="ocs-inline-draft"]').count()
        print(f'  inline draft 区数: {inline_draft}')

        # 5. 填写产品名称和编码
        print('\n=== 填写产品信息 ===')
        # 找到 name 输入框
        name_inputs = page.locator('input')
        count = await name_inputs.count()
        print(f'  input 总数: {count}')
        
        # 尝试找到第一个可见的 text input
        for i in range(min(count, 20)):
            inp = name_inputs.nth(i)
            is_vis = await inp.is_visible()
            if is_vis:
                placeholder = await inp.get_attribute('placeholder') or ''
                input_type = await inp.get_attribute('type') or ''
                print(f'  input[{i}]: visible, placeholder="{placeholder}", type="{input_type}"')

        # 填写 name 字段
        name_input = page.locator('input[placeholder*="name"], input[placeholder*="名称"], input[placeholder*="产品"]').first
        if await name_input.count() > 0:
            await name_input.fill('TEST888888')
            print('  ✅ 填产品名称')
        else:
            # 直接用第一个可见 input
            for i in range(min(count, 10)):
                inp = name_inputs.nth(i)
                if await inp.is_visible():
                    await inp.fill('TEST888888')
                    print(f'  ✅ 填 input[{i}] = TEST888888')
                    break

        # 填写 code 字段（产品编码）
        code_input = page.locator('input[placeholder*="code"], input[placeholder*="编码"], input[placeholder*="产品编码"]').first
        if await code_input.count() > 0:
            await code_input.fill('TEST888888')
            print('  ✅ 填产品编码')
        else:
            # 找第二个可见 input
            filled = False
            for i in range(min(count, 10)):
                inp = name_inputs.nth(i)
                if await inp.is_visible():
                    val = await inp.input_value()
                    if not val:  # 还没填的
                        await inp.fill('TEST888888')
                        print(f'  ✅ 填 input[{i}] = TEST888888 (code)')
                        filled = True
                        break
            if not filled:
                print('  ⚠️ 未找到 code 输入框')

        # 6. 检查 inline draft 区并添加版本
        print('\n=== 添加版本 V10 ===')
        add_btn = page.locator('[data-testid="ocs-inline-draft-add"]').first
        is_vis = await add_btn.is_visible()
        print(f'  添加按钮 visible: {is_vis}')
        
        if is_vis:
            await add_btn.click(force=True, timeout=5000)
            print('  ✅ 点击添加')
            await page.wait_for_timeout(500)

            name_input = page.locator('[data-testid="ocs-draft-name-0"]').first
            if await name_input.count():
                await name_input.fill('V10')
                print('  ✅ 填 V10 name')
            value_input = page.locator('[data-testid="ocs-draft-value-0"]').first
            if await value_input.count():
                await value_input.fill('10')
                print('  ✅ 填 V10 value')

        # 7. 截图
        await page.screenshot(path='d:/filework/excel-to-diagram/scripts/add_page_filled.png', full_page=True)
        print('  截图: add_page_filled.png')

        # 8. 点保存
        print('\n=== 点击保存 ===')
        # 找保存按钮
        save_btns = page.locator('button:has-text("保存"), button:has-text("Save")')
        save_count = await save_btns.count()
        print(f'  保存按钮数: {save_count}')
        for i in range(save_count):
            btn = save_btns.nth(i)
            is_vis = await btn.is_visible()
            text = await btn.text_content()
            print(f'  保存按钮[{i}]: visible={is_vis}, text="{text}"')
        
        if save_count > 0:
            # 点第一个可见的保存按钮
            for i in range(save_count):
                btn = save_btns.nth(i)
                if await btn.is_visible():
                    await btn.click(force=True, timeout=5000)
                    print(f'  ✅ 点击保存按钮[{i}]')
                    break
            await page.wait_for_timeout(5000)

        # 9. 截图
        await page.screenshot(path='d:/filework/excel-to-diagram/scripts/add_page_saved.png', full_page=True)
        print('  截图: add_page_saved.png')

        # 10. 打印所有请求
        print('\n=== 所有 API 请求 ===')
        for log in network_log:
            d = log['post_data'] or ''
            if len(d) > 500:
                d = d[:500] + '...'
            print(f'  {log["method"]} {log["url"]}')
            if d:
                print(f'    body: {d}')

        print('\n=== 所有响应 ===')
        for log in response_log:
            print(f'  {log["status"]} {log["url"]}')

        # 11. 检查后端
        print('\n=== 验证后端 ===')
        import urllib.request, http.cookiejar, json
        cj = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        op.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')
        r = op.open('http://localhost:3010/api/v2/bo/product?name=TEST888888')
        products = json.loads(r.read().decode())['data']['items']
        print(f'  TEST888888: {len(products)} found')
        for p in products:
            pid = p['id']
            r2 = op.open(f'http://localhost:3010/api/v2/bo/version?product_id={pid}&page_size=20')
            versions = json.loads(r2.read().decode())['data']['items']
            print(f'    id={pid} versions={len(versions)}')
            for v in versions:
                print(f'      - id={v["id"]} name={v["name"]}')

        await browser.close()

asyncio.run(main())

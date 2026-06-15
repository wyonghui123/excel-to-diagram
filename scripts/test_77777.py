#!/usr/bin/env python3
"""复现: TEST77777_NEW + V10 (用新名字避免重复创建)"""
import asyncio
from playwright.async_api import async_playwright

TEST_NAME = 'TEST77777_NEW'

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 监听 console
        page.on('console', lambda msg: print(f'  [console.{msg.type}] {msg.text}')
                if 'BUG-V007' in msg.text or 'Deep insert' in msg.text or 'error' in msg.text.lower() else None)

        network_log = []
        page.on('request', lambda req: network_log.append({
            'method': req.method, 'url': req.url, 'post_data': req.post_data,
        }) if '/api/v2/bo/' in req.url and 'deep' in req.url else None)

        # 1. 登录 admin
        await page.goto('http://localhost:3004/api/v1/auth/dev-login?username=admin')
        await page.wait_for_timeout(1000)

        # 2. 访问 add 页面
        print(f'=== 访问 /detail/product?mode=add (测试 {TEST_NAME}) ===')
        await page.goto('http://localhost:3004/detail/product?mode=add')
        await page.wait_for_timeout(3000)

        # 3. 填写产品名称和编码
        print(f'\n=== 填写 {TEST_NAME} ===')
        name_input = page.locator('input[placeholder*="名称"]').first
        await name_input.fill(TEST_NAME)
        print(f'  ✅ 填产品名称 = {TEST_NAME}')

        code_input = page.locator('input[placeholder*="编码"]').first
        await code_input.fill(TEST_NAME)
        print(f'  ✅ 填产品编码 = {TEST_NAME}')

        # 4. 添加版本 V10
        print('\n=== 添加版本 V10 ===')
        add_btn = page.locator('[data-testid="ocs-inline-draft-add"]').first
        await add_btn.click(force=True, timeout=5000)
        print('  ✅ 点击添加')

        name_input = page.locator('[data-testid="ocs-draft-name-0"]').first
        await name_input.fill('V10')
        print('  ✅ 填 V10 name')

        value_input = page.locator('[data-testid="ocs-draft-value-0"]').first
        await value_input.fill('10')
        print('  ✅ 填 V10 value')

        await page.wait_for_timeout(500)

        # 5. 点保存
        print('\n=== 点击保存 ===')
        save_btn = page.locator('button:has-text("保存")').first
        await save_btn.click(force=True, timeout=5000)
        print('  ✅ 点击保存')
        await page.wait_for_timeout(5000)

        # 6. 打印所有请求
        print('\n=== Deep Insert 请求 ===')
        for log in network_log:
            print(f'  {log["method"]} {log["url"]}')
            print(f'    body: {log["post_data"]}')

        # 7. 检查后端
        print(f'\n=== 验证后端 ({TEST_NAME}) ===')
        import urllib.request, http.cookiejar, json
        cj = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
        op.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')
        r = op.open(f'http://localhost:3010/api/v2/bo/product?name={TEST_NAME}')
        products = json.loads(r.read().decode())['data']['items']
        print(f'  {TEST_NAME}: {len(products)} found')
        for p in products:
            pid = p['id']
            r2 = op.open(f'http://localhost:3010/api/v2/bo/version?product_id={pid}&page_size=20')
            versions = json.loads(r2.read().decode())['data']['items']
            print(f'    id={pid} versions={len(versions)}')
            for v in versions:
                print(f'      - id={v["id"]} name={v["name"]}')

        await browser.close()

asyncio.run(main())

#!/usr/bin/env python3
"""[BMRD 2026-06-14] 用 Vite 端口 3004 测 UI 真实行为"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        network_log = []
        page.on('request', lambda req: network_log.append(f'{req.method} {req.url}') if '/api/' in req.url or '/detail' in req.url else None)
        page.on('console', lambda msg: print(f'  [console.{msg.type}] {msg.text}'))

        # 1. dev-login
        await page.goto('http://localhost:3004/api/v1/auth/dev-login?username=admin')
        await page.wait_for_timeout(1000)

        # 2. 试 /detail/product/new?mode=add (走 Vite 3004)
        print('=== A. http://localhost:3004/detail/product/new?mode=add ===')
        await page.goto('http://localhost:3004/detail/product/new?mode=add')
        await page.wait_for_timeout(5000)
        print('  最终 URL:', page.url)
        print('  标题:', await page.title())

        body_text = await page.locator('body').text_content()
        print('  body 前 200 字:', body_text[:200] if body_text else '(空)')

        child_count = await page.locator('[data-testid="odp-child-sections"]').count()
        print(f'  child sections: {child_count}')

        inputs = await page.locator('input').count()
        print(f'  输入框数: {inputs}')

        # 3. 看所有按钮
        buttons = await page.locator('button').all()
        btn_texts = []
        for b in buttons[:20]:
            t = await b.text_content()
            if t and t.strip():
                btn_texts.append(t.strip())
        print(f'  按钮: {btn_texts}')

        # 4. 网络请求
        print('\n=== 网络请求 ===')
        for log in network_log[:20]:
            print(f'  {log}')

        await browser.close()

asyncio.run(main())

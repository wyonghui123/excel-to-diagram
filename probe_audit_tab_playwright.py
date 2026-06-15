"""
用 Playwright 实际访问 domain 详情页, 验证操作日志 tab 是否能加载日志
"""
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        # 收集网络请求
        api_calls = []
        page.on('request', lambda req: api_calls.append((req.method, req.url, req.headers.get('Authorization', ''))) if '/audit/logs' in req.url or '/api/v1/auth/login' in req.url else None)

        # 1. 登录
        print('1. Login...')
        await page.goto('http://localhost:3004/login')
        await page.wait_for_load_state('domcontentloaded')
        await page.wait_for_timeout(1000)
        # 看登录页元素
        username = page.locator('input[placeholder*="用户名"], input[type="text"]').first
        password = page.locator('input[type="password"]').first
        await username.fill('admin')
        await password.fill('admin123')
        # 找登录按钮
        login_btn = page.locator('button:has-text("登录"), button:has-text("Login"), button[type="submit"]').first
        await login_btn.click()
        await page.wait_for_load_state('domcontentloaded')
        await page.wait_for_timeout(2000)
        print(f'   Current URL: {page.url}')

        # 2. 访问 domain 详情页 (假设路径是 /system/archdata/domain/683)
        print('2. Navigate to domain detail...')
        for url in [
            'http://localhost:3004/system/archdata/domain/683',
            'http://localhost:3004/data-domain/683',
            'http://localhost:3004/admin/domain/683',
            'http://localhost:3004/domains/683',
        ]:
            print(f'   try: {url}')
            await page.goto(url)
            await page.wait_for_load_state('domcontentloaded')
            await page.wait_for_timeout(1500)
            title = await page.title()
            print(f'   title: {title}, url: {page.url}')
            # 找"操作日志" tab
            audit_tab = page.locator('text=操作日志, text=变更历史, text=历史').first
            if await audit_tab.count() > 0:
                print(f'   found audit tab, click')
                await audit_tab.click()
                await page.wait_for_timeout(2000)
                # 看是否有日志条目
                log_items = page.locator('.op-audit-log-section, [class*="audit-log"]')
                print(f'   log section count: {await log_items.count()}')
                break

        # 截图
        await page.screenshot(path='audit_tab_debug.png', full_page=True)
        print('Screenshot saved: audit_tab_debug.png')

        # 看 API 调用
        print(f'\n=== API calls captured ({len(api_calls)}) ===')
        for m, u, h in api_calls[:20]:
            print(f'  {m} {u}  auth={h[:30] if h else "none"}')

        await browser.close()

asyncio.run(main())

"""
业务人员视角: 用 Playwright 走查 4 个详情页的 audit log tab, 截图
"""
import asyncio
import requests
from playwright.async_api import async_playwright

async def main():
    base = 'http://localhost:3010'
    r = requests.get(f'{base}/api/v1/auth/dev-login?username=admin', timeout=5)
    cookies = dict(r.cookies)

    cases = [
        ('detail/domain/683', 'domain_683_bizview.png', '领域 683'),
        ('detail/sub_domain/68', 'sub_domain_68_bizview.png', '子领域 68'),
        ('detail/relationship/35', 'relationship_35_bizview.png', '关系 35'),
        ('detail/user/1', 'user_1_bizview.png', '用户 1 (admin)'),
    ]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        for name, value in cookies.items():
            await context.add_cookies([{
                'name': name, 'value': value,
                'domain': 'localhost', 'path': '/',
                'httpOnly': True, 'secure': False
            }])

        for path, png, label in cases:
            page = await context.new_page()
            url = f'http://localhost:3004/{path}'
            print(f'\n=== {label}: {url} ===')
            await page.goto(url, timeout=15000)
            await page.wait_for_load_state('domcontentloaded', timeout=5000)
            await page.wait_for_timeout(2500)

            # 点击"操作日志" tab
            for tab_text in ['操作日志', '变更历史']:
                tab = page.locator(f'text={tab_text}').first
                if await tab.count() > 0:
                    await tab.click()
                    await page.wait_for_timeout(2500)
                    break

            await page.screenshot(path=png, full_page=True)
            print(f'  截图: {png}')

            # 列出/审计/弹窗内容
            section = page.locator('.op-audit-log-section').first
            if await section.count() > 0:
                text = await section.text_content()
                print(f'  audit log 内容[:600]:')
                print(f'    {text[:600]!r}')

                # 尝试点击第一条日志看弹窗
                item = page.locator('.al-item').first
                if await item.count() > 0:
                    await item.click()
                    await page.wait_for_timeout(1500)
                    drawer = page.locator('.el-drawer').first
                    if await drawer.count() > 0:
                        drawer_text = await drawer.text_content()
                        print(f'  [详情弹窗]:')
                        print(f'    {drawer_text[:1000]!r}')
                        await page.screenshot(path=png.replace('.png', '_detail.png'), full_page=True)
                        # 关闭弹窗
                        close_btn = page.locator('.el-drawer__close-btn').first
                        if await close_btn.count() > 0:
                            await close_btn.click()
                            await page.wait_for_timeout(500)
            await page.close()

        await browser.close()

asyncio.run(main())

"""
业务化修复验证: 走查 4 个详情页, 检查修复后是否无 IP/Trace/对象ID
+ object_type 是否翻译 + _record 是否隐藏 + "未知" 是否消失
"""
import asyncio
import requests
from playwright.async_api import async_playwright

async def main():
    base = 'http://localhost:3010'
    r = requests.get(f'{base}/api/v1/auth/dev-login?username=admin', timeout=5)
    cookies = dict(r.cookies)

    cases = [
        ('detail/domain/683', 'verify_domain_683.png', '领域 683'),
        ('detail/sub_domain/68', 'verify_sub_domain_68.png', '子领域 68'),
        ('detail/relationship/35', 'verify_relationship_35.png', '关系 35'),
        ('detail/user/1', 'verify_user_1.png', '用户 1 (admin)'),
        ('detail/user_group/8217', 'verify_user_group_8217.png', '用户组 8217'),
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
            await page.goto(url, timeout=20000, wait_until='domcontentloaded')
            await page.wait_for_timeout(3000)

            for tab_text in ['操作日志', '变更历史']:
                tab = page.locator(f'text={tab_text}').first
                if await tab.count() > 0:
                    await tab.click()
                    await page.wait_for_timeout(2500)
                    break

            await page.screenshot(path=png, full_page=True)
            print(f'  列表截图: {png}')

            section = page.locator('.op-audit-log-section').first
            if await section.count() > 0:
                text = await section.text_content()
                # 业务化检查
                issues = []
                if 'IP' in text and '操作人' in text:
                    pass  # IP 只在详情弹窗, 列表无
                if '127.0.0.1' in text:
                    issues.append('列表有 IP')
                if '_record' in text:
                    issues.append('列表有 _record 字段')
                if '未知' in text:
                    issues.append('列表有"未知"')
                if not issues:
                    print('  [OK] 列表业务化检查通过')
                else:
                    print(f'  [ISSUE] {issues}')

                # 点击第一条日志
                item = page.locator('.al-item').first
                if await item.count() > 0:
                    await item.click(force=True)
                    await page.wait_for_timeout(1500)
                    drawer = page.locator('.el-drawer').first
                    if await drawer.count() > 0:
                        drawer_text = await drawer.text_content()
                        issues_d = []
                        if 'IP' in drawer_text:
                            issues_d.append('详情有 IP 字段')
                        if 'Trace' in drawer_text and len(drawer_text) > 200:
                            issues_d.append('详情有 Trace 字段')
                        if '对象ID' in drawer_text:
                            issues_d.append('详情有对象ID 字段')
                        if 'annotation' in drawer_text and '对象类型' in drawer_text:
                            issues_d.append('详情 object_type 未翻译')
                        if 'sub_domain' in drawer_text and '对象类型' in drawer_text:
                            issues_d.append('详情 object_type 未翻译')
                        if 'relationship' in drawer_text and '对象类型' in drawer_text:
                            issues_d.append('详情 object_type 未翻译')
                        if 'user_group' in drawer_text and '对象类型' in drawer_text:
                            issues_d.append('详情 object_type 未翻译')
                        if issues_d:
                            print(f'  [ISSUE] 详情弹窗: {issues_d}')
                        else:
                            print(f'  [OK] 详情弹窗业务化检查通过')
                        print(f'  [详情内容]: {drawer_text[:400]!r}')
                        await page.screenshot(path=png.replace('.png', '_detail.png'), full_page=True)
                        close_btn = page.locator('.el-drawer__close-btn').first
                        if await close_btn.count() > 0:
                            await close_btn.click()
                            await page.wait_for_timeout(500)
            await page.close()

        await browser.close()

asyncio.run(main())

"""
简化的 E2E 测试：验证角色权限配置页面
"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth import authenticated_page
import asyncio


async def main():
    print("=" * 70)
    print("简化测试：角色权限配置页面的管理维度范围")
    print("=" * 70)

    screenshot_path = 'd:/filework/excel-to-diagram/test_dim_scope.png'

    # 1. 打开浏览器并导航
    print("\n[1] 打开浏览器，导航到角色列表页...")
    async with authenticated_page(target_url='/user-permission/roles') as page:
        await page.wait_for_load_state('domcontentloaded')
        await page.wait_for_timeout(3000)  # 等待渲染

        # 获取当前 URL
        url = page.url
        print(f"    当前 URL: {url}")

        # 获取页面标题
        title = await page.title()
        print(f"    页面标题: {title}")

        # 截图
        await page.screenshot(path='d:/filework/excel-to-diagram/step1_roles_list.png', full_page=True)
        print(f"    [OK] 截图保存: step1_roles_list.png")

        # 2. 获取页面内容摘要
        print("\n[2] 分析页面内容...")
        content = await page.evaluate("""
            () => {
                const body = document.body;
                const text = body.innerText || '';
                const tables = document.querySelectorAll('table, .el-table');
                const rows = [];
                tables.forEach(t => {
                    const trs = t.querySelectorAll('tr, .el-table__row');
                    trs.forEach(tr => {
                        const cells = tr.querySelectorAll('td, th, .el-table__cell');
                        const rowText = Array.from(cells).map(c => c.innerText.trim()).join(' | ');
                        if (rowText) rows.push(rowText);
                    });
                });
                return {
                    textLength: text.length,
                    hasRoles: text.includes('角色'),
                    has1397: text.includes('1397'),
                    tables: tables.length,
                    rows: rows.slice(0, 20)
                };
            }
        """)
        print(f"    文本长度: {content['textLength']}")
        print(f"    包含'角色': {content['hasRoles']}")
        print(f"    包含'1397': {content['has1397']}")
        print(f"    表格数量: {content['tables']}")

        if content['rows']:
            print(f"    表格内容 (前5行):")
            for i, row in enumerate(content['rows'][:5]):
                print(f"      {i+1}. {row[:100]}")

        # 3. 直接导航到角色详情
        print("\n[3] 导航到角色详情页 /role/1397...")
        await page.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router;
                router.push('/role/1397');
            }
        """)
        await page.wait_for_timeout(3000)

        url2 = page.url
        print(f"    当前 URL: {url2}")

        await page.screenshot(path='d:/filework/excel-to-diagram/step2_role_detail.png', full_page=True)
        print(f"    [OK] 截图保存: step2_role_detail.png")

        # 分析详情页
        detail = await page.evaluate("""
            () => {
                const body = document.body;
                const text = body.innerText || '';
                return {
                    textLength: text.length,
                    text: text.slice(0, 2000)
                };
            }
        """)
        print(f"    详情页文本长度: {detail['textLength']}")
        print(f"    详情页内容预览:")
        print(detail['text'][:1000])

        # 4. 尝试 /system/role-permission/1397
        print("\n[4] 导航到权限配置页 /system/role-permission/1397...")
        await page.evaluate("""
            () => {
                const router = document.querySelector('#app').__vue_app__
                    .config.globalProperties.$router;
                router.push('/system/role-permission/1397');
            }
        """)
        await page.wait_for_timeout(3000)

        url3 = page.url
        print(f"    当前 URL: {url3}")

        await page.screenshot(path='d:/filework/excel-to-diagram/step3_permission.png', full_page=True)
        print(f"    [OK] 截图保存: step3_permission.png")

        perm = await page.evaluate("""
            () => {
                const body = document.body;
                const text = body.innerText || '';
                return {
                    textLength: text.length,
                    text: text.slice(0, 3000)
                };
            }
        """)
        print(f"    权限页文本长度: {perm['textLength']}")

        # 关键词检查
        keywords = ['维度', 'dimension', 'scope', '版本', 'version', 'v1.0', 'V1.0', '权限', 'permission']
        print("\n    关键词检查:")
        for kw in keywords:
            found = kw.lower() in perm['text'].lower()
            status = "[OK]" if found else "[X]"
            print(f"      - '{kw}': {status}")

        # 5. 保存最终截图
        print(f"\n[5] 保存最终截图到: {screenshot_path}")
        await page.screenshot(path=screenshot_path, full_page=True)

    print("\n" + "=" * 70)
    print("测试完成!")
    print("=" * 70)


if __name__ == '__main__':
    asyncio.run(main())

import asyncio
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth import authenticated_page

async def test():
    async with authenticated_page(headless=False) as page:
        await asyncio.sleep(2)

        logs = []
        def handle_console(msg):
            logs.append(f"[{msg.type}] {msg.text}")
        page.on('console', handle_console)

        await page.goto('http://localhost:3004/system/role-detail/1397')
        await asyncio.sleep(15)

        perm_tab = page.locator('.anchor-tab:has-text("权限配置"), .el-tabs__item:has-text("权限配置")').first
        if await perm_tab.count() > 0:
            await perm_tab.click()
            await asyncio.sleep(5)

        # Query DOM
        result = await page.evaluate("""
            () => {
                const rows = document.querySelectorAll('.dimension-row');
                return Array.from(rows).map(r => ({
                    label: r.querySelector('.dimension-label')?.textContent,
                    tags: Array.from(r.querySelectorAll('.el-tag')).map(t => t.textContent.trim())
                }));
            }
        """)

        print("Dimension rows:")
        for item in result:
            print(f"  '{item['label']}': tags={item['tags']}")

        # Version check
        for item in result:
            if item['label'] and '版本' in item['label']:
                if any('v1' in t.lower() for t in item['tags']):
                    print("\n[DECORATIVE] SUCCESS: v1.0 displayed!")
                else:
                    print(f"\n[DECORATIVE] FAIL: Version tags: {item['tags']}")

        # Print Dim logs
        dim_logs = [l for l in logs if '[Dim]' in l]
        print(f"\n[Dim] logs ({len(dim_logs)}):")
        for l in dim_logs:
            print(f"  {l[:200]}")

asyncio.run(test())

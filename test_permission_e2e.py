import asyncio
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth import authenticated_page

async def test():
    async with authenticated_page(headless=False) as page:
        await asyncio.sleep(2)

        await page.goto('http://localhost:3004/system/role-detail/1397')
        await asyncio.sleep(15)

        # Click on 权限配置 tab
        perm_tab = page.locator('.el-tabs__item:has-text("权限配置")')
        if await perm_tab.count() > 0:
            await perm_tab.click()
            await asyncio.sleep(5)
            print("Clicked 权限配置 tab")

        # Check for any tree-like structures
        trees = await page.locator('.el-tree, .perm-tree, [class*="tree"]').all()
        print(f"Found {len(trees)} tree elements")

        # Check for permission-related classes
        perm_elements = await page.locator('[class*="perm"], [class*="menu"]').all()
        print(f"Found {len(perm_elements)} perm/menu elements")

        # Look for arch-data node with various selectors
        selectors = [
            'text=架构数据管理',
            '.node-label:has-text("架构数据管理")',
            '[data-v-*]:has-text("架构数据管理")',
            'span:has-text("架构数据管理")'
        ]

        for sel in selectors:
            try:
                elements = await page.locator(sel).all()
                print(f"Selector '{sel}': {len(elements)} elements")
                for el in elements[:3]:
                    visible = await el.is_visible()
                    if visible:
                        text = await el.text_content()
                        print(f"  Visible: {text[:50]}")
            except Exception as e:
                print(f"Selector '{sel}': error - {e}")

        # Get all visible text to understand structure
        visible_text = await page.evaluate("""
            () => {
                const walker = document.createTreeWalker(
                    document.body,
                    NodeFilter.SHOW_ELEMENT,
                    {
                        acceptNode: (node) => {
                            const style = window.getComputedStyle(node);
                            return style.display !== 'none' && style.visibility !== 'hidden' ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
                        }
                    }
                );
                const texts = [];
                let node;
                while (node = walker.nextNode()) {
                    if (node.textContent.trim() && node.textContent.trim().length < 100) {
                        texts.push(node.textContent.trim());
                    }
                }
                return texts.filter(t => t.includes('架构') || t.includes('domain')).slice(0, 20);
            }
        """)
        print(f"Visible text with '架构' or 'domain': {visible_text}")

asyncio.run(test())

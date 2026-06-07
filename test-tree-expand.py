import asyncio
from playwright.async_api import async_playwright

async def test_tree_expand():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        try:
            print("访问首页...")
            await page.goto("http://localhost:3004/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)
            
            print("登录...")
            await page.fill('input[type="text"], input[name="username"], input[name="account"]', 'admin')
            await page.fill('input[type="password"]', 'admin123')
            await page.click('button[type="submit"]')
            await asyncio.sleep(5)
            
            print("导航到关系管理页面...")
            await page.goto("http://localhost:3004/system/relationships", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)
            
            # 选择产品
            print("选择产品...")
            product_selectors = await page.query_selector_all('.el-select')
            if product_selectors:
                await product_selectors[0].click()
                await asyncio.sleep(1)
                options = await page.query_selector_all('.el-select-dropdown__item')
                if len(options) > 0:
                    await options[0].click()
                    await asyncio.sleep(3)
            
            # 选择版本
            print("选择版本...")
            version_selectors = await page.query_selector_all('.el-select')
            if len(version_selectors) > 1:
                await version_selectors[1].click()
                await asyncio.sleep(1)
                await page.keyboard.press('ArrowDown')
                await asyncio.sleep(0.5)
                await page.keyboard.press('Enter')
                await asyncio.sleep(5)
            
            # 获取树节点
            tree_nodes = await page.query_selector_all('.el-tree-node')
            print(f"\n初始树节点数: {len(tree_nodes)}")
            
            if tree_nodes:
                # 打印前几个节点
                print("顶级节点:")
                for i, node in enumerate(tree_nodes[:5]):
                    label = await node.query_selector('.el-tree-node__label')
                    has_expand = await node.query_selector('.el-tree-node__expand-icon:not(.is-leaf)')
                    if label:
                        text = await label.text_content()
                        expandable = " [可展开]" if has_expand else ""
                        print(f"  {i+1}. {text.strip()}{expandable}")
                
                # 展开第一个可展开的节点
                expand_icons = await page.query_selector_all('.el-tree-node__expand-icon:not(.is-leaf)')
                print(f"\n可展开节点数: {len(expand_icons)}")
                
                if len(expand_icons) > 0:
                    print("展开第一个可展开节点...")
                    await expand_icons[0].click()
                    await asyncio.sleep(2)
                    
                    # 再次获取树节点
                    tree_nodes_after = await page.query_selector_all('.el-tree-node')
                    print(f"\n展开后树节点数: {len(tree_nodes_after)}")
                    
                    # 打印子节点（跳过顶级）
                    print("新出现的子节点:")
                    for i, node in enumerate(tree_nodes_after[len(tree_nodes):][:5]):
                        label = await node.query_selector('.el-tree-node__label')
                        if label:
                            text = await label.text_content()
                            print(f"  {i+1}. {text.strip()}")
                    
                    # 继续展开子节点
                    expand_icons2 = await page.query_selector_all('.el-tree-node__expand-icon:not(.is-leaf)')
                    print(f"\n可展开节点数: {len(expand_icons2)}")
                    
                    if len(expand_icons2) > 1:
                        print("展开第二个可展开节点（子级）...")
                        await expand_icons2[1].click()
                        await asyncio.sleep(2)
                        
                        tree_nodes_3 = await page.query_selector_all('.el-tree-node')
                        print(f"再展开后树节点数: {len(tree_nodes_3)}")
                        
                        print("新出现的节点:")
                        for i, node in enumerate(tree_nodes_3[len(tree_nodes_after):][:5]):
                            label = await node.query_selector('.el-tree-node__label')
                            if label:
                                text = await label.text_content()
                                print(f"  {i+1}. {text.strip()}")
            
            await page.screenshot(path='tree_expand.png', full_page=True)
            print("\n截图已保存到 tree_expand.png")
            
        except Exception as e:
            print(f"测试异常: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path='test_error.png')
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tree_expand())

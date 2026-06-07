import asyncio
from playwright.async_api import async_playwright

async def test_tree_final():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        try:
            print("访问首页...")
            await page.goto("http://localhost:3005/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            
            # 登录
            print("登录...")
            await page.fill('input[type="text"], input[name="username"], input[name="account"]', 'admin')
            await page.fill('input[type="password"]', 'admin123')
            await page.click('button[type="submit"]')
            await asyncio.sleep(3)
            
            # 导航到关系管理页面
            print("导航到关系管理页面...")
            await page.goto("http://localhost:3005/system/relationships", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            
            # 选择产品
            print("选择产品...")
            product_selectors = await page.query_selector_all('.el-select')
            if product_selectors:
                await product_selectors[0].click()
                await asyncio.sleep(1)
                options = await page.query_selector_all('.el-select-dropdown__item')
                print(f"产品选项数量: {len(options)}")
                if len(options) > 0:
                    await options[0].click()
                    await asyncio.sleep(2)
            
            # 选择版本 - 使用键盘操作
            print("选择版本...")
            version_selectors = await page.query_selector_all('.el-select')
            if len(version_selectors) > 1:
                # 点击版本选择器
                await version_selectors[1].click()
                await asyncio.sleep(1)
                
                # 按 Enter 键选择第一个选项
                await page.keyboard.press('Enter')
                await asyncio.sleep(3)
            
            # 检查树组件
            print("\n检查树组件...")
            
            # 等待树加载
            try:
                await page.wait_for_selector('.el-tree-node', timeout=10000)
            except:
                print("等待树节点超时")
            
            # 获取树节点
            tree_nodes = await page.query_selector_all('.el-tree-node')
            print(f"找到 {len(tree_nodes)} 个 el-tree-node 元素")
            
            # 获取第一个节点的文本
            for i, node in enumerate(tree_nodes[:3]):
                label = await node.query_selector('.el-tree-node__label')
                if label:
                    text = await label.text_content()
                    print(f"  节点 {i+1}: {text.strip()}")
            
            # 展开第一个节点
            if tree_nodes:
                print("\n尝试展开第一个节点...")
                expand_icon = await tree_nodes[0].query_selector('.el-tree-node__expand-icon')
                if expand_icon:
                    await expand_icon.click()
                    await asyncio.sleep(2)
                    
                    # 再次获取节点
                    tree_nodes_after = await page.query_selector_all('.el-tree-node')
                    print(f"展开后节点数量: {len(tree_nodes_after)}")
                    
                    # 获取子节点
                    for i, node in enumerate(tree_nodes_after[1:6]):
                        label = await node.query_selector('.el-tree-node__label')
                        if label:
                            text = await label.text_content()
                            print(f"  子节点 {i+1}: {text.strip()}")
            
            # 截图
            await page.screenshot(path='tree-result.png', full_page=True)
            print("\n截图已保存到 tree-result.png")
            
        except Exception as e:
            print(f"测试异常: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path='tree-error.png')
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tree_final())

import asyncio
from playwright.async_api import async_playwright

async def test_tree_debug():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # 监听网络请求
        api_calls = []
        page.on("response", lambda response: api_calls.append({
            'url': response.url,
            'status': response.status,
            'ok': response.ok
        }) if '/api/' in response.url else None)
        
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
            await page.goto("http://localhost:3005/system/relationships", wait_until="networkidle", timeout=15000)
            await asyncio.sleep(3)
            
            # 选择产品
            print("选择产品...")
            product_selectors = await page.query_selector_all('.el-select')
            if product_selectors:
                await product_selectors[0].click()
                await asyncio.sleep(1)
                options = await page.query_selector_all('.el-select-dropdown__item')
                if len(options) > 0:
                    await options[0].click()
                    await asyncio.sleep(2)
            
            # 选择版本
            print("选择版本...")
            version_selectors = await page.query_selector_all('.el-select')
            if len(version_selectors) > 1:
                await version_selectors[1].click()
                await asyncio.sleep(1)
                version_options = await page.query_selector_all('.el-select-dropdown__item')
                if len(version_options) > 0:
                    await version_options[0].click()
                    await asyncio.sleep(3)
            
            # 获取树节点
            print("获取树节点...")
            tree_nodes = await page.query_selector_all('.el-tree-node')
            print(f"找到 {len(tree_nodes)} 个树节点")
            
            # 获取第一个节点的文本
            if len(tree_nodes) > 0:
                for i, node in enumerate(tree_nodes[:5]):
                    label = await node.query_selector('.el-tree-node__label')
                    if label:
                        text = await label.text_content()
                        print(f"节点 {i+1}: {text.strip()}")
            
            # 检查是否有子节点
            first_node_expanded = await page.query_selector('.el-tree-node.is-expanded')
            if first_node_expanded:
                print("[DECORATIVE] 有展开的节点")
            else:
                print("[DECORATIVE] 没有展开的节点")
            
            # 尝试展开第一个节点
            expand_icon = await page.query_selector('.el-tree-node .el-tree-node__expand-icon')
            if expand_icon:
                print("点击展开图标...")
                await expand_icon.click()
                await asyncio.sleep(2)
                
                # 再次获取节点
                tree_nodes_after = await page.query_selector_all('.el-tree-node')
                print(f"展开后找到 {len(tree_nodes_after)} 个树节点")
                
                if len(tree_nodes_after) > 1:
                    for i, node in enumerate(tree_nodes_after[1:6]):
                        label = await node.query_selector('.el-tree-node__label')
                        if label:
                            text = await label.text_content()
                            print(f"子节点 {i+1}: {text.strip()}")
            
            # 截图
            await page.screenshot(path='tree-debug.png', full_page=True)
            print("截图已保存到 tree-debug.png")
            
            # 打印 API 调用
            print("\nAPI 调用记录:")
            for call in api_calls:
                status_mark = "[DECORATIVE]" if call['ok'] else "[DECORATIVE]"
                print(f"  {status_mark} [{call['status']}] {call['url']}")
            
        except Exception as e:
            print(f"测试异常: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path='tree-error.png')
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tree_debug())

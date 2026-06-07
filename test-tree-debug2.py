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
            await page.goto("http://localhost:3005/system/relationships", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(3)
            
            # 选择产品
            print("选择产品...")
            product_selectors = await page.query_selector_all('.el-select')
            print(f"找到 {len(product_selectors)} 个下拉框")
            
            if product_selectors:
                await product_selectors[0].click()
                await asyncio.sleep(1)
                options = await page.query_selector_all('.el-select-dropdown__item')
                print(f"产品选项数量: {len(options)}")
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
                print(f"版本选项数量: {len(version_options)}")
                if len(version_options) > 0:
                    await version_options[0].click()
                    await asyncio.sleep(3)
            
            # 检查页面内容
            print("\n检查页面内容...")
            page_content = await page.content()
            
            # 查找树容器
            tree_containers = await page.query_selector_all('.relation-scope-tree')
            print(f"找到 {len(tree_containers)} 个 relation-scope-tree 容器")
            
            rst_containers = await page.query_selector_all('.rst-tree-container')
            print(f"找到 {len(rst_containers)} 个 rst-tree-container")
            
            el_trees = await page.query_selector_all('.el-tree')
            print(f"找到 {len(el_trees)} 个 el-tree 组件")
            
            # 获取树节点
            print("\n获取树节点...")
            tree_nodes = await page.query_selector_all('.el-tree-node')
            print(f"找到 {len(tree_nodes)} 个 el-tree-node 元素")
            
            # 获取加载状态
            loading_elements = await page.query_selector_all('.rst-loading')
            if loading_elements:
                print("[WARNING] 树正在加载中...")
            
            # 获取空状态
            empty_elements = await page.query_selector_all('.rst-empty')
            if empty_elements:
                print("[WARNING] 树为空（无数据）")
            
            # 截图
            await page.screenshot(path='tree-debug.png', full_page=True)
            print("\n截图已保存到 tree-debug.png")
            
            # 打印 API 调用
            print("\n" + "="*60)
            print("API 调用记录:")
            print("="*60)
            for call in api_calls:
                status_mark = "[DECORATIVE]" if call['ok'] else "[DECORATIVE]"
                # 提取 API 路径
                path = call['url'].split('/api')[1] if '/api' in call['url'] else call['url']
                print(f"  {status_mark} [{call['status']}] {path}")
            
            print("\n" + "="*60)
            print("总结:")
            print("="*60)
            
            if len(tree_nodes) == 0:
                if loading_elements:
                    print("[X] 问题：树正在加载但没有节点")
                elif empty_elements:
                    print("[X] 问题：树为空，后端可能没有返回数据")
                else:
                    print("[X] 问题：没有找到树组件，可能组件未渲染")
            else:
                print(f"[DECORATIVE] 树已加载，共 {len(tree_nodes)} 个节点")
            
        except Exception as e:
            print(f"测试异常: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path='tree-error.png')
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tree_debug())

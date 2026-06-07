import asyncio
from playwright.async_api import async_playwright

async def test_tree_detailed():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        # 监听控制台消息
        console_messages = []
        page.on("console", lambda msg: console_messages.append({
            'type': msg.type,
            'text': msg.text
        }))
        
        # 监听网络请求
        network_calls = []
        page.on("response", lambda response: network_calls.append({
            'url': response.url,
            'status': response.status
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
            
            # 清空之前的日志
            console_messages.clear()
            network_calls.clear()
            
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
            
            # 选择版本
            print("选择版本...")
            version_selectors = await page.query_selector_all('.el-select')
            if len(version_selectors) > 1:
                await version_selectors[1].click()
                await asyncio.sleep(1)
                await page.keyboard.press('Enter')
                await asyncio.sleep(5)
            
            # 打印网络调用
            print("\n" + "="*60)
            print("网络请求:")
            print("="*60)
            for call in network_calls[-20:]:
                url_path = call['url'].split('/api')[1] if '/api' in call['url'] else call['url']
                print(f"  [{call['status']}] {url_path[:100]}")
            
            # 打印控制台错误
            print("\n" + "="*60)
            print("控制台消息 (最后20条):")
            print("="*60)
            for msg in console_messages[-20:]:
                if msg['type'] in ['error', 'warning']:
                    print(f"  [{msg['type']}] {msg['text'][:200]}")
            
            # 检查页面状态
            print("\n" + "="*60)
            print("页面元素检查:")
            print("="*60)
            
            # 检查树容器
            tree_container = await page.query_selector('.rst-tree-container')
            if tree_container:
                print("[DECORATIVE] 树容器存在")
                
                # 检查加载状态
                loading = await tree_container.query_selector('.rst-loading')
                if loading:
                    print("[WARNING] 树正在加载...")
                
                # 检查空状态
                empty = await tree_container.query_selector('.rst-empty')
                if empty:
                    print("[WARNING] 树为空")
                
                # 检查 el-tree
                el_tree = await tree_container.query_selector('.el-tree')
                if el_tree:
                    print("[DECORATIVE] el-tree 组件存在")
                else:
                    print("[DECORATIVE] el-tree 组件不存在")
            else:
                print("[DECORATIVE] 树容器不存在")
            
            # 获取树节点
            tree_nodes = await page.query_selector_all('.el-tree-node')
            print(f"\n树节点数量: {len(tree_nodes)}")
            
            # 截图
            await page.screenshot(path='tree-detailed.png', full_page=True)
            print("\n截图已保存到 tree-detailed.png")
            
        except Exception as e:
            print(f"测试异常: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path='tree-error.png')
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tree_detailed())

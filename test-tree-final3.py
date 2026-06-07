import asyncio
from playwright.async_api import async_playwright

async def test_tree_final():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        console_messages = []
        page.on("console", lambda msg: console_messages.append(f"[{msg.type}] {msg.text}") if 'RelationScopeTree' in msg.text or 'useVersionContext' in msg.text or 'VersionContextSelector' in msg.text else None)
        
        try:
            print("访问首页...")
            await page.goto("http://localhost:3004/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)
            
            # 登录
            print("登录...")
            await page.fill('input[type="text"], input[name="username"], input[name="account"]', 'admin')
            await page.fill('input[type="password"]', 'admin123')
            await page.click('button[type="submit"]')
            await asyncio.sleep(5)
            
            # 导航到关系管理页面
            print("导航到关系管理页面...")
            await page.goto("http://localhost:3004/system/relationships", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)
            
            # 清空日志
            console_messages.clear()
            
            # 选择产品
            print("\n选择产品...")
            product_selectors = await page.query_selector_all('.el-select')
            if product_selectors:
                await product_selectors[0].click()
                await asyncio.sleep(1)
                options = await page.query_selector_all('.el-select-dropdown__item')
                print(f"产品选项数量: {len(options)}")
                if len(options) > 0:
                    await options[0].click()
                    await asyncio.sleep(3)
            
            # 选择版本 - 使用键盘操作
            print("\n选择版本（使用键盘）...")
            version_selectors = await page.query_selector_all('.el-select')
            if len(version_selectors) > 1:
                await version_selectors[1].click()
                await asyncio.sleep(1)
                # 按下键选择第一个选项
                await page.keyboard.press('ArrowDown')
                await asyncio.sleep(0.5)
                # 按 Enter 确认
                await page.keyboard.press('Enter')
                await asyncio.sleep(5)
            
            # 打印相关日志
            print("\n相关日志:")
            for msg in console_messages:
                print(f"  {msg}")
            
            # 检查树状态
            print("\n" + "="*60)
            print("最终状态检查:")
            print("="*60)
            
            loading = await page.query_selector('.rst-loading')
            empty = await page.query_selector('.rst-empty')
            tree_nodes = await page.query_selector_all('.el-tree-node')
            
            print(f"加载状态: {'显示' if loading else '隐藏'}")
            print(f"空状态: {'显示' if empty else '隐藏'}")
            print(f"树节点数: {len(tree_nodes)}")
            
            # 获取节点内容
            if tree_nodes:
                print("\n树节点内容:")
                for i, node in enumerate(tree_nodes[:5]):
                    label = await node.query_selector('.el-tree-node__label')
                    if label:
                        text = await label.text_content()
                        print(f"  {i+1}. {text.strip()}")
            
            # 截图
            await page.screenshot(path='tree_final.png', full_page=True)
            print("\n截图已保存到 tree_final.png")
            
        except Exception as e:
            print(f"\n测试异常: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path='test_error.png')
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tree_final())

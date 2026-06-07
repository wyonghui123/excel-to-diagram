import asyncio
from playwright.async_api import async_playwright

async def test_version_select():
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
            print("\n选择产品...")
            product_selectors = await page.query_selector_all('.el-select')
            if product_selectors:
                await product_selectors[0].click()
                await asyncio.sleep(1)
                options = await page.query_selector_all('.el-select-dropdown__item')
                print(f"产品选项数量: {len(options)}")
                if len(options) > 0:
                    await options[0].click()
                    await asyncio.sleep(2)
            
            # 选择版本 - 使用 JavaScript 直接设置值
            print("\n使用 JavaScript 选择版本...")
            await page.evaluate("""() => {
                const selectors = document.querySelectorAll('.el-select');
                if (selectors.length > 1) {
                    const vueInstance = selectors[1].__vueParentComponent;
                    console.log('Found version selector');
                    
                    // 触发版本选择器的 visible-change 事件
                    const selectComponent = selectors[1].__vueParentComponent;
                    if (selectComponent && selectComponent.exposed) {
                        console.log('Exposed methods:', Object.keys(selectComponent.exposed));
                    }
                }
            }""")
            await asyncio.sleep(1)
            
            # 使用更简单的方法：直接点击下拉框并选择选项
            version_selectors = await page.query_selector_all('.el-select')
            if len(version_selectors) > 1:
                # 获取版本选择器的输入框
                version_input = await version_selectors[1].query_selector('input')
                if version_input:
                    # 点击输入框打开下拉菜单
                    await version_input.click()
                    await asyncio.sleep(1)
                    
                    # 获取下拉选项
                    dropdown_items = await page.query_selector_all('.el-select-dropdown__item')
                    print(f"下拉选项数量: {len(dropdown_items)}")
                    
                    if len(dropdown_items) > 0:
                        # 直接点击第一个选项
                        item_html = await dropdown_items[0].inner_html()
                        print(f"第一个选项 HTML: {item_html[:100]}")
                        
                        # 尝试使用 force 选项点击
                        await dropdown_items[0].click(force=True)
                        print("点击了第一个选项")
                        await asyncio.sleep(3)
            
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
            
            # 截图
            await page.screenshot(path='test_version_select.png', full_page=True)
            print("\n截图已保存到 test_version_select.png")
            
        except Exception as e:
            print(f"\n测试异常: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path='test_error.png')
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_version_select())

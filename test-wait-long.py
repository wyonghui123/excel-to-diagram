import asyncio
from playwright.async_api import async_playwright

async def test_wait_long():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        console_errors = []
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == 'error' else None)
        
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
            
            # 等待 el-select 渲染
            print("\n等待 el-select 渲染...")
            try:
                await page.wait_for_selector('.el-select', timeout=10000)
                print("el-select 已渲染")
            except:
                print("等待 el-select 超时")
            
            # 检查页面元素
            el_selects = await page.query_selector_all('.el-select')
            print(f"\nel-select 数量: {len(el_selects)}")
            
            # 等待下拉菜单选项
            print("\n等待产品选项渲染...")
            try:
                product_selectors = await page.query_selector_all('.el-select')
                if product_selectors:
                    await product_selectors[0].click()
                    await page.wait_for_selector('.el-select-dropdown__item', timeout=5000)
                    options = await page.query_selector_all('.el-select-dropdown__item')
                    print(f"产品选项数量: {len(options)}")
                    
                    if len(options) > 0:
                        await options[0].click()
                        await asyncio.sleep(3)
                        
                        # 等待版本选项
                        print("\n等待版本选项...")
                        version_selectors = await page.query_selector_all('.el-select')
                        if len(version_selectors) > 1:
                            await version_selectors[1].click()
                            await page.wait_for_selector('.el-select-dropdown__item', timeout=5000)
                            version_options = await page.query_selector_all('.el-select-dropdown__item')
                            print(f"版本选项数量: {len(version_options)}")
                            
                            if len(version_options) > 0:
                                await version_options[0].click()
                                await asyncio.sleep(3)
            except Exception as e:
                print(f"选择选项时出错: {e}")
            
            # 检查树状态
            print("\n" + "="*60)
            print("树状态检查:")
            print("="*60)
            
            loading = await page.query_selector('.rst-loading')
            empty = await page.query_selector('.rst-empty')
            tree_nodes = await page.query_selector_all('.el-tree-node')
            
            print(f"加载状态: {'显示' if loading else '隐藏'}")
            print(f"空状态: {'显示' if empty else '隐藏'}")
            print(f"树节点数: {len(tree_nodes)}")
            
            # 检查控制台错误
            if console_errors:
                print("\n控制台错误:")
                for err in console_errors[:5]:
                    print(f"  {err}")
            
            # 截图
            await page.screenshot(path='test_wait_long.png', full_page=True)
            print("\n截图已保存到 test_wait_long.png")
            
        except Exception as e:
            print(f"\n测试异常: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path='test_error.png')
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_wait_long())

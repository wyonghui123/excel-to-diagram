import asyncio
from playwright.async_api import async_playwright

async def test_tree_diagnose():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        console_errors = []
        page.on("console", lambda msg: console_errors.append(f"[{msg.type}] {msg.text}") if msg.type == 'error' else None)
        
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
            
            # 选择版本
            print("选择版本...")
            version_selectors = await page.query_selector_all('.el-select')
            if len(version_selectors) > 1:
                await version_selectors[1].click()
                await asyncio.sleep(1)
                await page.keyboard.press('Enter')
                await asyncio.sleep(5)
            
            # 截图
            await page.screenshot(path='tree_diagnose.png', full_page=True)
            print("\n截图已保存到 tree_diagnose.png")
            
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
            
            # 打印控制台错误
            if console_errors:
                print("\n控制台错误:")
                for err in console_errors[:10]:
                    print(f"  {err}")
            
            # 尝试获取更多诊断信息
            print("\n尝试手动触发树加载...")
            
            # 检查是否有 JavaScript 错误
            js_errors = await page.evaluate("""() => {
                const errors = [];
                window.onerror = (msg, url, line, col, error) => {
                    errors.push({msg, line, col});
                };
                return errors;
            }""")
            if js_errors:
                print(f"JS 错误: {js_errors}")
            
            # 尝试直接检查 versionId
            version_context = await page.evaluate("""() => {
                // 尝试获取 versionContext 的状态
                try {
                    const treeEl = document.querySelector('.relation-scope-tree');
                    if (treeEl && treeEl.__vueParentComponent) {
                        const props = treeEl.__vueParentComponent.props;
                        return { versionId: props.versionId };
                    }
                } catch(e) {}
                return null;
            }""")
            print(f"\nversionId 检查: {version_context}")
            
        except Exception as e:
            print(f"测试异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_tree_diagnose())

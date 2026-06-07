import asyncio
from playwright.async_api import async_playwright

async def test_js_select():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        console_messages = []
        page.on("console", lambda msg: console_messages.append(f"[{msg.type}] {msg.text}"))
        
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
            print(f"初始 el-select 数量: {len(product_selectors)}")
            
            if product_selectors:
                await product_selectors[0].click()
                await asyncio.sleep(1)
                options = await page.query_selector_all('.el-select-dropdown__item')
                print(f"产品选项数量: {len(options)}")
                if len(options) > 0:
                    await options[0].click()
                    await asyncio.sleep(3)
            
            # 检查版本选择器
            print("\n检查页面结构...")
            el_selects = await page.query_selector_all('.el-select')
            print(f"选择产品后 el-select 数量: {len(el_selects)}")
            
            for i, select in enumerate(el_selects):
                placeholder = await select.query_selector('.el-input__inner, .el-select__placeholder')
                if placeholder:
                    text = await placeholder.text_content()
                    print(f"  选择器 {i+1}: {text.strip()}")
            
            # 使用 JavaScript 选择版本
            print("\n使用 JavaScript 选择版本...")
            result = await page.evaluate("""() => {
                // 获取所有 el-select 组件
                const selectors = document.querySelectorAll('.el-select');
                console.log('[JS] Found', selectors.length, 'el-select components');
                
                // 找到版本选择器（第二个）
                if (selectors.length > 1) {
                    const versionSelect = selectors[1];
                    
                    // 尝试通过 DOM 结构找到 input
                    const input = versionSelect.querySelector('input');
                    if (input) {
                        console.log('[JS] Found input');
                        // 设置值并触发事件
                        const versionId = parseInt(input.getAttribute('data-option-id')) || 1;
                        
                        // 尝试触发 el-select 的选择
                        const selectInstance = versionSelect.__vueParentComponent;
                        if (selectInstance && selectInstance.ctx) {
                            console.log('[JS] Found Vue component ctx');
                            // 直接设置 selectedVersionId
                            const versionContext = selectInstance.setupState;
                            console.log('[JS] setupState keys:', Object.keys(versionContext || {}));
                        }
                        
                        return { 
                            success: true, 
                            message: 'Found version select and input',
                            placeholder: input.placeholder
                        };
                    }
                }
                return { success: false, error: 'Version select not found' };
            }""")
            print(f"JavaScript 结果: {result}")
            
            # 打印控制台消息
            print("\n" + "="*60)
            print("控制台消息:")
            print("="*60)
            for msg in console_messages:
                print(msg)
            
            # 截图
            await page.screenshot(path='test_js_select.png', full_page=True)
            print("\n截图已保存到 test_js_select.png")
            
        except Exception as e:
            print(f"\n测试异常: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path='test_error.png')
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_js_select())

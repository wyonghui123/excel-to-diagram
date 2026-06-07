import asyncio
from playwright.async_api import async_playwright

async def test_version_loading():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        
        try:
            print("访问首页...")
            await page.goto("http://localhost:3005/", wait_until="load", timeout=10000)
            await asyncio.sleep(2)
            
            # 检查是否有登录表单
            login_form = await page.query_selector('form')
            if login_form:
                print("发现登录表单，进行登录...")
                await page.fill('input[type="text"], input[name="username"], input[name="account"]', 'admin')
                await page.fill('input[type="password"]', 'admin123')
                await page.click('button[type="submit"]')
                await asyncio.sleep(3)
            
            # 导航到关系管理页面
            print("导航到关系管理页面...")
            await page.goto("http://localhost:3005/system/relationships", wait_until="networkidle", timeout=15000)
            await asyncio.sleep(3)
            
            # 查找产品选择器
            print("查找产品选择器...")
            product_selectors = await page.query_selector_all('.el-select')
            
            if product_selectors:
                print(f"找到 {len(product_selectors)} 个 el-select 组件")
                
                # 点击第一个下拉框（产品选择器）
                print("点击产品选择器...")
                await product_selectors[0].click()
                await asyncio.sleep(1)
                
                # 等待选项出现
                print("等待选项出现...")
                await page.wait_for_selector('.el-select-dropdown__item', timeout=5000)
                
                # 获取所有选项
                options = await page.query_selector_all('.el-select-dropdown__item')
                print(f"找到 {len(options)} 个选项")
                
                if len(options) > 0:
                    # 点击第一个选项
                    print("选择第一个产品...")
                    await options[0].click()
                    await asyncio.sleep(2)
                    
                    # 检查版本选择器是否有内容
                    print("检查版本列表...")
                    
                    # 再次点击第二个下拉框（版本选择器）
                    product_selectors_after = await page.query_selector_all('.el-select')
                    if len(product_selectors_after) > 1:
                        print("点击版本选择器...")
                        await product_selectors_after[1].click()
                        await asyncio.sleep(1)
                        
                        # 等待版本选项
                        try:
                            version_options = await page.query_selector_all('.el-select-dropdown__item')
                            print(f"版本选项数量: {len(version_options)}")
                            
                            if len(version_options) > 0:
                                print("[OK] 版本列表加载成功！")
                                for i, opt in enumerate(version_options[:5]):
                                    text = await opt.text_content()
                                    print(f"  版本 {i+1}: {text.strip()}")
                            else:
                                print("[X] 版本列表为空")
                        except Exception as e:
                            print(f"[X] 获取版本选项失败: {e}")
                    else:
                        print("[X] 版本选择器不存在")
                else:
                    print("[X] 没有找到可选择的选项")
            else:
                print("[X] 未找到 el-select 组件")
                
                # 尝试其他选择器
                page_content = await page.content()
                if 'product' in page_content.lower():
                    print("页面包含产品相关内容")
                if 'version' in page_content.lower():
                    print("页面包含版本相关内容")
            
            # 截图保存结果
            await page.screenshot(path='test-result.png')
            print("截图已保存到 test-result.png")
            
        except Exception as e:
            print(f"测试异常: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path='test-error.png')
            print("错误截图已保存到 test-error.png")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_version_loading())

"""
调试关系管理页面 - 截图版本
"""
import asyncio
from playwright.async_api import async_playwright
import sys

async def test_with_screenshot():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        
        try:
            print("1. 访问首页...")
            await page.goto("http://localhost:3004/")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            await page.screenshot(path="debug_01_homepage.png")
            print("   截图: debug_01_homepage.png")
            
            print("2. 执行登录...")
            username_input = page.locator('input[placeholder*="用户名"], input[type="text"]').first
            password_input = page.locator('input[type="password"]')
            
            if await username_input.is_visible():
                print("   找到登录表单，填写...")
                await username_input.fill("admin")
                await password_input.fill("admin123")
                await asyncio.sleep(0.5)
                
                login_btn = page.locator('button[type="submit"], button:has-text("登 录")')
                if await login_btn.is_visible():
                    print("   点击登录按钮...")
                    await login_btn.click()
                    await asyncio.sleep(3)
                    await page.screenshot(path="debug_02_after_login.png")
                    print("   截图: debug_02_after_login.png")
            else:
                print("   未找到登录表单，可能已经登录")
                await asyncio.sleep(2)
            
            print("3. 导航到关系管理页面...")
            await page.goto("http://localhost:3004/system/relationships")
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(3)
            await page.screenshot(path="debug_03_relationships.png")
            print("   截图: debug_03_relationships.png")
            
            title = await page.title()
            print(f"   页面标题: {title}")
            
            if "关系管理" in title:
                print("4. 成功进入关系管理页面!")
                
                # 检查版本选择器
                print("5. 检查版本选择器...")
                version_selector = page.locator(".version-context-selector")
                if await version_selector.is_visible():
                    print("   [DECORATIVE] 版本选择器已显示")
                    await page.screenshot(path="debug_04_version_selector.png")
                    
                    # 点击产品选择器
                    print("6. 点击产品选择器...")
                    product_select = page.locator(".version-context-selector .el-select").first
                    if await product_select.is_visible():
                        await product_select.click()
                        await asyncio.sleep(1)
                        
                        options = page.locator(".el-select-dropdown__item")
                        count = await options.count()
                        print(f"   产品选项数量: {count}")
                        
                        if count > 0:
                            await page.screenshot(path="debug_05_product_options.png")
                            print("   选择第一个产品...")
                            await options.first.click()
                            await asyncio.sleep(2)
                            
                            version_select = page.locator(".version-context-selector .el-select").nth(1)
                            is_disabled = await version_select.get_attribute("disabled")
                            
                            if not is_disabled:
                                print("7. 版本选择器已启用!")
                                await version_select.click()
                                await asyncio.sleep(1)
                                
                                version_options = page.locator(".el-select-dropdown__item")
                                version_count = await version_options.count()
                                print(f"   版本选项数量: {version_count}")
                                
                                if version_count > 0:
                                    print("8. 选择第一个版本...")
                                    await version_options.first.click()
                                    await asyncio.sleep(2)
                                    
                                    await page.screenshot(path="debug_06_after_version_select.png")
                                    
                                    tree_nodes = page.locator(".el-tree-node")
                                    node_count = await tree_nodes.count()
                                    print(f"   树节点数量: {node_count}")
                                    
                                    if node_count > 0:
                                        print("   [OK] 业务对象树已加载!")
                                    else:
                                        print("   ! 树为空（可能正常）")
                                else:
                                    print("   [DECORATIVE] 没有版本选项")
                            else:
                                print("   [DECORATIVE] 版本选择器仍被禁用")
                        else:
                            print("   [DECORATIVE] 没有产品选项")
                    else:
                        print("   [DECORATIVE] 产品选择器未显示")
                else:
                    print("   [DECORATIVE] 版本选择器未显示")
            else:
                print(f"   [DECORATIVE] 未进入关系管理页面，当前标题: {title}")
                
            print("\n测试完成!")
            
        except Exception as e:
            print(f"\n[X] 测试出错: {e}")
            await page.screenshot(path="debug_error.png")
            print("   错误截图: debug_error.png")
            import traceback
            traceback.print_exc()
        finally:
            await asyncio.sleep(2)
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_with_screenshot())

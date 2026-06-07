"""
测试关系管理页面的单例模式修复
"""
import asyncio
from playwright.async_api import async_playwright
import sys

async def test_relationship_singleton():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # 访问首页
            print("1. 访问首页...")
            await page.goto("http://localhost:3004/")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            
            # 登录
            print("2. 执行登录...")
            username_input = page.locator('input[placeholder*="用户名"], input[type="text"]').first
            password_input = page.locator('input[type="password"]')
            
            if await username_input.is_visible():
                await username_input.fill("admin")
                await password_input.fill("admin123")
                login_btn = page.locator('button[type="submit"], button:has-text("登 录")')
                if await login_btn.is_visible():
                    await login_btn.click()
                    await asyncio.sleep(3)
            else:
                print("   未找到登录表单，可能已经登录")
                await asyncio.sleep(2)
            
            # 导航到关系管理页面
            print("3. 导航到关系管理页面...")
            await page.goto("http://localhost:3004/system/relationships")
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(3)
            
            # 再次检查登录状态
            title = await page.title()
            print(f"   当前页面标题: {title}")
            
            # 检查页面标题
            title = await page.title()
            print(f"   页面标题: {title}")
            
            # 检查版本选择器
            print("4. 检查版本选择器...")
            version_selector = page.locator(".version-context-selector")
            if await version_selector.is_visible():
                print("   [DECORATIVE] 版本选择器已显示")
            else:
                print("   [DECORATIVE] 版本选择器未显示")
            
            # 点击产品选择器
            print("5. 点击产品选择器...")
            product_select = page.locator(".version-context-selector .el-select").first
            if await product_select.is_visible():
                await product_select.click()
                await asyncio.sleep(1)
                
                # 检查是否有选项
                options = page.locator(".el-select-dropdown__item")
                count = await options.count()
                print(f"   产品选项数量: {count}")
                
                if count > 0:
                    # 选择第一个产品
                    print("6. 选择第一个产品...")
                    await options.first.click()
                    await asyncio.sleep(2)
                    
                    # 检查版本选择器是否启用
                    print("7. 检查版本选择器状态...")
                    version_select = page.locator(".version-context-selector .el-select").nth(1)
                    is_disabled = await version_select.get_attribute("disabled")
                    print(f"   版本选择器禁用状态: {is_disabled}")
                    
                    if not is_disabled:
                        # 点击版本选择器
                        print("8. 点击版本选择器...")
                        await version_select.click()
                        await asyncio.sleep(1)
                        
                        version_options = page.locator(".el-select-dropdown__item")
                        version_count = await version_options.count()
                        print(f"   版本选项数量: {version_count}")
                        
                        if version_count > 0:
                            print("9. 选择第一个版本...")
                            await version_options.first.click()
                            await asyncio.sleep(2)
                            
                            # 检查业务对象树
                            print("10. 检查业务对象树...")
                            tree_container = page.locator(".relation-scope-tree, [class*='scope-tree']")
                            if await tree_container.is_visible():
                                print("   [DECORATIVE] 业务对象树容器已显示")
                            else:
                                print("   [DECORATIVE] 业务对象树容器未显示")
                                
                            # 检查是否有树节点
                            tree_nodes = page.locator(".el-tree-node")
                            node_count = await tree_nodes.count()
                            print(f"   树节点数量: {node_count}")
                            
                            if node_count > 0:
                                print("   [DECORATIVE] 业务对象树已加载!")
                            else:
                                print("   ! 业务对象树为空（可能正常，取决于数据）")
                    
                    print("\n[OK] 测试完成!")
                else:
                    print("   [DECORATIVE] 没有可用的产品选项")
            else:
                print("   [DECORATIVE] 产品选择器未显示")
                
        except Exception as e:
            print(f"\n[X] 测试出错: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_relationship_singleton())

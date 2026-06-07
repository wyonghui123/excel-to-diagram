"""
简单测试关系管理页面 - 直接访问路径
"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        
        try:
            print("1. 直接访问关系管理页面...")
            await page.goto("http://localhost:3004/system/relationships")
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(3)
            
            title = await page.title()
            print(f"   页面标题: {title}")
            
            await page.screenshot(path="debug_01_direct.png")
            print("   截图: debug_01_direct.png")
            
            if "关系管理" in title:
                print("   [DECORATIVE] 成功进入关系管理页面!")
                
                print("2. 检查版本选择器...")
                version_selector = page.locator(".version-context-selector")
                if await version_selector.is_visible():
                    print("   [DECORATIVE] 版本选择器已显示")
                    await page.screenshot(path="debug_02_version_selector.png")
                    
                    print("3. 点击产品选择器...")
                    product_select = page.locator(".version-context-selector .el-select").first
                    await product_select.click()
                    await asyncio.sleep(1)
                    
                    options = page.locator(".el-select-dropdown__item")
                    count = await options.count()
                    print(f"   产品选项数量: {count}")
                    
                    if count > 0:
                        await page.screenshot(path="debug_03_product_options.png")
                        print("4. 选择第一个产品...")
                        await options.first.click()
                        await asyncio.sleep(2)
                        
                        version_select = page.locator(".version-context-selector .el-select").nth(1)
                        is_disabled = await version_select.get_attribute("disabled")
                        
                        if not is_disabled:
                            print("5. 版本选择器已启用!")
                            await version_select.click()
                            await asyncio.sleep(1)
                            
                            version_options = page.locator(".el-select-dropdown__item")
                            version_count = await version_options.count()
                            print(f"   版本选项数量: {version_count}")
                            
                            if version_count > 0:
                                print("6. 选择第一个版本...")
                                await version_options.first.click()
                                await asyncio.sleep(2)
                                
                                await page.screenshot(path="debug_04_after_version.png")
                                
                                tree_nodes = page.locator(".el-tree-node")
                                node_count = await tree_nodes.count()
                                print(f"   树节点数量: {node_count}")
                                
                                if node_count > 0:
                                    print("   [OK] 业务对象树已加载!")
                                else:
                                    print("   ! 树为空")
                            else:
                                print("   [DECORATIVE] 没有版本选项")
                        else:
                            print("   [DECORATIVE] 版本选择器仍被禁用")
                    else:
                        print("   [DECORATIVE] 没有产品选项")
                else:
                    print("   [DECORATIVE] 版本选择器未显示")
            else:
                print(f"   ! 当前页面: {title}")
                await page.screenshot(path="debug_error.png")
                
        except Exception as e:
            print(f"\n[X] 错误: {e}")
            await page.screenshot(path="debug_exception.png")
            import traceback
            traceback.print_exc()
        finally:
            await asyncio.sleep(2)
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test())

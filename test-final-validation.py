"""
最终验证测试 - 使用正确端口
"""
import asyncio
from playwright.async_api import async_playwright

async def test():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page = await context.new_page()
        
        try:
            print("=" * 60)
            print("最终验证测试 - 单例模式修复")
            print("=" * 60)
            
            # 1. 访问首页并登录
            print("\n[1] 访问首页并登录...")
            await page.goto("http://localhost:3005/")
            await page.wait_for_load_state("networkidle")
            await asyncio.sleep(2)
            
            username_input = page.locator('input[placeholder*="用户名"], input[type="text"]').first
            password_input = page.locator('input[type="password"]')
            
            if await username_input.is_visible(timeout=5000):
                await username_input.fill("admin")
                await password_input.fill("admin123")
                login_btn = page.locator('button[type="submit"], button:has-text("登")').first
                await login_btn.click()
                await asyncio.sleep(3)
            
            # 2. 导航到关系管理页面
            print("\n[2] 导航到关系管理页面...")
            await page.goto("http://localhost:3005/system/relationships")
            await page.wait_for_load_state("domcontentloaded")
            await asyncio.sleep(3)
            
            title = await page.title()
            print(f"    页面标题: {title}")
            
            if "关系管理" not in title:
                print("    [X] 未进入关系管理页面")
                return False
            
            print("    [OK] 成功进入关系管理页面")
            
            # 3. 检查版本选择器
            print("\n[3] 检查版本选择器...")
            version_selector = page.locator(".version-context-selector")
            if not await version_selector.is_visible(timeout=5000):
                print("    [X] 版本选择器未显示")
                return False
            print("    [OK] 版本选择器已显示")
            
            # 4. 点击产品选择器
            print("\n[4] 点击产品选择器...")
            product_select = page.locator(".version-context-selector .el-select").first
            await product_select.click()
            await asyncio.sleep(1)
            
            options = page.locator(".el-select-dropdown__item")
            count = await options.count()
            print(f"    产品选项数量: {count}")
            
            if count == 0:
                print("    [X] 没有产品选项 - 可能是后端连接问题")
                return False
            
            print("    [OK] 产品列表已加载")
            
            # 5. 选择第一个产品
            print("\n[5] 选择第一个产品...")
            await options.first.click()
            await asyncio.sleep(2)
            
            # 6. 关键验证：检查版本选择器是否启用
            print("\n[6] 检查版本选择器是否启用（关键验证）...")
            version_select = page.locator(".version-context-selector .el-select").nth(1)
            is_disabled = await version_select.get_attribute("disabled")
            
            if is_disabled:
                print("    [X] 版本选择器仍被禁用 - 单例模式可能有问题")
                return False
            else:
                print("    [OK] 版本选择器已启用!")
            
            await page.screenshot(path="final_test_result.png")
            
            print("\n" + "=" * 60)
            print("[OK] 测试通过 - 单例模式修复成功!")
            print("=" * 60)
            
            return True
                
        except Exception as e:
            print(f"\n[X] 测试异常: {e}")
            await page.screenshot(path="final_test_error.png")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await asyncio.sleep(2)
            await browser.close()

if __name__ == "__main__":
    result = asyncio.run(test())
    exit(0 if result else 1)

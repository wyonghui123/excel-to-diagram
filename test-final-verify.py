import asyncio
from playwright.async_api import async_playwright

async def test_final():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        try:
            print("访问并登录...")
            await page.goto("http://localhost:3004/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)
            await page.fill('input[type="text"], input[name="username"], input[name="account"]', 'admin')
            await page.fill('input[type="password"]', 'admin123')
            await page.click('button[type="submit"]')
            await asyncio.sleep(5)
            
            print("导航到关系管理页面...")
            await page.goto("http://localhost:3004/system/relationships", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)
            
            # 选择产品
            print("选择产品...")
            product_selectors = await page.query_selector_all('.el-select')
            if product_selectors:
                await product_selectors[0].click()
                await asyncio.sleep(1)
                options = await page.query_selector_all('.el-select-dropdown__item')
                if len(options) > 0:
                    opt_text = await options[0].text_content()
                    print(f"选择的第一个产品: {opt_text.strip()}")
                    await options[0].click()
                    await asyncio.sleep(3)
            
            # 检查产品选择器显示的值
            product_text = await page.evaluate("""() => {
                const selects = document.querySelectorAll('.el-select');
                if (selects.length > 0) {
                    const input = selects[0].querySelector('.el-select__selected-item, .el-tag');
                    if (input) return input.textContent;
                    const inner = selects[0].querySelector('.el-input__inner');
                    if (inner) return inner.value || inner.placeholder;
                    return selects[0].textContent.trim().substring(0, 50);
                }
                return null;
            }""")
            print(f"选择产品后显示: '{product_text}'")
            
            # 选择版本
            print("\n选择版本...")
            version_selectors = await page.query_selector_all('.el-select')
            if len(version_selectors) > 1:
                await version_selectors[1].click()
                await asyncio.sleep(1)
                await page.keyboard.press('ArrowDown')
                await asyncio.sleep(0.5)
                await page.keyboard.press('Enter')
                await asyncio.sleep(3)
            
            # 再次检查产品
            product_text2 = await page.evaluate("""() => {
                const selects = document.querySelectorAll('.el-select');
                if (selects.length > 0) {
                    const inner = selects[0].querySelector('.el-input__inner');
                    if (inner) return inner.value || inner.placeholder;
                    return selects[0].textContent.trim().substring(0, 50);
                }
                return null;
            }""")
            print(f"选择版本后产品显示: '{product_text2}'")
            
            # 版本显示
            version_text = await page.evaluate("""() => {
                const selects = document.querySelectorAll('.el-select');
                if (selects.length > 1) {
                    const inner = selects[1].querySelector('.el-input__inner');
                    if (inner) return inner.value || inner.placeholder;
                    return selects[1].textContent.trim().substring(0, 50);
                }
                return null;
            }""")
            print(f"选择版本后版本显示: '{version_text}'")
            
            # 检查 disabled 状态
            disabled = await page.evaluate("""() => {
                const selects = document.querySelectorAll('.el-select');
                return {
                    product: selects.length > 0 ? selects[0].classList.contains('is-disabled') : null,
                    version: selects.length > 1 ? selects[1].classList.contains('is-disabled') : null
                };
            }""")
            print(f"产品disabled: {disabled['product']}, 版本disabled: {disabled['version']}")
            
            # 树节点
            tree_nodes = await page.query_selector_all('.el-tree-node')
            print(f"\n树节点数: {len(tree_nodes)}")
            
            if tree_nodes:
                print("顶级节点:")
                for i, node in enumerate(tree_nodes[:5]):
                    label = await node.query_selector('.el-tree-node__label')
                    has_expand = await node.query_selector('.el-tree-node__expand-icon:not(.is-leaf)')
                    if label:
                        text = await label.text_content()
                        flag = "▶" if has_expand else "●"
                        print(f"  {flag} {text.strip()}")
                
                # 展开第一个
                expand_icons = await page.query_selector_all('.el-tree-node__expand-icon:not(.is-leaf)')
                if len(expand_icons) > 0:
                    await expand_icons[0].click()
                    await asyncio.sleep(2)
                    tree_nodes2 = await page.query_selector_all('.el-tree-node')
                    print(f"\n展开后节点数: {len(tree_nodes2)}")
                    for i, node in enumerate(tree_nodes2[len(tree_nodes):][:5]):
                        label = await node.query_selector('.el-tree-node__label')
                        if label:
                            text = await label.text_content()
                            print(f"  {text.strip()}")
            
            await page.screenshot(path='test_final.png', full_page=True)
            
        except Exception as e:
            print(f"异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_final())

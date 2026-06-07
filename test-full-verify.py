import asyncio
from playwright.async_api import async_playwright

async def test_full():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()
        
        try:
            print("登录...")
            await page.goto("http://localhost:3005/", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)
            await page.fill('input[type="text"], input[name="username"], input[name="account"]', 'admin')
            await page.fill('input[type="password"]', 'admin123')
            await page.click('button[type="submit"]')
            await asyncio.sleep(5)
            
            print("导航到关系管理...")
            await page.goto("http://localhost:3005/system/relationships", wait_until="domcontentloaded", timeout=30000)
            await asyncio.sleep(5)
            
            # 选择产品
            selects = await page.query_selector_all('.el-select')
            if selects:
                await selects[0].click()
                await asyncio.sleep(1)
                opts = await page.query_selector_all('.el-select-dropdown__item')
                if opts:
                    await opts[0].click()
                    await asyncio.sleep(3)
            
            # 选择版本
            selects2 = await page.query_selector_all('.el-select')
            if len(selects2) > 1:
                await selects2[1].click()
                await asyncio.sleep(1)
                await page.keyboard.press('ArrowDown')
                await asyncio.sleep(0.5)
                await page.keyboard.press('Enter')
                await asyncio.sleep(5)
            
            # ===== 检查面板结构 =====
            print("\n" + "="*60)
            print("面板结构检查:")
            print("="*60)
            
            panels = await page.query_selector_all('.collapsible-panel')
            print(f"CollapsiblePanel 数量: {len(panels)}")
            
            for i, panel in enumerate(panels):
                header = await panel.query_selector('.collapsible-panel__header')
                title_el = await panel.query_selector('.collapsible-panel__title')
                badge = await panel.query_selector('.collapsible-panel__badge')
                
                title_text = await title_el.text_content() if title_el else '(无)'
                badge_text = await badge.text_content() if badge else '(无)'
                print(f"  Panel {i+1}: 标题='{title_text}', Badge='{badge_text}'")
            
            # ===== 对象范围树 =====
            print("\n" + "="*60)
            print("对象范围树:")
            print("="*60)
            
            all_tree_nodes = await page.query_selector_all('.el-tree-node')
            print(f"总 el-tree-node 数量: {len(all_tree_nodes)}")
            
            # 对象范围 panel 应展开
            object_panel_content = await page.query_selector_all('.collapsible-panel__content')
            print(f"可见的 panel content: {len([c for c in object_panel_content if await c.is_visible()])}")
            
            # 检查对象范围树是否有节点
            tree_nodes_visible = [n for n in all_tree_nodes if await n.is_visible()]
            print(f"可见的树节点: {len(tree_nodes_visible)}")
            
            if len(tree_nodes_visible) > 0:
                print("\n可见节点内容:")
                for i, node in enumerate(tree_nodes_visible[:10]):
                    label = await node.query_selector('.el-tree-node__label')
                    cb = await node.query_selector('.el-checkbox')
                    if label:
                        text = await label.text_content()
                        has_cb = "[DECORATIVE]" if cb else ""
                        print(f"  {has_cb} {text.strip()}")
            
            # ===== 勾选对象范围 =====
            print("\n" + "="*60)
            print("勾选对象范围节点:")
            print("="*60)
            
            # 尝试点击复选框
            checkboxes = await page.query_selector_all('.el-tree-node .el-checkbox__input')
            vis_checkboxes = [cb for cb in checkboxes if await cb.is_visible()]
            print(f"可见复选框数量: {len(vis_checkboxes)}")
            
            if len(vis_checkboxes) > 0:
                await vis_checkboxes[0].click()
                await asyncio.sleep(2)
                print("[DECORATIVE] 勾选了第一个节点")
                
                # 检查"需刷新" badge
                stale = await page.query_selector('.rst-stale-badge')
                if stale:
                    stale_text = await stale.text_content()
                    print(f"[DECORATIVE] '需刷新' badge 显示: '{stale_text}'")
                else:
                    print("[DECORATIVE] 未找到 '需刷新' badge")
            
            # ===== 展开关系范围 =====
            print("\n" + "="*60)
            print("展开关系范围面板:")
            print("="*60)
            
            if len(panels) > 1:
                header2 = await panels[1].query_selector('.collapsible-panel__header')
                if header2:
                    await header2.click()
                    await asyncio.sleep(3)
                    print("[DECORATIVE] 点击了关系范围面板header")
            
            # 检查关系范围树
            await asyncio.sleep(3)
            all_tree_nodes2 = await page.query_selector_all('.el-tree-node')
            print(f"展开后总树节点数: {len(all_tree_nodes2)}")
            
            # 如果有关系分类树，检查其内容
            relation_panels = await page.query_selector_all('.collapsible-panel')
            if len(relation_panels) > 1:
                print("\n关系范围面板内容:")
                relation_nodes = await relation_panels[1].query_selector_all('.el-tree-node')
                print(f"  关系树节点数: {len(relation_nodes)}")
                for i, node in enumerate(relation_nodes[:5]):
                    label = await node.query_selector('.el-tree-node__label')
                    if label:
                        text = await label.text_content()
                        print(f"    {text.strip()}")
            
            await page.screenshot(path='test_full_verify.png', full_page=True)
            print("\n截图已保存")
            
        except Exception as e:
            print(f"异常: {e}")
            import traceback
            traceback.print_exc()
            await page.screenshot(path='test_error.png')
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(test_full())

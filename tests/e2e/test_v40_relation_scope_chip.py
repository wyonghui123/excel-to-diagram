"""
v40 修复前端 E2E 验证 (闭环)
- 验证管理页 折叠横条 + List tab 的 "关系范围" chip 数 = 实际关系数 (非 code 数)
- 验证 折叠横条 chip = 图表页导航 chip 一致
"""
import asyncio
import os
import sys
from playwright.async_api import async_playwright

BASE_URL = "http://localhost:3004"
API_URL = "http://localhost:3010"
SCREENSHOT_DIR = "d:/filework/excel-to-diagram/test_screenshots"

os.makedirs(SCREENSHOT_DIR, exist_ok=True)

results = []


def record(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((name, passed, detail))
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


async def setup_page(context, page):
    """登录 + 进入管理页 + 选择有数据的产品/版本"""
    await page.goto(f"{API_URL}/api/v1/auth/dev-login?username=admin", wait_until="networkidle")
    await page.goto(f"{BASE_URL}/system/archdata", wait_until="networkidle")
    await page.wait_for_timeout(3000)

    # 选择 供应链管理系统
    selects = await page.query_selector_all('.gt-select')
    if len(selects) >= 1:
        await selects[0].click()
        await page.wait_for_timeout(800)
        opt = await page.query_selector('.el-select-dropdown__item:has-text("供应链管理系统")')
        if opt:
            await opt.click()
            print("    -> selected product 供应链管理系统")
        await page.wait_for_timeout(2000)

    # 选择有数据的版本 (测试版本_SUPPLY_CHAIN_4B3A)
    selects = await page.query_selector_all('.gt-select')
    if len(selects) >= 2:
        await selects[1].click()
        await page.wait_for_timeout(800)
        opt = await page.query_selector('.el-select-dropdown__item:has-text("测试版本_SUPPLY_CHAIN_4B3A")')
        if opt:
            await opt.click()
            print("    -> selected version 测试版本_SUPPLY_CHAIN_4B3A")
    await page.wait_for_timeout(5000)  # 等待关系分析


async def get_chip_text(page, panel_index):
    """获取 panel header 中的 badge 文本"""
    return await page.evaluate(f"""() => {{
        var panels = document.querySelectorAll('.collapsible-panel');
        if ({panel_index} >= panels.length) return null;
        var panel = panels[{panel_index}];
        var badge = panel.querySelector('.collapsible-panel__badge');
        return badge ? badge.textContent.trim() : null;
    }}""")


async def expand_panel(page, panel_index):
    """展开指定索引的折叠面板"""
    await page.evaluate(f"""() => {{
        var panels = document.querySelectorAll('.collapsible-panel__header');
        if ({panel_index} >= panels.length) return false;
        var evt = new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }});
        panels[{panel_index}].dispatchEvent(evt);
        return true;
    }}""")
    await page.wait_for_timeout(1500)


async def select_rss_node_by_label(page, label):
    """勾选 RSS 树中指定 label 的第一个节点"""
    return await page.evaluate(f"""() => {{
        var tree = document.querySelector('.rss-tree-container .el-tree');
        if (!tree) return 'no_tree';
        var nodes = Array.from(tree.querySelectorAll('.el-tree-node'));
        for (var n of nodes) {{
            var lbl = n.querySelector('.rss-node-label');
            if (lbl && lbl.textContent.trim() === '{label}') {{
                var cb = n.querySelector('.el-checkbox');
                if (cb) {{ cb.click(); return 'clicked: ' + lbl.textContent.trim(); }}
            }}
        }}
        return 'not_found: {label}';
    }}""")


async def get_rss_node_count(page, label):
    """获取 RSS 树中指定 label 节点的 count (括号里的数字)"""
    return await page.evaluate(f"""() => {{
        var tree = document.querySelector('.rss-tree-container .el-tree');
        if (!tree) return null;
        var nodes = Array.from(tree.querySelectorAll('.el-tree-node'));
        for (var n of nodes) {{
            var lbl = n.querySelector('.rss-node-label');
            if (lbl && lbl.textContent.trim() === '{label}') {{
                var cnt = n.querySelector('.rss-node-count');
                return cnt ? cnt.textContent.trim() : null;
            }}
        }}
        return null;
    }}""")


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await context.new_page()
        # 收集 console
        page.on("console", lambda msg: print(f"    [console.{msg.type}] {msg.text[:200]}"))

        try:
            print("=" * 60)
            print("v40 修复 E2E 验证: 关系范围 chip = 实际关系数 (非 code 数)")
            print("=" * 60)

            print("\n[1] 登录 + 进入管理页 + 选择产品/版本")
            await setup_page(context, page)

            # 截图: 初始状态
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_init.png", full_page=True)
            print(f"    -> saved screenshot v40_init.png")

            # 检查 OSS (对象范围) 数据加载
            oss_count = await page.evaluate("""() => {
                var tree = document.querySelectorAll('.collapsible-panel')[0].querySelector('.el-tree');
                if (!tree) return 0;
                return tree.querySelectorAll('.el-tree-node').length;
            }""")
            print(f"    -> 对象范围 OSS tree nodes = {oss_count}")

            # 检查 RSS (关系范围) 数据加载
            rss_count = await page.evaluate("""() => {
                var tree = document.querySelectorAll('.collapsible-panel')[1].querySelector('.el-tree');
                if (!tree) return 0;
                return tree.querySelectorAll('.el-tree-node').length;
            }""")
            print(f"    -> 关系范围 RSS tree nodes = {rss_count}")

            if rss_count == 0:
                print("\n[!] 当前版本无关系数据, 尝试 v1.0")
                # 切换版本
                selects = await page.query_selector_all('.gt-select')
                if len(selects) >= 2:
                    await selects[1].click()
                    await page.wait_for_timeout(800)
                    opt = await page.query_selector('.el-select-dropdown__item:has-text("v1.0")')
                    if opt:
                        await opt.click()
                        print("    -> switched to v1.0")
                        await page.wait_for_timeout(5000)

                rss_count = await page.evaluate("""() => {
                    var tree = document.querySelectorAll('.collapsible-panel')[1].querySelector('.el-tree');
                    if (!tree) return 0;
                    return tree.querySelectorAll('.el-tree-node').length;
                }""")
                print(f"    -> 关系范围 RSS tree nodes = {rss_count}")

            if rss_count == 0:
                print("\n[FAIL] RSS 树仍无数据, 无法验证 v40 修复")
                record("v40 RSS 数据加载", False, f"RSS tree nodes = 0")
                return

            print("\n[2] 展开对象范围 + 关系范围 panel")
            await expand_panel(page, 0)  # 对象范围
            await expand_panel(page, 1)  # 关系范围

            # 截图
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_panels_expanded.png", full_page=True)
            print(f"    -> saved screenshot v40_panels_expanded.png")

            print("\n[3] 勾选 RSS 树中 '范围内' 顶级节点 (期望选中所有内部关系)")
            result = await select_rss_node_by_label(page, "范围内")
            print(f"    -> {result}")
            await page.wait_for_timeout(2500)

            # 验证: 折叠横条 关系范围 chip 应有 badge
            chip_text = await get_chip_text(page, 1)
            print(f"    -> 关系范围 折叠横条 chip = '{chip_text}'")

            # 验证: 列表 tab 关系范围 tag
            tab_tag = await page.evaluate("""() => {
                var tags = document.querySelectorAll('.rm-filter-tag');
                for (var t of tags) {
                    if (t.textContent.indexOf('关系范围') >= 0) return t.textContent.trim();
                }
                return null;
            }""")
            print(f"    -> 关系范围 list tab tag = '{tab_tag}'")

            # 从树节点获取 "范围内" 的实际关系数
            count_from_tree = await get_rss_node_count(page, "范围内")
            print(f"    -> '范围内' 树节点 (count) = '{count_from_tree}'")

            # 从图表页获取关系数 (通过点击 图表视图 进入)
            print("\n[4] 跳转到图表页验证导航统计")
            chart_btn = await page.query_selector('button:has-text("图表视图")')
            if chart_btn:
                await chart_btn.click()
                print("    -> clicked 图表视图")
                await page.wait_for_timeout(5000)
                await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_chart_page.png", full_page=True)
                print(f"    -> saved screenshot v40_chart_page.png")

                # 提取图表页导航的 "X 关系" 统计
                nav_text = await page.evaluate("""() => {
                    // 查找 StepNavigator 中显示的 "X 关系" 文本
                    var all = document.body.textContent;
                    var m = all.match(/(\\d+)\\s*关系/);
                    return m ? m[0] : 'not_found';
                }""")
                print(f"    -> 图表页导航 关系数 = '{nav_text}'")
            else:
                nav_text = None
                print("    [!] 图表视图按钮未找到")

            # 闭环验证
            print("\n[5] 闭环对比")
            print(f"    管理页 折叠横条 chip: {chip_text}")
            print(f"    管理页 list tab tag: {tab_tag}")
            print(f"    树节点 (实际关系数): {count_from_tree}")
            print(f"    图表页导航 关系数: {nav_text}")

            # 提取数字
            def extract_n(s):
                if not s: return None
                import re
                m = re.search(r'\d+', s)
                return int(m.group()) if m else None

            chip_n = extract_n(chip_text)
            tag_n = extract_n(tab_tag)
            tree_n = extract_n(count_from_tree)
            chart_n = extract_n(nav_text)

            print(f"\n  chip_n={chip_n}, tag_n={tag_n}, tree_n={tree_n}, chart_n={chart_n}")

            # v40 核心验证: chip = tree_n (实际关系数, 不再是 code 数)
            record("v40 折叠横条 chip = 实际关系数",
                   chip_n is not None and tree_n is not None and chip_n == tree_n,
                   f"chip={chip_n}, tree_n={tree_n}")

            # 列表 tab tag 与折叠横条 chip 一致
            record("v40 list tab tag = 折叠横条 chip",
                   tag_n is not None and chip_n is not None and tag_n == chip_n,
                   f"tag={tag_n}, chip={chip_n}")

            # 跨页面一致: 图表页 = 树节点 (用户角度)
            if chart_n is not None:
                record("v40 图表页 关系数 = 树节点 关系数",
                       chart_n == tree_n,
                       f"chart={chart_n}, tree_n={tree_n}")
            else:
                record("v40 图表页验证", False, "图表页未跳转或未提取到")

        except Exception as e:
            import traceback
            traceback.print_exc()
            record("E2E 异常", False, str(e)[:200])
        finally:
            await browser.close()

    print("\n" + "=" * 60)
    print("E2E 验证结果")
    print("=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"  PASS: {passed}")
    print(f"  FAIL: {failed}")
    if failed:
        print("  Failed tests:")
        for name, ok, detail in results:
            if not ok:
                print(f"    - {name}: {detail}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())

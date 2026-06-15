"""
v40 修复 E2E 验证 v2 - 主动扫描找到有数据的版本
"""
import asyncio
import os
import re
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


async def select_product(page, product_name):
    """选择产品"""
    selects = await page.query_selector_all('.gt-select')
    if len(selects) < 1:
        return False
    await selects[0].click()
    await page.wait_for_timeout(800)
    opt = await page.query_selector(f'.el-select-dropdown__item:has-text("{product_name}")')
    if not opt:
        return False
    await opt.click()
    await page.wait_for_timeout(2000)
    return True


async def select_version(page, version_name):
    """选择版本"""
    selects = await page.query_selector_all('.gt-select')
    if len(selects) < 2:
        return False
    await selects[1].click()
    await page.wait_for_timeout(800)
    opt = await page.query_selector(f'.el-select-dropdown__item:has-text("{version_name}")')
    if not opt:
        return False
    await opt.click()
    await page.wait_for_timeout(5000)
    return True


async def has_relation_data(page):
    """检查页面是否加载了关系数据"""
    rss_count = await page.evaluate("""() => {
        var tree = document.querySelectorAll('.collapsible-panel')[1].querySelector('.el-tree');
        if (!tree) return 0;
        return tree.querySelectorAll('.el-tree-node').length;
    }""")
    return rss_count > 0


async def expand_panel(page, idx):
    """展开折叠面板"""
    await page.evaluate(f"""() => {{
        var headers = document.querySelectorAll('.collapsible-panel__header');
        if ({idx} >= headers.length) return;
        var evt = new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }});
        headers[{idx}].dispatchEvent(evt);
    }}""")
    await page.wait_for_timeout(1500)


async def select_rss_node(page, label):
    """勾选 RSS 树中指定 label"""
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


async def get_chip_text(page, panel_index):
    """获取 panel header 中的 badge 文本"""
    return await page.evaluate(f"""() => {{
        var panels = document.querySelectorAll('.collapsible-panel');
        if ({panel_index} >= panels.length) return null;
        var panel = panels[{panel_index}];
        var badge = panel.querySelector('.collapsible-panel__badge');
        return badge ? badge.textContent.trim() : null;
    }}""")


async def get_tab_tag_text(page, filter_keyword):
    """获取 list tab filter tag"""
    return await page.evaluate(f"""() => {{
        var tags = document.querySelectorAll('.rm-filter-tag');
        for (var t of tags) {{
            if (t.textContent.indexOf('{filter_keyword}') >= 0) return t.textContent.trim();
        }}
        return null;
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

        try:
            print("=" * 70)
            print("v40 修复 E2E 验证 v2 (自动扫描产品/版本)")
            print("=" * 70)

            print("\n[1] 登录")
            await page.goto(f"{API_URL}/api/v1/auth/dev-login?username=admin", wait_until="networkidle")
            await page.goto(f"{BASE_URL}/system/archdata", wait_until="networkidle")
            await page.wait_for_timeout(3000)

            # 列出所有产品
            print("\n[2] 列出可用产品")
            await page.evaluate("""() => {
                var sel = document.querySelectorAll('.gt-select')[0];
                if (sel) sel.querySelector('.el-select__wrapper').click();
            }""")
            await page.wait_for_timeout(1000)
            products = await page.evaluate("""() => {
                var items = document.querySelectorAll('.el-select-dropdown__item');
                var arr = [];
                items.forEach(function(i) { arr.push(i.textContent.trim()); });
                return arr;
            }""")
            print(f"    -> {len(products)} 个产品")

            # 找有数据的产品: 跳过测试数据
            found_product = None
            found_version = None
            # 过滤掉明显的测试数据
            skip_patterns = ['ASDFSDF', 'SDFSDF', 'placeholder', 'test_', 'TEST_', 'TEST60',
                            'TESTDEMO', 'E2E Deactivation', 'KKDL', 'TEST220', 'TEST2000',
                            'FINAL_', 'PR_', 'createdby', 'REG_PROD_', 'CASC_PROD_',
                            'AUDIT', 'SUPPLY_CHAIN', '新测试', '验证版本', 'VER_CHILD_',
                            '深度创建产品', '审计版本父产品', '审计产品', 'TEST15', 'TEST14',
                            'TEST13', '重复', 'DVU_C03']
            real_products = [p for p in products
                            if not any(s.lower() in p.lower() for s in skip_patterns)]
            print(f"    -> 过滤测试数据后剩 {len(real_products)} 个真实产品: {real_products[:10]}")

            for prod_name in real_products[:5]:
                # 关闭当前 dropdown
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(500)
                ok = await select_product(page, prod_name)
                if not ok:
                    continue

                # 列出该产品的版本
                await page.evaluate("""() => {
                    var sel = document.querySelectorAll('.gt-select')[1];
                    if (sel) sel.querySelector('.el-select__wrapper').click();
                }""")
                await page.wait_for_timeout(1000)
                versions = await page.evaluate("""() => {
                    var items = document.querySelectorAll('.el-select-dropdown__item');
                    var arr = [];
                    items.forEach(function(i) { arr.push(i.textContent.trim()); });
                    return arr;
                }""")
                print(f"    -> 产品 '{prod_name}' 有 {len(versions)} 个版本: {versions[:3]}")

                # 尝试每个版本 (最多 3 个)
                for ver_name in versions[:3]:
                    await page.keyboard.press("Escape")
                    await page.wait_for_timeout(500)
                    ok = await select_version(page, ver_name)
                    if not ok:
                        continue
                    if await has_relation_data(page):
                        found_product = prod_name
                        found_version = ver_name
                        print(f"    ✓ 找到有数据的组合: {prod_name} / {ver_name}")
                        break
                if found_product:
                    break

            if not found_product:
                print("\n[FAIL] 找不到有数据的产品/版本组合")
                record("E2E 数据准备", False, "5 产品 × 3 版本 = 15 组合均无数据")
                return

            print(f"\n[3] 验证产品/版本: {found_product} / {found_version}")
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_loaded.png", full_page=True)
            print(f"    -> saved v40_loaded.png")

            # 检查 OSS / RSS 节点
            oss_count = await page.evaluate("""() => {
                var tree = document.querySelectorAll('.collapsible-panel')[0].querySelector('.el-tree');
                if (!tree) return 0;
                return tree.querySelectorAll('.el-tree-node').length;
            }""")
            rss_count = await page.evaluate("""() => {
                var tree = document.querySelectorAll('.collapsible-panel')[1].querySelector('.el-tree');
                if (!tree) return 0;
                return tree.querySelectorAll('.el-tree-node').length;
            }""")
            print(f"    -> OSS nodes: {oss_count}, RSS nodes: {rss_count}")

            # 展开 关系范围
            print("\n[4] 展开关系范围 panel")
            await expand_panel(page, 1)
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_rss_expanded.png", full_page=True)

            # 列出可见节点
            rss_nodes = await page.evaluate("""() => {
                var tree = document.querySelector('.rss-tree-container .el-tree');
                if (!tree) return [];
                var nodes = Array.from(tree.querySelectorAll('.el-tree-node'));
                return nodes.slice(0, 10).map(function(n) {
                    var lbl = n.querySelector('.rss-node-label');
                    var cnt = n.querySelector('.rss-node-count');
                    return (lbl ? lbl.textContent.trim() : '?') + ' | ' + (cnt ? cnt.textContent.trim() : 'no_count');
                });
            }""")
            print(f"    -> RSS 可见节点 (前 10): {rss_nodes}")

            # 勾选第一个有 count 的节点
            print("\n[5] 勾选 RSS 节点 (找第一个有 count 的)")
            target_label = None
            target_count = None
            for node_str in rss_nodes:
                parts = node_str.split('|')
                if len(parts) == 2 and parts[1].strip() != 'no_count':
                    m = re.search(r'\d+', parts[1])
                    if m and int(m.group()) > 0:
                        target_label = parts[0].strip()
                        target_count = parts[1].strip()
                        break

            if not target_label:
                print("    [!] 没有找到带 count 的可勾选节点, 尝试 范围内")
                result = await select_rss_node(page, "范围内")
                target_label = "范围内"
                target_count = await get_rss_node_count(page, "范围内")
            else:
                result = await select_rss_node(page, target_label)
            print(f"    -> {result} | tree count: {target_count}")
            await page.wait_for_timeout(2500)

            chip_text = await get_chip_text(page, 1)
            tab_tag = await get_tab_tag_text(page, "关系范围")
            print(f"    -> 折叠横条 chip: '{chip_text}'")
            print(f"    -> list tab tag: '{tab_tag}'")
            print(f"    -> 树节点 count: '{target_count}'")

            # 提取数字
            def extract_n(s):
                if not s: return None
                m = re.search(r'\d+', s)
                return int(m.group()) if m else None

            chip_n = extract_n(chip_text)
            tag_n = extract_n(tab_tag)
            tree_n = extract_n(target_count)

            # ===== 闭环验证 =====
            print("\n[6] 闭环验证 (管理页 chip 跟树节点和图表页一致)")
            record("折叠横条 chip = 树节点 count (关系数, 非 code 数)",
                   chip_n is not None and tree_n is not None and chip_n == tree_n,
                   f"chip={chip_n}, tree_n={tree_n}")
            record("list tab tag = 折叠横条 chip",
                   tag_n is not None and chip_n is not None and tag_n == chip_n,
                   f"tag={tag_n}, chip={chip_n}")

            # 跳图表页验证
            print("\n[7] 跳图表页验证导航统计")
            chart_btn = await page.query_selector('button:has-text("图表视图")')
            if chart_btn:
                await chart_btn.click()
                await page.wait_for_timeout(5000)
                await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_chart.png", full_page=True)
                nav_text = await page.evaluate("""() => {
                    var all = document.body.textContent;
                    var m = all.match(/(\\d+)\\s*关系/);
                    return m ? m[0] : 'not_found';
                }""")
                chart_n = extract_n(nav_text)
                print(f"    -> 图表页导航 关系数: '{nav_text}' (= {chart_n})")
                record("图表页 关系数 = 树节点 关系数 (跨页面闭环)",
                       chart_n is not None and tree_n is not None and chart_n == tree_n,
                       f"chart={chart_n}, tree_n={tree_n}")
            else:
                print("    [!] 图表视图按钮未找到")

        except Exception as e:
            import traceback
            traceback.print_exc()
            record("E2E 异常", False, str(e)[:200])
        finally:
            await browser.close()

    print("\n" + "=" * 70)
    print("E2E 验证结果")
    print("=" * 70)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = sum(1 for _, ok, _ in results if not ok)
    print(f"  PASS: {passed}  |  FAIL: {failed}")
    for name, ok, detail in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    asyncio.run(main())

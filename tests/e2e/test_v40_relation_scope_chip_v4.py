"""
v40 修复 E2E 验证 v4 - 简化版
直接通过 UI 找到有数据的版本, 跳过 dropdown 选择困难
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


async def try_combination(page, product_name, version_name):
    """尝试一个产品/版本组合, 返回是否有关系数据"""
    # 选产品
    selects = await page.query_selector_all('.gt-select')
    if not selects:
        return False, "no_selects"
    await selects[0].click()
    await page.wait_for_timeout(800)
    opt = await page.query_selector(f'.el-select-dropdown__item:has-text("{product_name}")')
    if not opt:
        return False, f"product_not_found: {product_name}"
    await opt.click()
    await page.wait_for_timeout(2000)

    # 选版本
    selects = await page.query_selector_all('.gt-select')
    if len(selects) < 2:
        return False, "no_version_select"
    await selects[1].click()
    await page.wait_for_timeout(800)
    opt = await page.query_selector(f'.el-select-dropdown__item:has-text("{version_name}")')
    if not opt:
        return False, f"version_not_found: {version_name}"
    await opt.click()
    await page.wait_for_timeout(6000)

    # 检查数据
    rss_count = await page.evaluate("""() => {
        var panels = document.querySelectorAll('.collapsible-panel');
        if (panels.length < 2) return 0;
        var tree = panels[1].querySelector('.el-tree');
        if (!tree) return 0;
        return tree.querySelectorAll('.el-tree-node').length;
    }""")
    return rss_count > 0, f"rss={rss_count}"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await context.new_page()

        try:
            print("=" * 70)
            print("v40 修复 E2E 验证 v4 (UI 全流程)")
            print("=" * 70)

            # 登录
            await page.goto(f"{API_URL}/api/v1/auth/dev-login?username=admin", wait_until="networkidle")
            await page.goto(f"{BASE_URL}/system/archdata", wait_until="networkidle")
            await page.wait_for_timeout(4000)

            # 扫描可用产品+版本
            print("\n[1] 扫描有数据的产品+版本")

            # 取产品列表
            await page.evaluate("""() => {
                var sel = document.querySelectorAll('.gt-select')[0];
                if (sel) sel.querySelector('.el-select__wrapper').click();
            }""")
            await page.wait_for_timeout(1500)
            products = await page.evaluate("""() => {
                return Array.from(document.querySelectorAll('.el-select-dropdown__item')).map(i => i.textContent.trim());
            }""")
            print(f"    产品数: {len(products)}")
            # 关闭 dropdown
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)

            # 跳过后 10 个产品, 每个取 1 个版本 (优先 v1.0 / v1 / 第一个非测试)
            skip_patterns = ['ASDFSDF', 'SDFSDF', 'placeholder', 'TEST_', 'TEST60', 'TESTDEMO',
                            'AUDIT', '深度创建', '审计版本', '供应链', '审计产品', '重复',
                            'DVU_C03', '新测试', '验证版本', 'PR_', 'createdby', 'REG_PROD_',
                            'CASC_PROD_', 'TEST15', 'TEST14', 'TEST13', 'TEST220', 'TEST2000',
                            'KKDL', 'E2E Deactivation', 'VER_CHILD', 'FINAL_', 'TESTPROD_',
                            'TESTPROD_07B71B', 'TESTPROD_BE22EA', 'TESTPROD_298B55']

            found = False
            tried = 0
            for prod in products[10:50]:  # 跳过前 10 个明显的测试产品
                if any(s.lower() in prod.lower() for s in skip_patterns):
                    continue
                # 取该产品的版本
                await page.evaluate("""() => {
                    var sel = document.querySelectorAll('.gt-select')[0];
                    if (sel) sel.querySelector('.el-select__wrapper').click();
                }""")
                await page.wait_for_timeout(1000)
                opt = await page.query_selector(f'.el-select-dropdown__item:has-text("{prod}")')
                if not opt:
                    continue
                await opt.click()
                await page.wait_for_timeout(2000)

                # 取版本
                await page.evaluate("""() => {
                    var sel = document.querySelectorAll('.gt-select')[1];
                    if (sel) sel.querySelector('.el-select__wrapper').click();
                }""")
                await page.wait_for_timeout(1000)
                versions = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('.el-select-dropdown__item')).map(i => i.textContent.trim());
                }""")
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(500)

                # 跳过测试版本
                real_versions = [v for v in versions
                                if not any(s.lower() in v.lower() for s in skip_patterns)]
                if not real_versions:
                    continue

                # 尝试第一个真实版本
                ver = real_versions[0]
                print(f"    -> 尝试: {prod[:25]} / {ver[:25]}")
                ok, info = await try_combination(page, prod, ver)
                tried += 1
                if ok:
                    print(f"    ✓ 找到有数据: {prod} / {ver} ({info})")
                    found = True
                    break
                if tried >= 3:
                    break

            if not found:
                # 最后尝试: 用 API 找 version_id=1 对应的产品
                print("\n    尝试 供应链管理系统 (我们已知 version_id=1 在此产品下)")
                # 先回到初始状态
                await page.goto(f"{BASE_URL}/system/archdata", wait_until="networkidle")
                await page.wait_for_timeout(3000)

                # 直接选 供应链管理系统
                selects = await page.query_selector_all('.gt-select')
                if selects:
                    await selects[0].click()
                    await page.wait_for_timeout(800)
                    opt = await page.query_selector('.el-select-dropdown__item:has-text("供应链管理系统")')
                    if opt:
                        await opt.click()
                        print("    -> 选 供应链管理系统")
                        await page.wait_for_timeout(3000)

                # 选版本 - 跳过 ASDFSDF 系列, 优先 v1.0
                selects = await page.query_selector_all('.gt-select')
                if len(selects) >= 2:
                    # 优先 v1.0
                    for target_ver in ['v1.0', 'v1', '1.0', '1']:
                        try:
                            await page.locator('.gt-select').nth(1).locator('input').fill(target_ver)
                            await page.wait_for_timeout(1000)
                            opt = page.locator(f'.el-select-dropdown__item:has-text("{target_ver}")').first
                            if await opt.count() > 0:
                                await opt.click(force=True)
                                print(f"    -> 选版本: {target_ver}")
                                await page.wait_for_timeout(6000)
                                rss_count = await page.evaluate("""() => {
                                    var tree = document.querySelectorAll('.collapsible-panel')[1]?.querySelector('.el-tree');
                                    if (!tree) return 0;
                                    return tree.querySelectorAll('.el-tree-node').length;
                                }""")
                                if rss_count > 0:
                                    print(f"    ✓ 找到: 供应链管理系统 / {target_ver}, RSS={rss_count}")
                                    found = True
                                    break
                        except Exception as e:
                            print(f"    试 {target_ver} 失败: {e}")

            if not found:
                print("\n[FAIL] 数据准备失败")
                record("数据准备", False, "找不到有数据的版本")
                return

            # 截图
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_v4_loaded.png", full_page=True)

            # 展开 panel
            print("\n[2] 展开 panel")
            for idx in [0, 1]:
                await page.evaluate(f"""() => {{
                    var headers = document.querySelectorAll('.collapsible-panel__header');
                    if ({idx} >= headers.length) return;
                    var evt = new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }});
                    headers[{idx}].dispatchEvent(evt);
                }}""")
                await page.wait_for_timeout(2000)
            print("    -> panels expanded")
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_v4_expanded.png", full_page=True)

            # 列出 RSS 节点
            rss_nodes = await page.evaluate("""() => {
                var tree = document.querySelector('.rss-tree-container .el-tree');
                if (!tree) return [];
                return Array.from(tree.querySelectorAll('.el-tree-node')).slice(0, 15).map(function(n) {
                    var lbl = n.querySelector('.rss-node-label');
                    var cnt = n.querySelector('.rss-node-count');
                    return (lbl ? lbl.textContent.trim() : '?') + ' | ' + (cnt ? cnt.textContent.trim() : 'no_count');
                });
            }""")
            print(f"\n[3] RSS 节点:")
            for n in rss_nodes:
                print(f"    {n}")

            # 找第一个有 count 的节点
            target_label = None
            for node_str in rss_nodes:
                parts = node_str.split('|')
                if len(parts) == 2 and parts[1].strip() != 'no_count':
                    m = re.search(r'\d+', parts[1])
                    if m and int(m.group()) > 0:
                        target_label = parts[0].strip()
                        break

            if not target_label:
                target_label = "范围内"

            print(f"\n[4] 勾选节点: {target_label}")
            click_result = await page.evaluate(f"""() => {{
                var tree = document.querySelector('.rss-tree-container .el-tree');
                if (!tree) return 'no_tree';
                var nodes = Array.from(tree.querySelectorAll('.el-tree-node'));
                for (var n of nodes) {{
                    var lbl = n.querySelector('.rss-node-label');
                    if (lbl && lbl.textContent.trim() === '{target_label}') {{
                        var cb = n.querySelector('.el-checkbox');
                        if (cb) {{ cb.click(); return 'clicked: ' + lbl.textContent.trim(); }}
                    }}
                }}
                return 'not_found: {target_label}';
            }}""")
            print(f"    -> {click_result}")
            await page.wait_for_timeout(3000)

            # 获取 chip / tag / tree count
            data = await page.evaluate("""() => {
                var panels = document.querySelectorAll('.collapsible-panel');
                var panel = panels[1];
                var badge = panel.querySelector('.collapsible-panel__badge');
                var chip = badge ? badge.textContent.trim() : null;
                var tag = null;
                document.querySelectorAll('.rm-filter-tag').forEach(function(t) {
                    if (t.textContent.indexOf('关系范围') >= 0) tag = t.textContent.trim();
                });
                return { chip: chip, tag: tag };
            }""")

            tree_count_str = await page.evaluate(f"""() => {{
                var tree = document.querySelector('.rss-tree-container .el-tree');
                if (!tree) return null;
                var nodes = Array.from(tree.querySelectorAll('.el-tree-node'));
                for (var n of nodes) {{
                    var lbl = n.querySelector('.rss-node-label');
                    if (lbl && lbl.textContent.trim() === '{target_label}') {{
                        var cnt = n.querySelector('.rss-node-count');
                        return cnt ? cnt.textContent.trim() : null;
                    }}
                }}
                return null;
            }}""")

            print(f"\n[5] 提取统计")
            print(f"    折叠横条 chip: {data['chip']}")
            print(f"    list tab tag:  {data['tag']}")
            print(f"    树节点 count:  {tree_count_str}")

            def extract_n(s):
                if not s: return None
                m = re.search(r'\d+', s)
                return int(m.group()) if m else None

            chip_n = extract_n(data['chip'])
            tag_n = extract_n(data['tag'])
            tree_n = extract_n(tree_count_str)

            print(f"\n[6] 闭环验证 (chip_n={chip_n}, tag_n={tag_n}, tree_n={tree_n})")
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_v4_selected.png", full_page=True)

            record("v40 折叠横条 chip = 实际关系数 (tree_n)",
                   chip_n is not None and tree_n is not None and chip_n == tree_n,
                   f"chip={chip_n}, tree_n={tree_n}")
            record("v40 list tab tag = 折叠横条 chip",
                   tag_n is not None and chip_n is not None and tag_n == chip_n,
                   f"tag={tag_n}, chip={chip_n}")

            # 跳图表页
            print("\n[7] 跳图表页")
            chart_btn = await page.query_selector('button:has-text("图表视图")')
            if chart_btn:
                await chart_btn.click()
                print("    -> clicked 图表视图")
                await page.wait_for_timeout(6000)
                await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_v4_chart.png", full_page=True)
                nav_text = await page.evaluate("""() => {
                    var m = document.body.textContent.match(/(\\d+)\\s*关系/);
                    return m ? m[0] : 'not_found';
                }""")
                chart_n = extract_n(nav_text)
                print(f"    -> 图表页 关系数: {nav_text} (={chart_n})")
                record("v40 图表页 关系数 = 树节点 关系数 (跨页面闭环)",
                       chart_n is not None and tree_n is not None and chart_n == tree_n,
                       f"chart={chart_n}, tree_n={tree_n}")
            else:
                record("图表页跳转", False, "图表视图按钮未找到")

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

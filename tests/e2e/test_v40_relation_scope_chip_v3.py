"""
v40 修复 E2E 验证 v3 - 使用 sessionStorage 注入选中的产品/版本
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


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await context.new_page()
        page.on("console", lambda msg: print(f"    [console.{msg.type[:4]}] {msg.text[:200]}") if msg.type in ('error', 'warning') else None)

        try:
            print("=" * 70)
            print("v40 修复 E2E 验证 v3 (sessionStorage 注入)")
            print("=" * 70)

            print("\n[1] 登录")
            await page.goto(f"{API_URL}/api/v1/auth/dev-login?username=admin", wait_until="networkidle")
            print("    -> dev-login OK")

            # 通过 API 找有数据的版本和对应的产品
            print("\n[2] 通过 API 找有数据的版本")
            api_data = await page.evaluate(f"""async () => {{
                // 通过 fetch 找数据
                const r = await fetch('{API_URL}/api/v1/relationships?page=1&page_size=20');
                const j = await r.json();
                return j;
            }}""")
            items = api_data.get('data', [])
            total = api_data.get('total', 0)
            print(f"    -> total={total}, items={len(items)}")
            if not items:
                print("    [FAIL] 无数据")
                record("数据准备", False, "API 返回 0 关系")
                return

            # 按 version_id 分组
            versions = {}
            for it in items:
                vid = it.get('version_id')
                if vid:
                    versions[vid] = versions.get(vid, 0) + 1
            print(f"    -> versions with data: {versions}")

            # 选最大数据量的版本
            target_version_id = max(versions, key=versions.get)
            print(f"    -> target version_id: {target_version_id} ({versions[target_version_id]} relations)")

            # 用 version_id=1 (有 BO_REQ-BO_LOCATION 数据, 真实数据)
            target_version_id = 1
            print(f"    -> 使用 version_id={target_version_id}")

            # 直接导航到管理页, 然后用 JavaScript 设置选中的产品/版本
            print("\n[3] 导航到管理页, 直接通过 JS 设置 store")
            await page.goto(f"{BASE_URL}/system/archdata", wait_until="networkidle")
            await page.wait_for_timeout(3000)

            # 通过 sessionStorage 设置 productId/versionId (这是 useVersionContext 的存储 key)
            await page.evaluate(f"""() => {{
                // 触发 useVersionContext 的初始化
                localStorage.setItem('arch_product_id', '1');
                localStorage.setItem('arch_version_id', '{target_version_id}');
                sessionStorage.setItem('arch_product_id', '1');
                sessionStorage.setItem('arch_version_id', '{target_version_id}');
            }}""")
            print("    -> set localStorage arch_product_id=1, arch_version_id=1")

            # 刷新页面让 store 重新加载
            await page.reload(wait_until="networkidle")
            await page.wait_for_timeout(5000)

            # 检查页面是否有数据
            rss_count = await page.evaluate("""() => {
                var tree = document.querySelectorAll('.collapsible-panel')[1].querySelector('.el-tree');
                if (!tree) return 0;
                return tree.querySelectorAll('.el-tree-node').length;
            }""")
            oss_count = await page.evaluate("""() => {
                var tree = document.querySelectorAll('.collapsible-panel')[0].querySelector('.el-tree');
                if (!tree) return 0;
                return tree.querySelectorAll('.el-tree-node').length;
            }""")
            print(f"    -> OSS nodes: {oss_count}, RSS nodes: {rss_count}")

            # 截图
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_v3_loaded.png", full_page=True)

            if rss_count == 0 and oss_count == 0:
                # 试一下手动选 (用点击 + 等更久)
                print("\n    [!] sessionStorage 未生效, 改用手动选择")
                # 选 供应链管理系统
                selects = await page.query_selector_all('.gt-select')
                if len(selects) >= 1:
                    await selects[0].click()
                    await page.wait_for_timeout(1000)
                    opt = await page.query_selector('.el-select-dropdown__item:has-text("供应链管理系统")')
                    if opt:
                        await opt.click()
                        print("    -> selected product 供应链管理系统")
                        await page.wait_for_timeout(3000)

                # 选版本 (找有数据的)
                selects = await page.query_selector_all('.gt-select')
                if len(selects) >= 2:
                    await selects[1].click()
                    await page.wait_for_timeout(1000)
                    # 取前 5 个版本依次尝试
                    opts = await page.query_selector_all('.el-select-dropdown__item')
                    for opt in opts[:10]:
                        txt = await opt.text_content()
                        # 跳过测试数据
                        if any(s in txt for s in ['ASDFSDF', 'SDFSDF', 'placeholder', 'TEST_', 'AUDIT', '深度创建', '审计版本', '供应链', '审计产品', '重复', 'DVU_C03', '新测试', '验证版本']):
                            continue
                        print(f"    -> trying version: {txt.strip()[:30]}")
                        await opt.click()
                        await page.wait_for_timeout(5000)
                        rss_count = await page.evaluate("""() => {
                            var tree = document.querySelectorAll('.collapsible-panel')[1].querySelector('.el-tree');
                            if (!tree) return 0;
                            return tree.querySelectorAll('.el-tree-node').length;
                        }""")
                        if rss_count > 0:
                            print(f"    ✓ 找到有数据的版本: {txt.strip()[:30]}, RSS={rss_count}")
                            break

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
            print(f"    -> 最终: OSS nodes: {oss_count}, RSS nodes: {rss_count}")

            if rss_count == 0:
                print("\n[FAIL] 找不到有数据的版本, 无法验证")
                record("E2E 数据准备", False, f"RSS nodes = 0 (tried 10 versions)")
                return

            # 截图
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_v3_ready.png", full_page=True)
            print(f"    -> saved v40_v3_ready.png")

            # 展开两个 panel
            print("\n[4] 展开 对象范围 + 关系范围 panel")
            for idx in [0, 1]:
                await page.evaluate(f"""() => {{
                    var headers = document.querySelectorAll('.collapsible-panel__header');
                    if ({idx} >= headers.length) return;
                    var evt = new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }});
                    headers[{idx}].dispatchEvent(evt);
                }}""")
                await page.wait_for_timeout(1500)
            print("    -> panels expanded")

            # 列出 RSS 树可见节点
            print("\n[5] 列出 RSS 树节点")
            rss_nodes = await page.evaluate("""() => {
                var tree = document.querySelector('.rss-tree-container .el-tree');
                if (!tree) return [];
                var nodes = Array.from(tree.querySelectorAll('.el-tree-node'));
                return nodes.slice(0, 15).map(function(n) {
                    var lbl = n.querySelector('.rss-node-label');
                    var cnt = n.querySelector('.rss-node-count');
                    return (lbl ? lbl.textContent.trim() : '?') + ' | ' + (cnt ? cnt.textContent.trim() : 'no_count');
                });
            }""")
            for n in rss_nodes:
                print(f"    -> {n}")

            # 找到第一个有 count 的节点
            target_label = None
            target_count_str = None
            for node_str in rss_nodes:
                parts = node_str.split('|')
                if len(parts) == 2 and parts[1].strip() != 'no_count':
                    m = re.search(r'\d+', parts[1])
                    if m and int(m.group()) > 0:
                        target_label = parts[0].strip()
                        target_count_str = parts[1].strip()
                        break

            if not target_label:
                # 试 "范围内"
                target_label = "范围内"

            print(f"\n[6] 勾选节点: '{target_label}' (count: {target_count_str})")
            result = await page.evaluate(f"""() => {{
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
            print(f"    -> {result}")
            await page.wait_for_timeout(2500)

            # 获取 chip
            chip_text = await page.evaluate("""() => {
                var panels = document.querySelectorAll('.collapsible-panel');
                var panel = panels[1];
                var badge = panel.querySelector('.collapsible-panel__badge');
                return badge ? badge.textContent.trim() : null;
            }""")
            tab_tag = await page.evaluate("""() => {
                var tags = document.querySelectorAll('.rm-filter-tag');
                for (var t of tags) {
                    if (t.textContent.indexOf('关系范围') >= 0) return t.textContent.trim();
                }
                return null;
            }""")

            # 获取树节点 count (重新获取, 防止变化)
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

            print(f"\n[7] 提取统计")
            print(f"    折叠横条 chip: '{chip_text}'")
            print(f"    list tab tag: '{tab_tag}'")
            print(f"    树节点 count: '{tree_count_str}'")

            def extract_n(s):
                if not s: return None
                m = re.search(r'\d+', s)
                return int(m.group()) if m else None

            chip_n = extract_n(chip_text)
            tag_n = extract_n(tab_tag)
            tree_n = extract_n(tree_count_str)

            # 验证
            print(f"\n[8] 闭环验证")
            print(f"    chip_n={chip_n}, tag_n={tag_n}, tree_n={tree_n}")

            record("v40 折叠横条 chip = 树节点 count (关系数, 非 code 数)",
                   chip_n is not None and tree_n is not None and chip_n == tree_n,
                   f"chip={chip_n}, tree_n={tree_n}")
            record("v40 list tab tag = 折叠横条 chip",
                   tag_n is not None and chip_n is not None and tag_n == chip_n,
                   f"tag={tag_n}, chip={chip_n}")

            # 跨页面验证
            print("\n[9] 跳图表页验证")
            chart_btn = await page.query_selector('button:has-text("图表视图")')
            if chart_btn:
                await chart_btn.click()
                print("    -> clicked 图表视图")
                await page.wait_for_timeout(6000)
                await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_v3_chart.png", full_page=True)
                nav_text = await page.evaluate("""() => {
                    var all = document.body.textContent;
                    var m = all.match(/(\\d+)\\s*关系/);
                    return m ? m[0] : 'not_found';
                }""")
                chart_n = extract_n(nav_text)
                print(f"    -> 图表页导航 关系数: '{nav_text}' (={chart_n})")
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

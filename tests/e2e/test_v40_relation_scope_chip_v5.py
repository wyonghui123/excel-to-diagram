"""
v40 修复 E2E 验证 v5 - 直接通过 JS 触发 el-select 选择 (绕开虚拟滚动问题)
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

        try:
            print("=" * 70)
            print("v40 修复 E2E 验证 v5 (useVersionContext 内部状态直接设置)")
            print("=" * 70)

            print("\n[1] 登录")
            await page.goto(f"{API_URL}/api/v1/auth/dev-login?username=admin", wait_until="networkidle")
            await page.goto(f"{BASE_URL}/system/archdata", wait_until="networkidle")
            await page.wait_for_timeout(4000)

            # 找对应的 product_id/version_id
            print("\n[2] 通过 API 找 product_id (含 version_id=1)")
            info = await page.evaluate(f"""async () => {{
                try {{
                    const r1 = await fetch('{API_URL}/api/v1/relationships?version_id=1&page=1&page_size=1');
                    const j1 = await r1.json();
                    return {{ total: j1.total, item: j1.data && j1.data[0] }};
                }} catch (e) {{
                    return {{ error: e.message }};
                }}
            }}""")
            print(f"    -> info: {info}")
            if 'error' in info:
                print(f"    [FAIL] API 调用失败: {info['error']}")
                record("API 调用", False, info['error'])
                return
            item = info.get('item') or {{}}
            print(f"    -> first item: {item.get('source_bo_name', '?')}")

            # 通过 select 的 vue instance 找 product_id
            print("\n[3] 找 Pinia store 内部 state")
            stores_dump = await page.evaluate("""() => {
                var app = document.querySelector('#app')?.__vue_app__;
                if (!app) return 'no_app';
                var pinia = app.config.globalProperties.$pinia;
                return JSON.stringify(Array.from(pinia._s.keys()));
            }""")
            print(f"    -> stores: {stores_dump}")

            # 通过 dropdown 显示 + 直接设置 model
            print("\n[4] 直接通过 Vue 设置 product_id/version_id")
            # 先正常点开 product dropdown, 然后用 el-select 的底层 model 直接 set
            await page.evaluate("""() => {
                var app = document.querySelector('#app').__vue_app__;
                var pinia = app.config.globalProperties.$pinia;

                // 找 versionContext
                var ctx = null;
                for (var key of pinia._s.keys()) {
                    var s = pinia._s.get(key);
                    if (s && s.versions && s.products) {
                        ctx = s;
                        console.log('Found versionContext in store:', key);
                        break;
                    }
                }
                if (ctx && ctx.products && ctx.products.length > 0) {
                    // 找含 "供应链" 的产品
                    var supply = ctx.products.find(p => p.name && p.name.indexOf('供应链') >= 0);
                    if (supply) {
                        ctx.selectProduct(supply);
                        console.log('Selected product:', supply.name);
                    }
                }
            }""")
            await page.wait_for_timeout(5000)
            print("    -> selected 供应链")

            # 找 v1.0 version
            await page.evaluate("""() => {
                var app = document.querySelector('#app').__vue_app__;
                var pinia = app.config.globalProperties.$pinia;
                for (var key of pinia._s.keys()) {
                    var s = pinia._s.get(key);
                    if (s && s.versions && s.products) {
                        var v = s.versions.find(v => v.name && (v.name === 'v1.0' || v.name === 'V1.0' || v.id === 1));
                        if (v) {
                            s.selectVersion(v);
                            console.log('Selected version:', v.name, 'id:', v.id);
                        }
                    }
                }
            }""")
            await page.wait_for_timeout(8000)
            print("    -> selected v1.0 / version_id=1")

            # 截图
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_v5_loaded.png", full_page=True)

            # 检查数据
            data_state = await page.evaluate("""() => {
                var panels = document.querySelectorAll('.collapsible-panel');
                if (panels.length < 2) return { error: 'panels=' + panels.length };
                var oss = panels[0].querySelector('.el-tree');
                var rss = panels[1].querySelector('.el-tree');
                return {
                    ossNodes: oss ? oss.querySelectorAll('.el-tree-node').length : 0,
                    rssNodes: rss ? rss.querySelectorAll('.el-tree-node').length : 0
                };
            }""")
            print(f"\n[5] 数据状态: {data_state}")

            if data_state.get('rssNodes', 0) == 0:
                print("    [FAIL] 仍无 RSS 数据")
                record("数据加载", False, str(data_state))
                return

            # 展开两个 panel
            print("\n[6] 展开 panel")
            for idx in [0, 1]:
                await page.evaluate(f"""() => {{
                    var headers = document.querySelectorAll('.collapsible-panel__header');
                    if ({idx} >= headers.length) return;
                    var evt = new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }});
                    headers[{idx}].dispatchEvent(evt);
                }}""")
                await page.wait_for_timeout(2000)
            print("    -> expanded")
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_v5_expanded.png", full_page=True)

            # 列 RSS 节点
            rss_nodes = await page.evaluate("""() => {
                var tree = document.querySelector('.rss-tree-container .el-tree');
                if (!tree) return [];
                return Array.from(tree.querySelectorAll('.el-tree-node')).slice(0, 20).map(function(n) {
                    var lbl = n.querySelector('.rss-node-label');
                    var cnt = n.querySelector('.rss-node-count');
                    return (lbl ? lbl.textContent.trim() : '?') + ' | ' + (cnt ? cnt.textContent.trim() : 'no_count');
                });
            }""")
            print(f"\n[7] RSS 节点:")
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

            print(f"\n[8] 勾选节点: {target_label}")
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

            # 提取
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

            print(f"\n[9] 统计:")
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

            print(f"\n[10] 闭环验证 (chip_n={chip_n}, tag_n={tag_n}, tree_n={tree_n})")
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_v5_selected.png", full_page=True)

            record("v40 折叠横条 chip = 实际关系数 (tree_n, 非 code 数)",
                   chip_n is not None and tree_n is not None and chip_n == tree_n,
                   f"chip={chip_n}, tree_n={tree_n}")
            record("v40 list tab tag = 折叠横条 chip",
                   tag_n is not None and chip_n is not None and tag_n == chip_n,
                   f"tag={tag_n}, chip={chip_n}")

            # 跨页面
            print("\n[11] 跳图表页验证")
            chart_btn = await page.query_selector('button:has-text("图表视图")')
            if chart_btn:
                await chart_btn.click()
                print("    -> clicked 图表视图")
                await page.wait_for_timeout(6000)
                await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_v5_chart.png", full_page=True)
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

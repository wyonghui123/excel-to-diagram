"""
v40 修复 E2E 验证 v6 - 修复 v5 的 bug
  - 修复 line 56 'item = info.get('item') or {{}}' (set of dict) → 'or {}'
  - 加完整 traceback
  - 直接通过 Pinia store 选 product/version (绕开 UI dropdown 虚拟滚动)
  - 验证: 折叠横条 chip = list tab tag = 树节点 count = 图表页导航 关系数
"""
import asyncio
import os
import re
import sys
import traceback
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


def extract_n(s):
    if not s:
        return None
    m = re.search(r'\d+', s)
    return int(m.group()) if m else None


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1600, "height": 900})
        page = await context.new_page()

        try:
            print("=" * 70)
            print("v40 修复 E2E 验证 v6")
            print("=" * 70)

            # 1. 登录
            print("\n[1] 登录 + 进入架构管理页 (带 productId/versionId URL 参数, 让 versionContext 自动恢复)")
            await page.goto(f"{API_URL}/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded")
            await page.goto(f"{BASE_URL}/system/archdata?productId=1&versionId=1", wait_until="domcontentloaded")
            await page.wait_for_timeout(10000)  # 等页面完整加载

            # 2. 直接通过 Pinia store 选产品+版本
            print("\n[2] 通过 Pinia store 选产品+版本")
            setup_result = await page.evaluate("""() => {
                var app = document.querySelector('#app')?.__vue_app__;
                if (!app) return 'no_app';
                var pinia = app.config.globalProperties.$pinia;

                var ctx = null;
                for (var key of pinia._s.keys()) {
                    var s = pinia._s.get(key);
                    if (s && s.versions && s.products) {
                        ctx = s;
                        break;
                    }
                }
                if (!ctx) return 'no_ctx';

                // 选 供应链管理系统 (id=1)
                var product = ctx.products.find(p => p.id === 1);
                if (!product) {
                    // 如果 products 还没加载, 触发 fetch
                    if (ctx.fetchProducts) {
                        return 'products_not_loaded, count=' + (ctx.products?.length || 0);
                    }
                    return 'product_1_not_found';
                }
                ctx.selectProduct(product);

                return 'selected_product: ' + product.name + ', versions_loaded=' + (ctx.versions?.length || 0);
            }""")
            print(f"    -> {setup_result}")
            await page.wait_for_timeout(3000)

            # 选 version id=1
            setup_v2 = await page.evaluate("""() => {
                var app = document.querySelector('#app').__vue_app__;
                var pinia = app.config.globalProperties.$pinia;
                for (var key of pinia._s.keys()) {
                    var s = pinia._s.get(key);
                    if (s && s.versions && s.products) {
                        var v = s.versions.find(v => v.id === 1);
                        if (v) {
                            s.selectVersion(v);
                            return 'selected_version: ' + v.name + ' (id=' + v.id + ')';
                        }
                        return 'version_id=1_not_found, available=' + JSON.stringify(s.versions.map(x => x.id));
                    }
                }
                return 'no_ctx';
            }""")
            print(f"    -> {setup_v2}")
            await page.wait_for_timeout(8000)
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_v6_loaded.png", full_page=True)

            # 3. 验证 RSS 树加载
            print("\n[3] 验证 RSS 树加载")
            data_state = await page.evaluate("""() => {
                var panels = document.querySelectorAll('.collapsible-panel');
                if (panels.length < 2) {
                    return {
                        error: 'panels=' + panels.length,
                        url: location.href,
                        allClasses: Array.from(document.querySelectorAll('[class*="collapsible"]')).map(e => e.className).slice(0, 5),
                        bodySample: document.body.innerHTML.substring(0, 800)
                    };
                }
                var oss = panels[0].querySelector('.el-tree');
                var rss = panels[1].querySelector('.el-tree');
                return {
                    ossNodes: oss ? oss.querySelectorAll('.el-tree-node').length : 0,
                    rssNodes: rss ? rss.querySelectorAll('.el-tree-node').length : 0
                };
            }""")
            print(f"    -> {data_state}")
            if data_state.get('rssNodes', 0) == 0:
                record("数据加载", False, str(data_state))
                return

            # 4. 展开 panel
            print("\n[4] 展开 panel (关系范围)")
            for idx in [0, 1]:
                await page.evaluate(f"""() => {{
                    var headers = document.querySelectorAll('.collapsible-panel__header');
                    if ({idx} >= headers.length) return;
                    var evt = new MouseEvent('click', {{ bubbles: true, cancelable: true, view: window }});
                    headers[{idx}].dispatchEvent(evt);
                }}""")
                await page.wait_for_timeout(2000)
            print("    -> expanded")
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_v6_expanded.png", full_page=True)

            # 5. 列 RSS 节点, 找第一个有 count > 0 的节点
            print("\n[5] 列出 RSS 树节点")
            rss_nodes = await page.evaluate("""() => {
                var tree = document.querySelector('.rss-tree-container .el-tree');
                if (!tree) return [];
                return Array.from(tree.querySelectorAll('.el-tree-node')).slice(0, 25).map(function(n) {
                    var lbl = n.querySelector('.rss-node-label');
                    var cnt = n.querySelector('.rss-node-count');
                    return (lbl ? lbl.textContent.trim() : '?') + ' | ' + (cnt ? cnt.textContent.trim() : 'no_count');
                });
            }""")
            for n in rss_nodes:
                print(f"    {n}")

            # 找第一个有 count > 0 的节点
            target_label = None
            for node_str in rss_nodes:
                parts = node_str.split('|')
                if len(parts) == 2 and parts[1].strip() != 'no_count':
                    m = re.search(r'\d+', parts[1])
                    if m and int(m.group()) > 0:
                        target_label = parts[0].strip()
                        break

            if not target_label:
                # 兜底: 取第一个节点
                target_label = "范围内"
            print(f"\n[6] 目标节点: {target_label}")

            # 7. 勾选节点
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

            # 8. 提取 chip / tag / tree count
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

            chip_n = extract_n(data['chip'])
            tag_n = extract_n(data['tag'])
            tree_n = extract_n(tree_count_str)

            print(f"\n[7] 提取统计:")
            print(f"    折叠横条 chip: {data['chip']!r} → {chip_n}")
            print(f"    list tab tag:  {data['tag']!r} → {tag_n}")
            print(f"    树节点 count:  {tree_count_str!r} → {tree_n}")
            await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_v6_selected.png", full_page=True)

            # 9. 闭环验证
            record("v40 折叠横条 chip = 树节点 关系数 (口径统一: 关系记录数, 非 code 数)",
                   chip_n is not None and tree_n is not None and chip_n == tree_n,
                   f"chip={chip_n}, tree_n={tree_n}")
            record("v40 list tab tag = 折叠横条 chip",
                   tag_n is not None and chip_n is not None and tag_n == chip_n,
                   f"tag={tag_n}, chip={chip_n}")
            record("v40 list tab tag = 树节点 关系数",
                   tag_n is not None and tree_n is not None and tag_n == tree_n,
                   f"tag={tag_n}, tree_n={tree_n}")

            # 10. 跳图表页验证
            print("\n[8] 跳图表页验证")
            chart_btn = await page.query_selector('button:has-text("图表视图")')
            if chart_btn:
                await chart_btn.click()
                print("    -> clicked 图表视图")
                await page.wait_for_timeout(8000)
                await page.screenshot(path=f"{SCREENSHOT_DIR}/v40_v6_chart.png", full_page=True)
                # 提取所有 "X 关系" 数字, 优先取 "总数" 面板里的
                chart_data = await page.evaluate("""() => {
                    // 找 "总数" 标签
                    var totalLabel = null;
                    document.querySelectorAll('*').forEach(function(el) {
                        if (el.children.length === 0 && el.textContent.trim() === '总数') {
                            totalLabel = el;
                        }
                    });
                    if (!totalLabel) return { found: false };

                    // 向上找 summary-card 容器
                    var panel = totalLabel;
                    for (var i = 0; i < 8; i++) {
                        if (panel.parentElement) {
                            panel = panel.parentElement;
                            if (panel.className && String(panel.className).indexOf('summary-card') >= 0
                                && String(panel.className).indexOf('summary-card--total') >= 0) {
                                break;
                            }
                        } else {
                            break;
                        }
                    }
                    var text = panel ? panel.textContent : '';
                    var matches = text.match(/(\\d+)\\s*关系/g) || [];
                    return { found: true, panel_cls: String(panel?.className || ''), panel_text: text.substring(0, 400), matches: matches };
                }""")
                print(f"    -> 图表页 数据: {chart_data}")
                # 取最后一个 (总数里的)
                if chart_data.get('matches'):
                    last_match = chart_data['matches'][-1]
                    chart_n = extract_n(last_match)
                else:
                    chart_n = 0
                print(f"    -> 图表页 总数 关系数: {chart_n}")
                record("v40 图表页 总数 关系数 = 树节点 关系数 (跨页面闭环)",
                       chart_n is not None and tree_n is not None and chart_n == tree_n,
                       f"chart_total={chart_n}, tree_n={tree_n}")
                record("v40 图表页 总数 关系数 = 折叠横条 chip",
                       chart_n is not None and chip_n is not None and chart_n == chip_n,
                       f"chart_total={chart_n}, chip={chip_n}")
                record("v40 图表页 总数 关系数 = list tab tag",
                       chart_n is not None and tag_n is not None and chart_n == tag_n,
                       f"chart_total={chart_n}, tag={tag_n}")
            else:
                record("图表页跳转", False, "图表视图按钮未找到")

        except Exception as e:
            print("\n[!!!] 异常 traceback:")
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
    sys.stdout = open(sys.stdout.fileno(), mode='w', buffering=1)
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"[!!!] Main crashed: {e}")
        import traceback
        traceback.print_exc()

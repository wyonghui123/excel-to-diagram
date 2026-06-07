"""
RelationScopeTree 端到端测试 (权威)

覆盖 5 个关键场景，确保所有 bug 修复 + regression 都被验证：
1) 问题1：手动展开 范围内, 同服务模块 后保持展开
2) 问题2：关系 list 精确显示 2 条
3) 范围外 可反勾选（keyCount 从 39 → 0）
4) flash 消除（点击不展开又快速合上）
5) 选中节点不自动折叠（regression test）

测试场景使用「财务管理 + 付款计划-付款计划」：
- 这是用户原始 bug 报告的具体场景（同服务模块(9) > 付款计划-付款计划(2) 出现 4 条而非 2 条）
- 付款计划 (AP_PAYMENT) 模块有 2 个 self-loop 关系（用户期望的 2 条）

使用 Playwright 真浏览器 (headless chromium) 跑真实 UI。
运行方式：python tests/e2e/e2e_relation_scope_tree.py
"""
import asyncio
import re
import os
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
    """登录 + 进入页面 + 选择产品/版本"""
    await page.goto(f"{API_URL}/api/v1/auth/dev-login?username=admin", wait_until="networkidle")
    await page.goto(f"{BASE_URL}/system/archdata", wait_until="networkidle")
    await page.wait_for_timeout(3000)

    selects = await page.query_selector_all('.el-select')
    if len(selects) >= 2:
        await selects[0].click()
        await page.wait_for_timeout(500)
        opt = await page.query_selector('.el-select-dropdown__item:has-text("供应链管理系统")')
        if opt: await opt.click()
        await page.wait_for_timeout(1500)
        selects = await page.query_selector_all('.el-select')
        await selects[1].click()
        await page.wait_for_timeout(500)
        opt = await page.query_selector('.el-select-dropdown__item:has-text("v1.0")')
        if opt: await opt.click()
    await page.wait_for_timeout(3000)


async def click_oss_domain(page, label):
    """点击 OSS 树中的 domain"""
    await page.evaluate(f"""() => {{
        const tree = document.querySelector('.oss-tree-container .el-tree');
        if (!tree) return;
        const nodes = Array.from(tree.querySelectorAll('.el-tree-node'));
        for (const n of nodes) {{
            const lbl = n.querySelector('.oss-node-label');
            if (lbl && lbl.textContent.trim() === '{label}') {{
                const cb = n.querySelector('.el-checkbox');
                if (cb) cb.click();
                return;
            }}
        }}
    }}""")
    await page.wait_for_timeout(2500)


async def expand_rss_panel(page):
    """展开 RSS 面板"""
    header = await page.query_selector('.rst-panel-relation .collapsible-panel__header')
    if header:
        await header.click()
    await page.wait_for_timeout(1500)


async def expand_rss_node(page, label):
    """展开 RSS 树的指定节点"""
    await page.evaluate(f"""() => {{
        const tree = document.querySelector('.rss-tree-container .el-tree');
        if (!tree) return;
        const all = Array.from(tree.querySelectorAll('.el-tree-node'));
        for (const n of all) {{
            const lbl = n.querySelector('.rss-node-label');
            if (lbl && lbl.textContent.trim() === '{label}') {{
                const expandIcon = n.querySelector('.el-tree-node__expand-icon');
                if (expandIcon && !expandIcon.classList.contains('is-leaf') && !n.classList.contains('is-expanded')) {{
                    expandIcon.click();
                }}
                return;
            }}
        }}
    }}""")
    await page.wait_for_timeout(800)


async def click_rss_leaf(page, label_prefix):
    """点击 RSS 树的叶子节点 checkbox"""
    return await page.evaluate(f"""() => {{
        const tree = document.querySelector('.rss-tree-container .el-tree');
        if (!tree) return {{ ok: false, reason: 'no tree' }};
        const all = Array.from(tree.querySelectorAll('.el-tree-node'));
        for (const n of all) {{
            if (n.offsetParent === null) continue;
            const lbl = n.querySelector('.rss-node-label')?.textContent?.trim() || '';
            if (lbl.startsWith('{label_prefix}')) {{
                const cb = n.querySelector('.el-checkbox');
                if (cb) {{
                    cb.click();
                    return {{ ok: true, label: lbl }};
                }}
            }}
        }}
        return {{ ok: false, reason: 'not found' }};
    }}""")


async def click_rss_parent(page, label):
    """点击 RSS 树的父节点 checkbox"""
    return await page.evaluate(f"""() => {{
        const tree = document.querySelector('.rss-tree-container .el-tree');
        if (!tree) return {{ ok: false }};
        const all = Array.from(tree.querySelectorAll('.el-tree-node'));
        for (const n of all) {{
            if (n.offsetParent === null) continue;
            const lbl = n.querySelector('.rss-node-label')?.textContent?.trim() || '';
            if (lbl === '{label}') {{
                const cb = n.querySelector('.el-checkbox');
                if (cb) {{
                    cb.click();
                    return {{ ok: true }};
                }}
            }}
        }}
        return {{ ok: false }};
    }}""")


async def get_rss_expanded_labels(page):
    """获取 RSS 树中所有展开节点的 label"""
    return await page.evaluate("""() => {
        const tree = document.querySelector('.rss-tree-container .el-tree');
        if (!tree) return [];
        const expanded = Array.from(tree.querySelectorAll('.el-tree-node.is-expanded'));
        return expanded.map(n => n.querySelector('.rss-node-label')?.textContent?.trim()).filter(Boolean);
    }""")


async def get_rss_node_state(page, label):
    """获取指定 label 节点的状态"""
    return await page.evaluate(f"""() => {{
        const tree = document.querySelector('.rss-tree-container .el-tree');
        if (!tree) return null;
        const all = Array.from(tree.querySelectorAll('.el-tree-node'));
        for (const n of all) {{
            const lbl = n.querySelector('.rss-node-label');
            if (lbl && lbl.textContent.trim() === '{label}') {{
                return {{
                    isChecked: !!n.querySelector('.is-checked'),
                    isExpanded: n.classList.contains('is-expanded'),
                    isIndeterminate: !!n.querySelector('.is-indeterminate')
                }};
            }}
        }}
        return null;
    }}""")


async def get_relations_list_count(page):
    """获取关系列表的行数"""
    return await page.evaluate("""() => {
        const tables = document.querySelectorAll('.el-table__body-wrapper');
        for (const t of tables) {
            const rows = t.querySelectorAll('tbody tr');
            if (rows.length > 0) {
                return {
                    count: rows.length,
                    samples: Array.from(rows).slice(0, 3).map(r =>
                        Array.from(r.querySelectorAll('td')).map(c => c.textContent.trim()).filter(Boolean).slice(0, 5).join(' | ')
                    )
                };
            }
        }
        return { count: 0, samples: [] };
    }""")


async def install_flash_observer(page, label):
    """在指定 label 节点上挂 MutationObserver，监测 is-expanded 状态变化"""
    return await page.evaluate(f"""() => {{
        window.__flashMutations = [];
        const tree = document.querySelector('.rss-tree-container .el-tree');
        if (!tree) return false;
        const all = Array.from(tree.querySelectorAll('.el-tree-node'));
        for (const n of all) {{
            const lbl = n.querySelector('.rss-node-label');
            if (lbl && lbl.textContent.trim() === '{label}') {{
                const obs = new MutationObserver((muts) => {{
                    for (const m of muts) {{
                        if (m.type === 'attributes' && m.attributeName === 'class') {{
                            window.__flashMutations.push({{
                                t: performance.now(),
                                isExpanded: n.classList.contains('is-expanded')
                            }});
                        }}
                    }}
                }});
                obs.observe(n, {{ attributes: true, attributeFilter: ['class'] }});
                window.__obs = obs;
                return true;
            }}
        }}
        return false;
    }}""")


async def get_flash_transitions(page):
    return await page.evaluate("""() => {
        const m = window.__flashMutations || [];
        let expandToCollapse = 0;
        for (let i = 1; i < m.length; i++) {
            if (m[i-1].isExpanded && !m[i].isExpanded) expandToCollapse++;
        }
        return { transitions: expandToCollapse, totalMutations: m.length };
    }""")


def clear_mutations(page):
    return page.evaluate("() => { window.__flashMutations = []; }")


# ============================================================
# 场景 1+2: 展开保持 + 关系 list 精确显示 2 条
# ============================================================
async def scenario_1_2_preserve_expansion_and_filter(p):
    print("\n=== 场景 1+2: 手动展开保持 + 关系 list 精确 2 条 ===")
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(viewport={"width": 1920, "height": 1200})
    page = await context.new_page()

    await setup_page(context, page)
    await click_oss_domain(page, '财务管理')
    await expand_rss_panel(page)

    # 手动展开 范围内, 同服务模块
    await expand_rss_node(page, '范围内')
    await expand_rss_node(page, '同服务模块')
    await page.wait_for_timeout(1000)

    before_expanded = await get_rss_expanded_labels(page)
    print(f"  展开后: {before_expanded}")

    # 点击 付款计划-付款计划 leaf（用户原始 bug 场景）
    click_result = await click_rss_leaf(page, '付款计划-付款计划')
    record("场景1: 找到并点击 付款计划-付款计划 leaf",
           click_result.get('ok', False),
           f"label={click_result.get('label', '?')}")
    await page.wait_for_timeout(3000)

    after_expanded = await get_rss_expanded_labels(page)
    print(f"  点击后: {after_expanded}")

    # 验证展开保持
    record("场景1: '范围内' 保持展开", '范围内' in after_expanded)
    record("场景1: '同服务模块' 保持展开", '同服务模块' in after_expanded)

    # 验证 关系 list 精确 2 条
    list_info = await get_relations_list_count(page)
    record("场景2: 关系 list 精确显示 2 条",
           list_info.get('count', 0) == 2,
           f"actual={list_info.get('count', 0)}")

    await browser.close()


# ============================================================
# 场景 3: 范围外 可反勾选
# ============================================================
async def scenario_3_uncheck_outer(p):
    print("\n=== 场景 3: 范围外 可反勾选 ===")
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(viewport={"width": 1920, "height": 1200})
    page = await context.new_page()

    handle_check_logs = []
    page.on("console", lambda msg: handle_check_logs.append(
        re.search(r'keyCount:\s*(\d+)', msg.text).group(1)
    ) if 'handleClassifierCheck' in msg.text and 'keyCount' in msg.text else None)

    await setup_page(context, page)
    await click_oss_domain(page, '销售管理')
    await expand_rss_panel(page)

    # 第 1 次点击 范围外 父
    handle_check_logs.clear()
    await click_rss_parent(page, '范围外')
    await page.wait_for_timeout(3000)
    s1 = await get_rss_node_state(page, '范围外')
    record("场景3: 第1次点击 范围外 → 勾选", s1 and s1.get('isChecked'), f"state={s1}")
    record("场景3: keyCount > 0 (勾选多个 keys)",
           len(handle_check_logs) > 0 and int(handle_check_logs[-1]) > 0,
           f"keyCount={handle_check_logs[-1] if handle_check_logs else 'N/A'}")

    # 第 2 次点击 范围外 父 (反勾选)
    handle_check_logs.clear()
    await click_rss_parent(page, '范围外')
    await page.wait_for_timeout(3000)
    s2 = await get_rss_node_state(page, '范围外')
    record("场景3: 第2次点击 范围外 → 反勾选",
           s2 and not s2.get('isChecked'),
           f"state={s2}")
    record("场景3: keyCount = 0 (反勾选)",
           len(handle_check_logs) > 0 and int(handle_check_logs[-1]) == 0,
           f"keyCount={handle_check_logs[-1] if handle_check_logs else 'N/A'}")

    await browser.close()


# ============================================================
# 场景 4: 无 flash (MutationObserver 监测 expand→collapse 转换)
# ============================================================
async def scenario_4_no_flash(p):
    print("\n=== 场景 4: 无 flash 行为 ===")
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(viewport={"width": 1920, "height": 1200})
    page = await context.new_page()

    await setup_page(context, page)
    await click_oss_domain(page, '销售管理')
    await expand_rss_panel(page)

    # 手动展开 范围内
    await expand_rss_node(page, '范围内')
    await page.wait_for_timeout(1000)

    # 挂 MutationObserver
    await install_flash_observer(page, '范围内')
    await clear_mutations(page)

    # 点击 范围外 父节点
    await click_rss_parent(page, '范围外')
    await page.wait_for_timeout(2500)

    result = await get_flash_transitions(page)
    record("场景4: 无 expand→collapse 转换 (无 flash)",
           result['transitions'] == 0,
           f"transitions={result['transitions']}, mutations={result['totalMutations']}")

    await browser.close()


# ============================================================
# 场景 5: 选中节点不自动折叠 (regression)
# ============================================================
async def scenario_5_no_auto_collapse(p):
    print("\n=== 场景 5: 选中节点不自动折叠 (regression) ===")
    browser = await p.chromium.launch(headless=True)
    context = await browser.new_context(viewport={"width": 1920, "height": 1200})
    page = await context.new_page()

    await setup_page(context, page)
    await click_oss_domain(page, '财务管理')
    await expand_rss_panel(page)

    # 手动展开 范围内, 同服务模块
    await expand_rss_node(page, '范围内')
    await expand_rss_node(page, '同服务模块')
    await page.wait_for_timeout(1000)

    before = await get_rss_expanded_labels(page)
    record("场景5: 手动展开 '范围内', '同服务模块'",
           '范围内' in before and '同服务模块' in before,
           f"before={before}")

    # 点击 付款计划-付款计划 leaf（用户原始 bug 场景）
    await click_rss_leaf(page, '付款计划-付款计划')
    await page.wait_for_timeout(3000)

    after = await get_rss_expanded_labels(page)
    print(f"  点击后: {after}")
    record("场景5: 点击后 '范围内' 仍展开", '范围内' in after)
    record("场景5: 点击后 '同服务模块' 仍展开", '同服务模块' in after)

    await browser.close()


async def main():
    print("=" * 70)
    print("RelationScopeTree E2E 测试")
    print("=" * 70)

    async with async_playwright() as p:
        await scenario_1_2_preserve_expansion_and_filter(p)
        await scenario_3_uncheck_outer(p)
        await scenario_4_no_flash(p)
        await scenario_5_no_auto_collapse(p)

    print("\n" + "=" * 70, flush=True)
    print("汇总", flush=True)
    print("=" * 70, flush=True)
    passed = sum(1 for _, p, _ in results if p)
    failed = sum(1 for _, p, _ in results if not p)
    total = len(results)
    print(f"  通过: {passed}/{total}", flush=True)
    if failed:
        print(f"\n  失败项:", flush=True)
        for name, p, detail in results:
            if not p:
                print(f"    - {name}: {detail}", flush=True)
    return failed == 0


if __name__ == "__main__":
    import sys
    success = asyncio.run(main())
    sys.exit(0 if success else 1)

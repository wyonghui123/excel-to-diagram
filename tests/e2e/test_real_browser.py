# -*- coding: utf-8 -*-
"""真实浏览器测试：精确复现用户报告的两个问题
1. 每次点击选择会自动全部展开关系范围树
2. 勾选付款计划-付款计划(2)后，关系list显示4条而不是2条
"""
import sys, json, time, os
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from playwright.sync_api import sync_playwright

SCREENSHOT_DIR = 'd:/filework/excel-to-diagram/test_screenshots'
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=500)
    context = browser.new_context(viewport={'width': 1920, 'height': 1080})
    page = context.new_page()
    
    # 收集 console 日志
    console_logs = []
    page.on('console', lambda msg: console_logs.append(f'[{msg.type}] {msg.text}'))
    
    # 1. 登录
    print("=== Step 1: 登录 ===")
    page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin",
              wait_until="domcontentloaded", timeout=10000)
    time.sleep(1)
    
    # 2. 导航到架构数据页
    print("=== Step 2: 导航到架构数据页 ===")
    page.goto("http://localhost:3004/system/archdata?productId=1&versionId=1",
              wait_until="domcontentloaded", timeout=10000)
    page.wait_for_function("() => !!document.querySelector('#app')?.__vue_app__", timeout=15000)
    time.sleep(3)
    page.screenshot(path=f'{SCREENSHOT_DIR}/01-page-loaded.png')
    
    # 3. 展开 OSS 和 RSS 面板
    print("=== Step 3: 展开面板 ===")
    # 找到所有 collapsible panel headers
    panels = page.evaluate("""() => {
        const headers = document.querySelectorAll('.collapsible-panel__header');
        return Array.from(headers).map(h => ({
            text: h.textContent.trim().substring(0, 30),
            isCollapsed: h.closest('.collapsible-panel')?.classList.contains('is-collapsed')
        }));
    }""")
    print(f"   Panels: {json.dumps(panels, ensure_ascii=False)}")
    
    # 展开所有面板
    page.evaluate("""() => {
        document.querySelectorAll('.collapsible-panel__header').forEach(h => {
            const panel = h.closest('.collapsible-panel');
            if (panel?.classList.contains('is-collapsed')) h.click();
        });
    }""")
    time.sleep(2)
    page.screenshot(path=f'{SCREENSHOT_DIR}/02-panels-expanded.png')
    
    # 4. 在 OSS 树中勾选"销售管理"
    print("=== Step 4: 勾选 OSS '销售管理' ===")
    # 先找到"销售管理"节点
    oss_info = page.evaluate("""() => {
        const labels = document.querySelectorAll('[data-testid="oss-tree-label"]');
        const result = [];
        for (const l of labels) {
            const text = l.textContent.trim();
            if (text.includes('销售')) {
                const node = l.closest('.el-tree-node');
                const cb = node?.querySelector('.el-checkbox__input');
                result.push({ text, hasCheckbox: !!cb, isChecked: cb?.classList.contains('is-checked') });
            }
        }
        return result;
    }""")
    print(f"   OSS 销售相关节点: {json.dumps(oss_info, ensure_ascii=False)}")
    
    # 点击"销售管理"的 checkbox
    click_result = page.evaluate("""() => {
        const labels = document.querySelectorAll('[data-testid="oss-tree-label"]');
        for (const l of labels) {
            if (l.textContent.trim() === '销售管理') {
                const node = l.closest('.el-tree-node');
                const cb = node?.querySelector('.el-checkbox__input');
                if (cb) { cb.click(); return { clicked: true, text: l.textContent.trim() }; }
            }
        }
        return { clicked: false };
    }""")
    print(f"   Click result: {click_result}")
    time.sleep(5)
    page.screenshot(path=f'{SCREENSHOT_DIR}/03-oss-sales-mgmt-checked.png')
    
    # 5. 检查 RSS 树状态
    print("=== Step 5: RSS 树状态 ===")
    rss_state = page.evaluate("""() => {
        const trees = document.querySelectorAll('.el-tree');
        const rssTree = trees[1];
        if (!rssTree) return { error: 'no RSS tree' };
        
        // 统计 expanded 节点
        const allNodes = rssTree.querySelectorAll('.el-tree-node');
        const expanded = [];
        const collapsed = [];
        for (const n of allNodes) {
            const label = n.querySelector('[data-testid="rss-tree-label"]')?.textContent?.trim();
            if (!label) continue;
            if (n.classList.contains('is-expanded')) {
                expanded.push(label);
            } else if (!n.classList.contains('is-leaf')) {
                collapsed.push(label);
            }
        }
        
        return {
            totalNodes: allNodes.length,
            expandedCount: expanded.length,
            expanded: expanded.slice(0, 20),
            collapsedCount: collapsed.length,
            collapsed: collapsed.slice(0, 10)
        };
    }""")
    print(f"   RSS state: {json.dumps(rss_state, ensure_ascii=False, indent=2)}")
    
    # 问题 1 验证：是否自动全部展开
    if rss_state.get('collapsedCount', 0) > 0:
        print(f"   [问题1] 还有 {rss_state['collapsedCount']} 个折叠节点 - 部分展开")
    else:
        print(f"   [问题1] 所有非叶节点都已展开 - 全部展开！BUG!")
    
    # 6. 手动折叠"范围内"节点
    print("\n=== Step 6: 手动折叠'范围内' ===")
    page.evaluate("""() => {
        const labels = document.querySelectorAll('[data-testid="rss-tree-label"]');
        for (const l of labels) {
            if (l.textContent.trim() === '范围内') {
                const node = l.closest('.el-tree-node');
                const icon = node?.querySelector('.el-tree-node__expand-icon');
                if (icon) { icon.click(); return 'collapsed'; }
            }
        }
        return 'not found';
    }""")
    time.sleep(1)
    page.screenshot(path=f'{SCREENSHOT_DIR}/04-within-collapsed.png')
    
    # 7. 展开"范围内" → "同服务模块"
    print("=== Step 7: 展开'范围内' → '同服务模块' ===")
    page.evaluate("""() => {
        const labels = document.querySelectorAll('[data-testid="rss-tree-label"]');
        for (const l of labels) {
            if (l.textContent.trim() === '范围内') {
                const node = l.closest('.el-tree-node');
                const icon = node?.querySelector('.el-tree-node__expand-icon');
                if (icon) icon.click();
            }
        }
    }""")
    time.sleep(1)
    page.evaluate("""() => {
        const labels = document.querySelectorAll('[data-testid="rss-tree-label"]');
        for (const l of labels) {
            if (l.textContent.trim() === '同服务模块') {
                const node = l.closest('.el-tree-node');
                const icon = node?.querySelector('.el-tree-node__expand-icon');
                if (icon) icon.click();
            }
        }
    }""")
    time.sleep(2)
    page.screenshot(path=f'{SCREENSHOT_DIR}/05-same-module-expanded.png')
    
    # 8. 列出"同服务模块"下所有叶子节点
    print("=== Step 8: '同服务模块' 下叶子节点 ===")
    leaves = page.evaluate("""() => {
        const labels = document.querySelectorAll('[data-testid="rss-tree-label"]');
        let sameModuleNode = null;
        for (const l of labels) {
            if (l.textContent.trim() === '同服务模块') {
                sameModuleNode = l.closest('.el-tree-node');
                break;
            }
        }
        if (!sameModuleNode) return { error: 'not found' };
        
        const children = sameModuleNode.querySelectorAll('.el-tree-node.is-leaf');
        return Array.from(children).map(c => {
            const label = c.querySelector('[data-testid="rss-tree-label"]')?.textContent?.trim();
            return label;
        });
    }""")
    print(f"   Leaves: {json.dumps(leaves, ensure_ascii=False)}")
    
    # 9. 只勾选"付款计划-付款计划"
    print("\n=== Step 9: 勾选 '付款计划-付款计划' ===")
    click_leaf = page.evaluate("""() => {
        const labels = document.querySelectorAll('[data-testid="rss-tree-label"]');
        for (const l of labels) {
            if (l.textContent.trim() === '付款计划-付款计划') {
                const node = l.closest('.el-tree-node');
                const cb = node?.querySelector('.el-checkbox__input');
                if (cb) { cb.click(); return { clicked: true, text: l.textContent.trim() }; }
            }
        }
        return { clicked: false };
    }""")
    print(f"   Click: {click_leaf}")
    time.sleep(3)
    page.screenshot(path=f'{SCREENSHOT_DIR}/06-payment-plan-checked.png')
    
    # 10. 检查问题 1：是否自动展开
    print("\n=== Step 10: 检查是否自动展开 ===")
    after_click_expand = page.evaluate("""() => {
        const trees = document.querySelectorAll('.el-tree');
        const rssTree = trees[1];
        const allNodes = rssTree.querySelectorAll('.el-tree-node');
        const expanded = [];
        for (const n of allNodes) {
            if (n.classList.contains('is-expanded')) {
                const label = n.querySelector('[data-testid="rss-tree-label"]')?.textContent?.trim();
                if (label) expanded.push(label);
            }
        }
        return { expandedCount: expanded.length, expanded };
    }""")
    print(f"   Expanded after click: {json.dumps(after_click_expand, ensure_ascii=False)}")
    
    if after_click_expand['expandedCount'] > 2:
        print(f"   [问题1 BUG] 勾选后 expanded 节点数={after_click_expand['expandedCount']} > 2，自动展开了！")
    else:
        print(f"   [问题1 OK] 勾选后 expanded 节点数={after_click_expand['expandedCount']}")
    
    # 11. 检查问题 2：selectedCodes 数量
    print("\n=== Step 11: 检查 selectedCodes ===")
    codes_info = page.evaluate("""() => {
        const trees = document.querySelectorAll('.el-tree');
        const rssTree = trees[1];
        if (!rssTree?.__vueParentComponent) return { error: 'no comp' };
        let p = rssTree.__vueParentComponent;
        while (p) {
            if (p.exposed?._test) {
                const t = p.exposed._test;
                return {
                    selectedCodes: t.selectedCodes,
                    selectedCodesLen: t.selectedCodes?.length || 0,
                    filterParams: t.filterParams
                };
            }
            if (p.setupState?._test) {
                const t = p.setupState._test;
                return {
                    selectedCodes: t.selectedCodes,
                    selectedCodesLen: t.selectedCodes?.length || 0,
                    filterParams: t.filterParams
                };
            }
            p = p.parent;
        }
        return { error: 'no _test' };
    }""")
    print(f"   selectedCodes: {json.dumps(codes_info, ensure_ascii=False, indent=2)}")
    
    # 12. 检查 el-tree store 内部 checked 节点（包含隐藏节点）
    print("\n=== Step 12: el-tree store checked 节点（含隐藏） ===")
    store_checked = page.evaluate("""() => {
        const trees = document.querySelectorAll('.el-tree');
        const rssTree = trees[1];
        let p = rssTree.__vueParentComponent;
        while (p) {
            if (p.setupState?.relationTreeRef?.value?.store) {
                const store = p.setupState.relationTreeRef.value.store;
                const checked = store.getCheckedNodes(false, false) || [];
                return {
                    count: checked.length,
                    nodes: checked.map(n => ({
                        label: n.label?.substring(0, 30),
                        id: n.id,
                        isLeaf: n.isLeaf,
                        visible: n.visible,
                        relationCodes: n.relationCodes
                    }))
                };
            }
            p = p.parent;
        }
        return { error: 'no store' };
    }""")
    print(f"   Store checked: {json.dumps(store_checked, ensure_ascii=False, indent=2)}")
    
    # 13. 检查 DOM 中 checked 的节点
    print("\n=== Step 13: DOM checked 节点 ===")
    dom_checked = page.evaluate("""() => {
        const trees = document.querySelectorAll('.el-tree');
        const rssTree = trees[1];
        const checked = [];
        const checkboxes = rssTree.querySelectorAll('.el-checkbox__input.is-checked');
        for (const cb of checkboxes) {
            const content = cb.closest('.el-tree-node__content');
            const label = content?.querySelector('[data-testid="rss-tree-label"]')?.textContent?.trim();
            if (label) checked.push(label);
        }
        return { count: checked.length, labels: checked };
    }""")
    print(f"   DOM checked: {json.dumps(dom_checked, ensure_ascii=False)}")
    
    # 14. 检查关系 list（右侧面板）
    print("\n=== Step 14: 关系 list ===")
    relation_list = page.evaluate("""() => {
        // 查找关系列表
        const tables = document.querySelectorAll('.el-table, .relation-list, [class*="relation"]');
        const result = [];
        for (const t of tables) {
            const rows = t.querySelectorAll('.el-table__row, tr');
            if (rows.length > 0) {
                result.push({
                    class: t.className?.substring(0, 50),
                    rowCount: rows.length,
                    sample: Array.from(rows).slice(0, 5).map(r => r.textContent?.trim().substring(0, 60))
                });
            }
        }
        
        // 也查找 useMultiObjectPage 的 scopeIds
        const app = document.querySelector('#app')?.__vue_app__;
        if (app) {
            const pinia = app.config?.globalProperties?.$pinia;
            if (pinia) {
                for (const [id, store] of pinia._s) {
                    if (store.scopeIds) {
                        result.push({
                            storeId: id,
                            relationExtra: store.scopeIds?.relationExtra
                        });
                    }
                }
            }
        }
        
        return result;
    }""")
    print(f"   Relation list: {json.dumps(relation_list, ensure_ascii=False, indent=2)}")
    
    # 最终截图
    page.screenshot(path=f'{SCREENSHOT_DIR}/07-final-state.png')
    
    # 输出 console 错误
    errors = [l for l in console_logs if '[error]' in l.lower() or 'ERR' in l]
    if errors:
        print(f"\n=== Console Errors ({len(errors)}) ===")
        for e in errors[:10]:
            print(f"   {e}")
    
    print("\n=== 测试完成 ===")
    print(f"截图保存在: {SCREENSHOT_DIR}")
    
    browser.close()

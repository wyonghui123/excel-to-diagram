# -*- coding: utf-8 -*-
"""诊断 v12: 复现问题 2 - 勾选付款计划-付款计划 后实际 selectedCodes 是什么"""
import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from test_helpers.browser_auth_cli import PlaywrightCLI
from test_helpers.tree_helpers import expand_oss_panel, expand_rss_panel, click_oss_by_label

with PlaywrightCLI(headless=False) as cli:
    page = cli._ensure_browser()
    
    page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin",
              wait_until="domcontentloaded", timeout=10000)
    page.goto("http://localhost:3004/system/archdata?productId=1&versionId=1",
              wait_until="domcontentloaded", timeout=10000)
    
    page.wait_for_function("() => !!document.querySelector('#app')?.__vue_app__", timeout=15000)
    page.wait_for_url("**/archdata**", timeout=10000)
    time.sleep(3)
    
    expand_oss_panel(cli)
    expand_rss_panel(cli)
    time.sleep(1)
    
    # 1. 选择 OSS 销售管理
    print("=== 1. 选择 OSS: 销售管理 ===")
    click_oss_by_label(cli, "销售管理")
    time.sleep(5)
    
    # 2. 展开所有节点
    print("\n=== 2. 展开所有 RSS 树节点 ===")
    page.evaluate("""() => {
        const trees = document.querySelectorAll('.el-tree');
        const rssTree = trees[1];
        const icons = rssTree.querySelectorAll('.el-tree-node__expand-icon');
        icons.forEach(i => {
            if (!i.closest('.el-tree-node').classList.contains('is-leaf')) {
                if (!i.closest('.el-tree-node').classList.contains('is-expanded')) {
                    i.click();
                }
            }
        });
    }""")
    time.sleep(3)
    
    # 3. 看 RSS 树所有叶子节点
    print("\n=== 3. 列出所有叶子节点 ===")
    leaves = page.evaluate("""() => {
        const trees = document.querySelectorAll('.el-tree');
        const rssTree = trees[1];
        const nodes = rssTree.querySelectorAll('.el-tree-node.is-leaf');
        const result = [];
        for (const n of nodes) {
            const label = n.querySelector('[data-testid="rss-tree-label"]')?.textContent?.trim();
            // 找父级 category
            let p = n.parentElement;
            let path = [];
            while (p && p !== document.body) {
                if (p.classList?.contains('el-tree-node') && !p.classList.contains('is-leaf')) {
                    const lbl = p.querySelector(':scope > .el-tree-node__content .el-tree-node__label');
                    if (lbl) path.unshift(lbl.textContent.trim());
                }
                p = p.parentElement;
            }
            result.push({ label, path: path.join(' > ') });
        }
        return result;
    }""")
    for l in leaves:
        print(f"   {l['path']} → {l['label']}")
    print(f"   Total: {len(leaves)}")
    
    # 4. 找 "付款计划-付款计划" 节点
    print("\n=== 4. 找 '付款计划-付款计划' 节点 ===")
    target = page.evaluate("""() => {
        const trees = document.querySelectorAll('.el-tree');
        const rssTree = trees[1];
        const nodes = rssTree.querySelectorAll('.el-tree-node.is-leaf');
        for (const n of nodes) {
            const label = n.querySelector('[data-testid="rss-tree-label"]')?.textContent?.trim();
            if (label === '付款计划-付款计划') {
                const cb = n.querySelector('.el-checkbox__input');
                if (cb) {
                    cb.click();
                    return { found: true, label };
                }
            }
        }
        return { found: false };
    }""")
    print(f"   {json.dumps(target, ensure_ascii=False)}")
    time.sleep(2)
    
    # 5. 读取 el-tree store 内部状态（包含隐藏节点的 checked）
    print("\n=== 5. el-tree store.getCheckedNodes ===")
    store = page.evaluate("""() => {
        const trees = document.querySelectorAll('.el-tree');
        const rssTree = trees[1];
        let p = rssTree.__vueParentComponent;
        while (p) {
            if (p.setupState?.relationTreeRef?.value?.store) {
                const store = p.setupState.relationTreeRef.value.store;
                const checked = Array.from(store.getCheckedNodes(false, false) || []);
                return {
                    count: checked.length,
                    names: checked.map(n => ({
                        label: n.label?.substring(0, 30),
                        id: n.id,
                        isLeaf: n.isLeaf,
                        isHidden: !n.visible,
                    }))
                };
            }
            p = p.parent;
        }
        return { error: 'no store' };
    }""")
    print(f"   {json.dumps(store, ensure_ascii=False, indent=2)}")
    
    # 6. 读取 _test 状态
    print("\n=== 6. _test 状态 ===")
    test_state = page.evaluate("""() => {
        const trees = document.querySelectorAll('.el-tree');
        const rssTree = trees[1];
        let p = rssTree.__vueParentComponent;
        while (p) {
            if (p.exposed?._test) return p.exposed._test;
            if (p.setupState?._test) return p.setupState._test;
            p = p.parent;
        }
        return null;
    }""")
    print(f"   filterParams: {json.dumps(test_state.get('filterParams', {}), ensure_ascii=False)}")
    print(f"   selectedCodes: {test_state.get('selectedCodes', [])}")
    print(f"   selectedCodesLen: {len(test_state.get('selectedCodes', []))}")
    
    # 7. 模拟后端关系 list (使用 useMultiObjectPage)
    print("\n=== 7. 找关系 list 显示条数 ===")
    relation_count = page.evaluate("""() => {
        // 找 useMultiObjectPage composable
        const app = document.querySelector('#app')?.__vue_app__;
        if (!app) return { error: 'no app' };
        
        // 查找 useMultiObjectPage 内部状态
        // 通过 store
        const pinia = app.config?.globalProperties?.$pinia;
        if (!pinia) return { error: 'no pinia' };
        
        const stores = Array.from(pinia._s.values());
        for (const store of stores) {
            if (store.$id?.includes('archdata') || store.$id?.includes('multi')) {
                const relations = store.allRelations || store.relations || store.scopeIds?.relationExtra;
                if (relations) {
                    return {
                        storeId: store.$id,
                        hasScopeIds: !!store.scopeIds,
                        relationExtra: store.scopeIds?.relationExtra
                    };
                }
            }
        }
        return { storeCount: stores.length, storeIds: stores.map(s => s.$id) };
    }""")
    print(f"   {json.dumps(relation_count, ensure_ascii=False, indent=2)}")
    
    cli.close()

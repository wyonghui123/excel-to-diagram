# -*- coding: utf-8 -*-
"""快速检查 el-tree store.defaultExpandAll"""
import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width': 1920, 'height': 1080})
    page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded", timeout=10000)
    page.goto("http://localhost:3004/system/archdata?productId=1&versionId=1", wait_until="domcontentloaded", timeout=10000)
    page.wait_for_function("() => !!document.querySelector('#app')?.__vue_app__", timeout=15000)
    time.sleep(3)
    
    # 展开面板
    page.evaluate("""() => {
        document.querySelectorAll('.collapsible-panel__header').forEach(h => {
            const panel = h.closest('.collapsible-panel');
            if (panel?.classList.contains('is-collapsed')) h.click();
        });
    }""")
    time.sleep(1)
    
    # 勾选 OSS 销售管理
    page.evaluate("""() => {
        const labels = document.querySelectorAll('[data-testid="oss-tree-label"]');
        for (const l of labels) {
            if (l.textContent.trim() === '销售管理') {
                const cb = l.closest('.el-tree-node')?.querySelector('.el-checkbox__input');
                if (cb) cb.click();
            }
        }
    }""")
    time.sleep(5)
    
    # 检查 el-tree store 配置
    info = page.evaluate("""() => {
        const trees = document.querySelectorAll('.el-tree');
        const results = [];
        for (let i = 0; i < trees.length; i++) {
            const t = trees[i];
            if (!t.__vueParentComponent) continue;
            let p = t.__vueParentComponent;
            let store = null;
            // 找 store
            while (p) {
                if (p.setupState?.relationTreeRef?.value?.store) {
                    store = p.setupState.relationTreeRef.value.store;
                    break;
                }
                if (p.setupState?.treeRef?.value?.store) {
                    store = p.setupState.treeRef.value.store;
                    break;
                }
                p = p.parent;
            }
            if (!store) {
                // 直接从 el-tree 组件找
                const elTreeComp = t.__vueParentComponent;
                if (elTreeComp?.setupState?.store) {
                    store = elTreeComp.setupState.store;
                }
            }
            if (store) {
                results.push({
                    treeIndex: i,
                    defaultExpandAll: store.defaultExpandAll,
                    defaultExpandedKeys: Array.from(store.defaultExpandedKeys || []),
                    expandedKeys: Array.from(store.expandedKeys || []),
                    lazy: store.lazy,
                    nodesMapCount: Object.keys(store.nodesMap || {}).length
                });
            } else {
                results.push({ treeIndex: i, error: 'no store found' });
            }
        }
        return results;
    }""")
    print(json.dumps(info, ensure_ascii=False, indent=2))
    
    browser.close()

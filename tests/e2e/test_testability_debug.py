# -*- coding: utf-8 -*-
"""深度诊断 OSS/RSS 树的可测试性问题"""
import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

print("=== 前端测试可测试性深度诊断 ===\n")

with PlaywrightCLI(headless=False) as cli:
    # Step 1: 认证导航到目标页面
    print("[1] 导航到 archdata 页面...")
    cli.authenticated_navigate(
        '/system/archdata?productId=1&versionId=1',
        wait_for_selector='.oss-node-label,.rss-node-label,.el-tree'
    )
    time.sleep(3)
    
    # Step 2: 简单健康检查
    has_app = cli.evaluate("!!document.querySelector('#app')")
    page_errors = len(getattr(cli, '_page_errors', []))
    console_errors = [e for e in getattr(cli, '_console_errors', []) if e.get('level') == 'error']
    print(f"[2] Health: #app={has_app}, pageErrors={page_errors}, consoleErrors={len(console_errors)}")
    
    # Step 3: OSS 面板状态
    print("\n[3] === OSS 面板 ===")
    oss_panel = cli.evaluate("""() => {
        const panel = document.querySelector('.rst-panel-object');
        if (!panel) return {error: 'no oss panel'};
        return {
            collapsed: panel.classList.contains('is-collapsed'),
            display: getComputedStyle(panel).display,
            height: panel.getBoundingClientRect().height
        };
    }""")
    print(f"  OSS panel: {json.dumps(oss_panel, ensure_ascii=False)}")
    
    # Step 4: OSS 树节点
    oss_labels = cli.evaluate("document.querySelectorAll('.oss-node-label').length")
    oss_el_nodes = cli.evaluate("document.querySelectorAll('.el-tree')[0]?.querySelectorAll('.el-tree-node').length")
    print(f"  OSS labels: {oss_labels}, el-tree-nodes: {oss_el_nodes}")
    
    # OSS 前5个 label 文本
    if oss_labels > 0:
        oss_texts = cli.evaluate("""() => {
            return Array.from(document.querySelectorAll('.oss-node-label')).slice(0,8)
                .map(l => l.textContent.trim());
        }""")
        print(f"  OSS label texts: {oss_texts}")
    
    # Step 5: 展开 OSS 面板（如果折叠）
    cli.evaluate("""() => {
        const panel = document.querySelector('.rst-panel-object');
        if (panel && panel.classList.contains('is-collapsed')) {
            const header = panel.querySelector('.collapsible-panel__header');
            if (header) header.click();
        }
    }""")
    time.sleep(1.5)
    
    # Step 6: 再次检查 OSS 节点数
    oss_checkboxes = cli.evaluate("document.querySelectorAll('.el-tree')[0]?.querySelectorAll('.el-checkbox__original').length")
    print(f"  OSS checkboxes (after expand): {oss_checkboxes}")
    
    # Step 7: RSS 面板状态
    print("\n[4] === RSS 面板 ===")
    rss_panel = cli.evaluate("""() => {
        const panel = document.querySelector('.rst-panel-relation');
        if (!panel) return {error: 'no rss panel'};
        return {
            collapsed: panel.classList.contains('is-collapsed'),
            display: getComputedStyle(panel).display,
            height: panel.getBoundingClientRect().height
        };
    }""")
    print(f"  RSS panel: {json.dumps(rss_panel, ensure_ascii=False)}")
    
    # 展开 RSS 面板
    cli.evaluate("""() => {
        const panel = document.querySelector('.rst-panel-relation');
        if (panel && panel.classList.contains('is-collapsed')) {
            const header = panel.querySelector('.collapsible-panel__header');
            if (header) header.click();
        }
    }""")
    time.sleep(1.5)
    
    # Step 8: RSS 树节点
    rss_labels = cli.evaluate("document.querySelectorAll('.rss-node-label').length")
    rss_el_nodes = cli.evaluate("document.querySelectorAll('.el-tree')[1]?.querySelectorAll('.el-tree-node').length")
    rss_checkboxes = cli.evaluate("document.querySelectorAll('.el-tree')[1]?.querySelectorAll('.el-checkbox__original').length")
    print(f"  RSS labels: {rss_labels}, el-tree-nodes: {rss_el_nodes}, checkboxes: {rss_checkboxes}")
    
    if rss_labels > 0:
        rss_texts = cli.evaluate("""() => {
            return Array.from(document.querySelectorAll('.rss-node-label')).slice(0,10)
                .map(l => l.textContent.trim());
        }""")
        print(f"  RSS label texts: {rss_texts}")
    
    # Step 9: RSS 可见节点详情
    rss_visible = cli.evaluate("""() => {
        const trees = document.querySelectorAll('.el-tree');
        if (trees.length < 2) return {error: 'no rss tree'};
        const nodes = trees[1].querySelectorAll('.el-tree-node');
        const result = [];
        nodes.forEach((n, i) => {
            if (n.offsetHeight > 0) {
                const label = n.querySelector('.rss-node-label');
                result.push({
                    idx: i,
                    label: label ? label.textContent.trim().substring(0, 50) : '-',
                    expanded: n.classList.contains('is-expanded'),
                    leaf: n.classList.contains('is-leaf'),
                    children: n.querySelectorAll('.el-tree-node__children .el-tree-node').length
                });
            }
        });
        return result;
    }""")
    print(f"  RSS visible nodes: {json.dumps(rss_visible, ensure_ascii=False)}")
    
    # Step 10: Vue 组件链
    print("\n[5] === Vue 组件链 ===")
    vue_chains = cli.evaluate("""() => {
        const trees = document.querySelectorAll('.el-tree');
        const result = [];
        for (let j = 0; j < trees.length; j++) {
            let comp = trees[j].__vueParentComponent;
            const chain = [];
            for (let i = 0; i < 20 && comp; i++) {
                chain.push(comp.type?.__name || comp.type?.name || '?');
                comp = comp.parent;
            }
            result.push({tree: j, chain: chain.join(' -> ')});
        }
        return result;
    }""")
    for c in vue_chains:
        print(f"  {c}")
    
    # Step 11: RSS filter 参数
    print("\n[6] === RSS filter 参数 ===")
    filter_params = cli.evaluate("""() => {
        const t = document.querySelectorAll('.el-tree')[1];
        if (!t) return 'no rss tree';
        let comp = t.__vueParentComponent;
        for (let i = 0; i < 20 && comp; i++) {
            if ((comp.type?.__name || '') === 'RelationScopeSection') {
                const p = comp.proxy;
                return {
                    domainIds: p.selectedDomainIds,
                    subDomainIds: p.selectedSubDomainIds,
                    serviceModuleIds: p.selectedServiceModuleIds,
                    boIds: p.selectedBoIds,
                    stale: p.stale,
                    classifierLoading: p.classifierLoading,
                    hasData: p.hasData,
                    treeDataLen: p.classifierTreeData?.length
                };
            }
            comp = comp.parent;
        }
        return 'no RSS comp found';
    }""")
    print(f"  {json.dumps(filter_params, ensure_ascii=False)}")
    
    # Step 12: 尝试点击 OSS 节点触发 scope-change
    print("\n[7] === 测试 OSS 点击 -> RSS filter ===")
    click_result = cli.evaluate("""() => {
        const tree = document.querySelectorAll('.el-tree')[0];
        if (!tree) return {error: 'no oss tree'};
        // 找到第一个 checkbox
        const cb = tree.querySelector('.el-checkbox__original');
        if (cb) {
            cb.click();
            return {clicked: true, label: cb.closest('.el-tree-node')?.querySelector('.oss-node-label')?.textContent?.trim() || '-'};
        }
        return {error: 'no checkbox'};
    }""")
    print(f"  Click: {json.dumps(click_result, ensure_ascii=False)}")
    time.sleep(3)
    
    # 点击后检查 RSS filter 变化
    filter_after = cli.evaluate("""() => {
        const t = document.querySelectorAll('.el-tree')[1];
        if (!t) return 'no rss tree';
        let comp = t.__vueParentComponent;
        for (let i = 0; i < 20 && comp; i++) {
            if ((comp.type?.__name || '') === 'RelationScopeSection') {
                const p = comp.proxy;
                return {
                    domainIds: p.selectedDomainIds,
                    serviceModuleIds: p.selectedServiceModuleIds,
                    stale: p.stale,
                    treeDataLen: p.classifierTreeData?.length
                };
            }
            comp = comp.parent;
        }
        return 'no RSS comp';
    }""")
    print(f"  After click: {json.dumps(filter_after, ensure_ascii=False)}")
    
    # Step 13: 截图
    cli.screenshot('testability_diag.png')
    print("\n[8] 截图: testability_diag.png")
    
print("\n=== 诊断完成 ===")

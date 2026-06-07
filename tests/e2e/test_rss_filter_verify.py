# -*- coding: utf-8 -*-
"""验证 OSS 点击后 RSS filter 是否真的触发树更新"""
import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

print("=== RSS filter 联动验证 ===\n")

with PlaywrightCLI(headless=False) as cli:
    cli.authenticated_navigate(
        '/system/archdata?productId=1&versionId=1',
        wait_for_selector='.oss-node-label'
    )
    time.sleep(3)
    
    # 展开两个面板
    for panel_sel in ['.rst-panel-object', '.rst-panel-relation']:
        cli.evaluate(f"""() => {{
            const panel = document.querySelector('{panel_sel}');
            if (panel && panel.classList.contains('is-collapsed')) {{
                panel.querySelector('.collapsible-panel__header')?.click();
            }}
        }}""")
    time.sleep(2)
    
    # ====== BEFORE OSS click ======
    print("[1] BEFORE OSS click:")
    total_rss_before = cli.evaluate("document.querySelectorAll('.rss-node-label').length")
    print(f"  RSS total labels: {total_rss_before}")
    
    rss_visible_before = cli.evaluate("""() => {
        return document.querySelectorAll('.el-tree')[1]
            .querySelectorAll('.el-tree-node:not([style*="display: none"])').length;
    }""")
    print(f"  RSS visible nodes (before): {rss_visible_before}")
    
    # 检查 RSS 组件 props
    rss_filter_input = cli.evaluate("""() => {
        let comp = document.querySelectorAll('.el-tree')[1].__vueParentComponent;
        for (let i=0; i<20 && comp; i++) {
            if (comp.type?.__name === 'RelationScopeSection') {
                return {
                    domainIds: comp.proxy.selectedDomainIds,
                    serviceModuleIds: comp.proxy.selectedServiceModuleIds,
                    stale: comp.proxy.stale
                };
            }
            comp = comp.parent;
        }
        return null;
    }""")
    print(f"  RSS selectedDomainIds: {json.dumps(rss_filter_input, ensure_ascii=False)}")
    
    # OSS checked keys
    oss_checked = cli.evaluate("""() => {
        const t = document.querySelectorAll('.el-tree')[0];
        if (!t) return null;
        const cbs = t.querySelectorAll('.el-checkbox.is-checked');
        return cbs.length;
    }""")
    print(f"  OSS checked checkboxes: {oss_checked}")
    
    # ====== CLICK OSS node ======
    print("\n[2] Click OSS domain 17 (RoundTrip新增测试)...")
    cli.evaluate("""() => {
        // 找到 RoundTrip 旁边的 checkbox
        const labels = document.querySelectorAll('.oss-node-label');
        for (const l of labels) {
            if (l.textContent.trim() === 'RoundTrip新增测试') {
                const node = l.closest('.el-tree-node');
                const cb = node?.querySelector('.el-checkbox__original');
                if (cb) { cb.click(); return 'clicked'; }
            }
        }
        return 'not found';
    }""")
    time.sleep(5)  # Wait for API + tree rebuild
    
    # ====== AFTER OSS click ======
    print("\n[3] AFTER OSS click:")
    total_rss_after = cli.evaluate("document.querySelectorAll('.rss-node-label').length")
    print(f"  RSS total labels: {total_rss_after}")
    
    rss_visible_after = cli.evaluate("""() => {
        const tree = document.querySelectorAll('.el-tree')[1];
        if (!tree) return 0;
        return tree.querySelectorAll('.el-tree-node:not([style*="display: none"])').length;
    }""")
    print(f"  RSS visible nodes (after): {rss_visible_after}")
    
    # RSS labels after
    rss_texts_after = cli.evaluate("""() => {
        const all = document.querySelectorAll('.rss-node-label');
        return Array.from(all).slice(0, 12).map(l => ({
            text: l.textContent.trim().substring(0, 40),
            hidden: l.closest('.el-tree-node')?.style?.display === 'none'
        }));
    }""")
    print(f"  RSS labels (after): {json.dumps(rss_texts_after, ensure_ascii=False)}")
    
    # filter params after
    filter_after = cli.evaluate("""() => {
        let comp = document.querySelectorAll('.el-tree')[1].__vueParentComponent;
        for (let i=0; i<20 && comp; i++) {
            if (comp.type?.__name === 'RelationScopeSection') {
                const p = comp.proxy;
                return {
                    domainIds: p.selectedDomainIds,
                    serviceModuleIds: p.selectedServiceModuleIds,
                    stale: p.stale,
                    classifierLoading: p.classifierLoading
                };
            }
            comp = comp.parent;
        }
        return null;
    }""")
    print(f"  RSS filter params: {json.dumps(filter_after, ensure_ascii=False)}")
    
    # 检查 console 是否有 API 错误
    console_errs = [e for e in getattr(cli, '_console_errors', []) if e.get('level') == 'error']
    if console_errs:
        print(f"\n[4] Console errors ({len(console_errs)}):")
        for e in console_errs[:5]:
            print(f"  {e['text'][:200]}")
    else:
        print("\n[4] No console errors")
    
    cli.screenshot('rss_filter_verify.png')
    print("\n截图: rss_filter_verify.png")

print("\n=== 验证完成 ===")

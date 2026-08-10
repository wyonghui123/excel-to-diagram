# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
try:
    page = cli.authenticated_navigate("/system/archdata?preset=scp&mode=debug",
        wait_for_selector=".embedded-chart-view", timeout=30000)
    page.wait_for_function("() => !!window.__archPage && !!window.__archPage.verify", timeout=30000)
    page.wait_for_timeout(2500)

    # 双击展开 MM
    page.evaluate("""() => {
        const svg = document.querySelector('svg.flowchart');
        const nodes = svg.querySelectorAll('g.node[id*="COLLAPSE_SD_MM"]');
        nodes[0].dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
        return true;
    }""")
    page.wait_for_timeout(2000)

    # 给 updateLayoutControlConfig 加插桩
    page.evaluate("""() => {
        const pinia = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia;
        const store = pinia._s.get('diagramConfig') || pinia._s.get('diagramConfigStore') || Object.values(Object.fromEntries(pinia._s)).find(s => s.layoutControlConfig);
        window.__store = store;
        const orig = store.updateLayoutControlConfig.bind(store);
        window.__updates = [];
        store.updateLayoutControlConfig = function(config) {
            const cfg = config?.value || config;
            const find = (list, key) => { for (const g of list||[]) { if ((g.elementCode||g.id)===key) return g; const r=find(g.children,key); if(r) return r; const r2=find(g.containers,key); if(r2) return r2; } return null; };
            const mm = find(cfg && cfg.groups, 'MM');
            window.__updates.push({
                ts: new Date().getTime(),
                mmCollapsed: mm ? mm.collapsed : 'MM-not-in-groups',
                stack: new Error().stack.split('\\n').slice(1,12).join(' < ').slice(0,600)
            });
            return orig(config);
        };
        return true;
    }""")

    # 切换 centerScopeHighlight
    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(1500)
    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(1500)

    print("[updateLayoutControlConfig calls]:")
    for u in page.evaluate("() => window.__updates"):
        print("  ts-offset:", u['ts'])
        print("  mmCollapsed:", u['mmCollapsed'])
        print("  stack:", u['stack'])
        print("  ---")
    print("[count]", len(page.evaluate("() => window.__updates")))
finally:
    cli.close()
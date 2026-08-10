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

    # 捕获 [WATCH] layoutControlConfig 日志
    page.evaluate("""() => {
        window.__watch_log = [];
        const orig = console.log;
        console.log = function(...a){
            const s = String(a[0]||'');
            if (s.includes('[WATCH] layoutControlConfig')) window.__watch_log.push(a.map(x=>String(x)).join(' '));
            orig.apply(console, a);
        };
        return true;
    }""")

    # 双击展开 MM
    page.evaluate("""() => {
        const svg = document.querySelector('svg.flowchart');
        const nodes = svg.querySelectorAll('g.node[id*="COLLAPSE_SD_MM"]');
        nodes[0].dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
        return true;
    }""")
    page.wait_for_timeout(2000)
    print("[expanded]")

    # 记录 configStore 与 chartConfig 中 MM 的 collapsed
    st = page.evaluate("""() => {
        const c = window.__archPage.chartConfig;
        const storeGroups = c.layoutControl && c.layoutControl.groups;
        let mm = null;
        const find = (list) => { for (const g of list||[]) { if ((g.elementCode||g.id)==='MM') mm=g; find(g.children); find(g.containers); } };
        find(storeGroups);
        return { chartConfigMMcollapsed: mm ? mm.collapsed : 'MM-not-in-chartConfig' };
    }""")
    print("[chartConfig MM collapsed]", st)
    # 双击展开后 configStore 里 MM collapsed
    st2 = page.evaluate("""() => {
        const pinia = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia;
        const store = pinia._s.get('diagramConfig') || pinia._s.get('diagramConfigStore');
        if (!store) return 'no-store';
        const lc = store.layoutControlConfig;
        const find = (list) => { for (const g of list||[]) { if ((g.elementCode||g.id)==='MM') return g.collapsed; const r=find(g.children); if(r!==undefined) return r; const r2=find(g.containers); if(r2!==undefined) return r2; } return undefined; };
        return { storeMMcollapsed: find(lc && lc.groups), storeExists: !!store, storeKeys: Object.keys(store) };
    }""")
    print("[configStore MM collapsed]", st2)

    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(2000)
    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(2000)

    print("[WATCH logs]:")
    for l in page.evaluate("() => window.__watch_log"):
        print("   ", l[:300])
    print("[WATCH log count]", len(page.evaluate("() => window.__watch_log")))
finally:
    cli.close()
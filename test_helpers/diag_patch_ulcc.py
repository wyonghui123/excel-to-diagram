# -*- coding: utf-8 -*-
# patch configStore.updateLayoutControlConfig, 捕获切换期间所有调用 + 调用栈
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
try:
    page = cli.authenticated_navigate("/system/archdata?preset=scp&mode=debug",
        wait_for_selector=".embedded-chart-view", timeout=30000)
    page.wait_for_function("() => !!window.__archPage && !!window.__archPage.verify", timeout=30000)
    page.wait_for_timeout(2500)

    page.evaluate("""() => {
        const svg = document.querySelector('svg.flowchart');
        const nodes = svg.querySelectorAll('g.node[id*="COLLAPSE_SD_MM"]');
        if (nodes.length === 0) return;
        nodes[0].dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
    }""")
    page.wait_for_timeout(2000)

    # patch updateLayoutControlConfig
    patch = page.evaluate("""() => {
        const store = window.__archPage.storeProxy;
        const orig = store.updateLayoutControlConfig;
        window.__ulccLog = [];
        const _f=(list)=>{for(const g of list||[]){if((g.elementCode||g.id)==='MM')return g;const r=_f(g.children);if(r)return r;const r2=_f(g.containers);if(r2)return r2;}return null;};
        store.updateLayoutControlConfig = function(cfg) {
            const mm = _f(cfg?.groups);
            window.__ulccLog.push({
                mmCollapsed: mm?.collapsed,
                groupCount: (cfg?.groups||[]).length,
                stack: (new Error().stack||'').split('\\n').slice(1,10).join(' | ')
            });
            return orig.call(this, cfg);
        };
        return { ok:true };
    }""")
    print("[patch]", json.dumps(patch))
    # 清空双击阶段日志
    page.evaluate("() => { window.__ulccLog = []; return true; }")

    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(2000)

    logs = page.evaluate("() => window.__ulccLog")
    print(f"=== updateLayoutControlConfig 调用 ({len(logs)} 次) ===")
    for i, l in enumerate(logs):
        print(f"[{i}] mmCollapsed={l['mmCollapsed']} groupCount={l['groupCount']}")
        print(f"    stack: {l['stack'][:500]}")
        print()
finally:
    cli.close()
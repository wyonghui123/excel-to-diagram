# -*- coding: utf-8 -*-
# Proxy trap chartConfig.layoutControl.groups 的 set, 捕获替换来源
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
try:
    page = cli.authenticated_navigate("/system/archdata?preset=scp&mode=debug",
        wait_for_selector=".embedded-chart-view", timeout=30000)
    page.wait_for_function("() => !!window.__archPage && !!window.__archPage.verify", timeout=30000)
    page.wait_for_timeout(2500)

    # 先 trap chartConfig.layoutControl.groups set
    trap = page.evaluate("""() => {
        const chart = window.__archPage.chartConfig;
        window.__groupsSetLog = [];
        let _groups = chart.layoutControl.groups;
        try {
            Object.defineProperty(chart.layoutControl, 'groups', {
                configurable: true,
                enumerable: true,
                get(){ return _groups; },
                set(v){
                    const _f=(list)=>{for(const g of list||[]){if((g.elementCode||g.id)==='MM')return g.collapsed;const r=_f(g.children);if(r!==undefined)return r;const r2=_f(g.containers);if(r2!==undefined)return r2;}return undefined;};
                    window.__groupsSetLog.push({ mmCollapsed: _f(v), topCount: (v||[]).length, stack: (new Error().stack||'').split('\\n').slice(1,9).join(' | ') });
                    _groups = v;
                }
            });
            return { ok:true };
        } catch(e) { return { ok:false, reason:String(e&&e.message||e) }; }
    }""")
    print("[trap groups set]", json.dumps(trap))

    # 双击展开 MM
    page.evaluate("""() => {
        const svg = document.querySelector('svg.flowchart');
        const nodes = svg.querySelectorAll('g.node[id*="COLLAPSE_SD_MM"]');
        if (nodes.length === 0) return;
        nodes[0].dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
    }""")
    page.wait_for_timeout(2000)
    # 清空, 只看切换阶段
    page.evaluate("() => { window.__groupsSetLog = []; return true; }")

    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(2000)

    logs = page.evaluate("() => window.__groupsSetLog")
    print(f"=== chartConfig.layoutControl.groups 被替换 ({len(logs)} 次) ===")
    for i, l in enumerate(logs):
        print(f"[{i}] mmCollapsed={l['mmCollapsed']} topCount={l['topCount']}")
        print(f"    stack: {l['stack'][:500]}")
        print()
finally:
    cli.close()
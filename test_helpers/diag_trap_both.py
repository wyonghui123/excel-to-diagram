# -*- coding: utf-8 -*-
# 陷阱 store + chartConfig 的 MM.collapsed, 并检测对象是否被整体替换
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
try:
    page = cli.authenticated_navigate("/system/archdata?preset=scp&mode=debug",
        wait_for_selector=".embedded-chart-view", timeout=30000)
    page.wait_for_function("() => !!window.__archPage && !!window.__archPage.verify", timeout=30000)
    page.wait_for_timeout(2500)

    console_logs = []
    def on_console(msg):
        text = msg.text
        if any(k in text for k in ['DBG-MM', 'WATCH', 'SYNC', 'DBG-store', 'TRACE', 'DIAG', 'DBG-syncLayout', 'updateLayoutControlConfig', 'expandLevel', 'CTX', 'DBL']):
            console_logs.append(text[:200])
    page.on("console", on_console)
    page.on("pageerror", lambda e: console_logs.append('PAGEERR: ' + str(e)))

    page.evaluate("""() => {
        const svg = document.querySelector('svg.flowchart');
        const nodes = svg.querySelectorAll('g.node[id*="COLLAPSE_SD_MM"]');
        if (nodes.length === 0) return;
        nodes[0].dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
    }""")
    page.wait_for_timeout(2000)

    init = page.evaluate("""() => {
        const _f=(list)=>{for(const g of list||[]){if((g.elementCode||g.id)==='MM')return g;const r=_f(g.children);if(r)return r;const r2=_f(g.containers);if(r2)return r2;}return null;};
        const store = window.__archPage.storeProxy;
        const chart = window.__archPage.chartConfig;
        const storeMM = _f(store?.layoutControlConfig?.groups);
        const chartMM = _f(chart?.layoutControl?.groups);
        window.__trapLog = [];
        const trap=(obj, tag)=>{
            if(!obj) return;
            let val = obj.collapsed;
            try {
                Object.defineProperty(obj, 'collapsed', {
                    configurable:true, enumerable:true,
                    get(){ return val; },
                    set(v){
                        if(v!==val){
                            window.__trapLog.push({ tag, from:val, to:v, stack:(new Error().stack||'').split('\\n').slice(1,14).join(' | ') });
                        }
                        val=v;
                    }
                });
            } catch(e){ window.__trapLog.push({ tag, err:String(e&&e.message||e) }); }
        };
        trap(storeMM, 'storeMM');
        trap(chartMM, 'chartMM');
        // 记录引用, 用于切换后对比是否被替换
        window.__refSnapshot = {
            storeLCC: store?.layoutControlConfig,
            chartLC: chart?.layoutControl,
            storeMM, chartMM
        };
        return {
            storeMM_before: storeMM?.collapsed,
            chartMM_before: chartMM?.collapsed,
            storeAliasChart: store?.layoutControlConfig === chart?.layoutControl
        };
    }""")
    print("[init]", json.dumps(init))

    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(2000)

    print("[console-logs]")
    for t in console_logs[:40]:
        print("  ", t)

    result = page.evaluate("""() => {
        const store = window.__archPage.storeProxy;
        const chart = window.__archPage.chartConfig;
        const _f=(list)=>{for(const g of list||[]){if((g.elementCode||g.id)==='MM')return g;const r=_f(g.children);if(r)return r;const r2=_f(g.containers);if(r2)return r2;}return null;};
        const ref = window.__refSnapshot;
        return {
            trapLog: window.__trapLog,
            storeLCC_replaced: ref.storeLCC !== store?.layoutControlConfig,
            chartLC_replaced: ref.chartLC !== chart?.layoutControl,
            storeMM_replaced: ref.storeMM !== _f(store?.layoutControlConfig?.groups),
            chartMM_replaced: ref.chartMM !== _f(chart?.layoutControl?.groups),
            storeMM_after: _f(store?.layoutControlConfig?.groups)?.collapsed,
            chartMM_after: _f(chart?.layoutControl?.groups)?.collapsed
        };
    }""")
    print("[after]")
    print("  trapLog:", json.dumps([{t:l.get('tag'),f:l.get('from'),to:l.get('to'),err:l.get('err'),s:l.get('stack')} for l in result['trapLog']][:10], default=str)[:1500])
    print("  storeLCC_replaced:", result['storeLCC_replaced'], "chartLC_replaced:", result['chartLC_replaced'])
    print("  storeMM_replaced:", result['storeMM_replaced'], "chartMM_replaced:", result['chartMM_replaced'])
    print("  storeMM_after:", result['storeMM_after'], "chartMM_after:", result['chartMM_after'])
    for l in result['trapLog']:
        if 'stack' in l:
            print("  STACK:", l['stack'][:400])
finally:
    cli.close()
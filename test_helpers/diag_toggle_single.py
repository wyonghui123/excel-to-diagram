# -*- coding: utf-8 -*-
# 单次切换诊断: 捕获切换前 store/chart 状态、引用是否别名、以及切换瞬间首个事件
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
        if any(k in text for k in ['DBG-MM', 'WATCH', 'SYNC', 'DBG-store', 'TRACE', 'DIAG', 'DBG-syncLayout', 'updateLayoutControlConfig', 'collapsed']):
            console_logs.append((msg.type, text))
    page.on("console", on_console)
    page.on("pageerror", lambda e: console_logs.append(('pageerror', str(e))))

    # 双击展开 MM
    page.evaluate("""() => {
        const svg = document.querySelector('svg.flowchart');
        const nodes = svg.querySelectorAll('g.node[id*="COLLAPSE_SD_MM"]');
        if (nodes.length === 0) return 'no-node';
        nodes[0].dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
        return 'dblclicked';
    }""")
    page.wait_for_timeout(2000)
    console_logs.clear()

    # 切换前快照: 引用是否别名 + MM 状态
    pre = page.evaluate("""() => {
        const _f=(list)=>{for(const g of list||[]){if((g.elementCode||g.id)==='MM')return g;const r=_f(g.children);if(r)return r;const r2=_f(g.containers);if(r2)return r2;}return null;};
        const storeGroup = _f(window.__archPage.storeProxy?.groups);
        const chartGroup = _f(window.__archPage.chartConfig?.layoutControl?.groups);
        return {
            storeExists: !!window.__archPage.storeProxy,
            aliased: window.__archPage.storeProxy?.groups === window.__archPage.chartConfig?.layoutControl?.groups,
            storeMMcollapsed: storeGroup?.collapsed,
            chartMMcollapsed: chartGroup?.collapsed
        };
    }""")
    print("[pre-toggle]", json.dumps(pre))

    # 单次切换
    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = false; return true; }")
    page.wait_for_timeout(1500)

    print(f"=== 切换后捕获 {len(console_logs)} 条日志 ===")
    for typ, text in console_logs[:40]:
        print(f"[{typ}] {text[:300]}")

    after = page.evaluate("""() => {
        const d = window.__archPage.diag();
        return {
            mmRender: d.render.filter(x => x.key === 'MM').map(x => x.collapsed),
            storeMM: d.store.filter(x => x.key === 'MM').map(x => x.collapsed),
            chartMM: d.chart.filter(x => x.key === 'MM').map(x => x.collapsed),
            groupManualSet: d.config.groupManualSet
        };
    }""")
    print("[after-toggle]", json.dumps(after))
finally:
    cli.close()
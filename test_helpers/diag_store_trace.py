# -*- coding: utf-8 -*-
"""捕获 updateLayoutControlConfig 被以 MM collapsed=true 调用的调用栈."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
try:
    page = cli.authenticated_navigate("/system/archdata?preset=scp&mode=debug",
        wait_for_selector=".embedded-chart-view", timeout=30000)
    page.wait_for_function("() => !!window.__archPage && !!window.__archPage.verify", timeout=30000)
    page.wait_for_timeout(2500)

    traces = []
    def on_console(msg):
        t = msg.text
        if 'DBG-MM' in t or 'DBG-syncLayout' in t:
            traces.append(t)
    page.on('console', on_console)
    page.evaluate("""() => {
        window.__dbg_stack = [];
        const orig = console.trace;
        console.trace = function(...a) {
            const s = String(a[0]||'');
            if (s.includes('DBG-store-MM-true')) {
                window.__dbg_stack.push(new Error().stack.split('\\n'));
            }
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
    page.wait_for_timeout(2500)
    traces.append("=== BEFORE TOGGLE ===")

    # 切换 centerScopeHighlight
    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(2000)
    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(2000)

    print("=== updateLayoutControlConfig MM=true traces ===")
    for t in traces:
        print(t[:300])
        print("---")
    stacks = page.evaluate("() => window.__dbg_stack")
    print("=== MM=true caller stacks ===")
    for st in stacks:
        print("STACK:")
        for line in st[:12]:
            print("  ", line[:200])
        print("---")
finally:
    cli.close()
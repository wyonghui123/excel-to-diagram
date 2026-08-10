# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
try:
    page = cli.authenticated_navigate("/system/archdata?preset=scp&mode=debug",
        wait_for_selector=".embedded-chart-view", timeout=30000)
    page.wait_for_function("() => !!window.__archPage && !!window.__archPage.verify", timeout=30000)
    page.wait_for_timeout(2500)

    page.evaluate("""() => {
        window.__sync_log = [];
        const orig = console.log;
        console.log = function(...a){
            const s = String(a[0]||'');
            window.__sync_log.push(a.map(x=>String(x)).join(' '));
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
    print("[expanded done]")

    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(1500)
    print("[toggled once]")

    print("[sync logs during toggle]:")
    for l in page.evaluate("() => window.__sync_log"):
        if '[DIAG-sync]' in l:
            print("   ", l)
    print("[total sync count]", len([l for l in page.evaluate("() => window.__sync_log") if '[DIAG-sync]' in l]))
finally:
    cli.close()
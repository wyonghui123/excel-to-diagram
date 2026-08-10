# -*- coding: utf-8 -*-
"""捕获切换 centerScopeHighlight 时的 console 日志, 定位 renderMermaid 触发源."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
try:
    page = cli.authenticated_navigate("/system/archdata?preset=scp&mode=debug",
        wait_for_selector=".embedded-chart-view", timeout=30000)
    page.wait_for_function("() => !!window.__archPage && !!window.__archPage.verify", timeout=30000)
    page.wait_for_timeout(2500)

    # 收集 console 消息
    logs = []
    def on_console(msg):
        text = msg.text
        if any(k in text for k in ['[WATCH] layoutControlConfig', 'renderMermaid', 'TRACE-generateDiagram',
                                    '[DBL]', '[CTX]', 'updateColorsOnly', 'updateVisibilityOnly', '[DBG]',
                                    'groupManualSet', 'collapsed', 'expandGroup', 'expanded']):
            logs.append(text)
    page.on('console', on_console)

    # 双击展开 MM
    page.evaluate("""() => {
        const svg = document.querySelector('svg.flowchart');
        const nodes = svg.querySelectorAll('g.node[id*="COLLAPSE_SD_MM"]');
        nodes[0].dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
        return true;
    }""")
    page.wait_for_timeout(2500)
    logs.append("=== after dblclick, before toggle ===")

    # 切换 centerScopeHighlight
    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(2000)
    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(2000)

    print("=== console logs during toggle ===")
    if not logs:
        print("(none captured)")
    for l in logs:
        print(l[:300])
finally:
    cli.close()
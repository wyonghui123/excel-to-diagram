# -*- coding: utf-8 -*-
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
try:
    page = cli.authenticated_navigate("/system/archdata?preset=scp&mode=debug",
        wait_for_selector=".embedded-chart-view", timeout=30000)
    page.wait_for_function("() => !!window.__archPage && !!window.__archPage.verify", timeout=30000)
    page.wait_for_function("() => !!document.querySelector('.embedded-chart-view svg')", timeout=30000)
    page.wait_for_timeout(2000)

    # 打印所有 g.node 和 g.cluster 的 id 和文本
    info = page.evaluate("""() => {
        const svg = document.querySelector('.embedded-chart-view svg');
        const nodes = Array.from(svg.querySelectorAll('g.node')).map(g => ({id: g.id, txt: (g.textContent||'').replace(/\\s+/g,' ').slice(0,40)}));
        const clusters = Array.from(svg.querySelectorAll('g.cluster')).map(g => ({id: g.id, txt: (g.textContent||'').replace(/\\s+/g,' ').slice(0,40)}));
        return { nodes, clusters };
    }""")
    print("=== NODES ===")
    for n in info['nodes']:
        print("  ", n)
    print("=== CLUSTERS ===")
    for c in info['clusters']:
        print("  ", c)
    cli.screenshot("diag_nodes.png")
finally:
    cli.close()
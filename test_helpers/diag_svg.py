# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
try:
    page = cli.authenticated_navigate("/system/archdata?preset=scp&mode=debug",
        wait_for_selector=".embedded-chart-view", timeout=30000)
    page.wait_for_function("() => !!window.__archPage && !!window.__archPage.verify", timeout=30000)
    page.wait_for_timeout(3000)
    # 用 __archPage.captureNodeSignature 拿已渲染信息
    sig = page.evaluate("() => window.__archPage.captureNodeSignature()")
    print("[sig]", {k: v for k, v in sig.items() if k != 'nodeIds'})
    print("[nodeIds]", sig.get('nodeIds'))
    # 查找所有 svg 位置
    svgs = page.evaluate("""() => {
        return Array.from(document.querySelectorAll('svg')).map(s => ({
            cls: s.getAttribute('class'), id: s.id,
            nodes: s.querySelectorAll('g.node').length,
            clusters: s.querySelectorAll('g.cluster').length
        }));
    }""")
    print("[svgs]", svgs)
    # 查找 '采购供应' 文本所在元素
    found = page.evaluate("""() => {
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        const res = [];
        while (walker.nextNode()) {
            const t = walker.currentNode.textContent || '';
            if (t.includes('采购供应')) {
                res.push(t.trim().slice(0,40));
            }
        }
        return res.slice(0, 10);
    }""")
    print("[采购供应 texts]", found)
    cli.screenshot("diag_svg.png")
finally:
    cli.close()
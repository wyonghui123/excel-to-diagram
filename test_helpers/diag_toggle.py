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

    # 确认修复代码是否加载: 检查源文件文本
    ver = page.evaluate("""() => {
        // 通过检查 __archPage 是否暴露了足够调试信息来判断
        return {
            hasDiag: !!window.__archPage.diag,
            hasVerify: !!window.__archPage.verify,
            hasCapture: !!window.__archPage.captureNodeSignature,
            hasDebug: !!window.__archPage.debug
        };
    }""")
    print("[api]", ver)

    # 双击展开 MM
    dbl = page.evaluate("""() => {
        const svg = document.querySelector('svg.flowchart');
        const nodes = svg.querySelectorAll('g.node[id*="COLLAPSE_SD_MM"]');
        if (nodes.length === 0) return 'no-node';
        nodes[0].dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
        return 'dblclicked';
    }""")
    print("[dbl]", dbl)
    page.wait_for_timeout(2000)
    afterExpand = page.evaluate("() => window.__archPage.captureNodeSignature()")
    print("[after-expand hash]", afterExpand['hash'], "MM collapsed render:",
          page.evaluate("() => { const d=window.__archPage.diag(); const g=d.render.filter(x=>x.key==='MM'); return g.map(x=>x.collapsed); }"))

    # 监听 console trace generateDiagram
    page.evaluate("""() => {
        window.__trace_log = [];
        const orig = console.trace;
        console.trace = function(...a) {
            const s = String(a[0]||'');
            if (s.includes('TRACE-generateDiagram')) window.__trace_log.push(s);
            orig.apply(console, a);
        };
        return true;
    }""")

    # 切换 centerScopeHighlight
    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(2000)
    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(2000)

    trace = page.evaluate("() => window.__trace_log")
    print("[TRACE generateDiagram count]", len(trace))
    for t in trace[:5]:
        print("   ", t)

    afterToggle = page.evaluate("() => window.__archPage.captureNodeSignature()")
    print("[after-toggle hash]", afterToggle['hash'], "MM collapsed render:",
          page.evaluate("() => { const d=window.__archPage.diag(); const g=d.render.filter(x=>x.key==='MM'); return g.map(x=>x.collapsed); }"))
    print("[hash changed?]", afterExpand['hash'] != afterToggle['hash'])
finally:
    cli.close()
# -*- coding: utf-8 -*-
# 捕获切换 centerScopeHighlight 期间的全部 console 消息, 定位 MM 折叠源头
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
try:
    page = cli.authenticated_navigate("/system/archdata?preset=scp&mode=debug",
        wait_for_selector=".embedded-chart-view", timeout=30000)
    page.wait_for_function("() => !!window.__archPage && !!window.__archPage.verify", timeout=30000)
    page.wait_for_timeout(2500)

    # 捕获所有 console 消息
    page.on("console", lambda msg: None)  # 需要先注册, 但 playwright 直接捕获
    console_logs = []
    def on_console(msg):
        text = msg.text
        if any(k in text for k in ['DBG-MM', 'WATCH', 'SYNC', 'DBG-store', 'TRACE', 'DIAG', 'CTX', 'DBL', 'updateLayoutControlConfig', 'collapsed']):
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
    console_logs.clear()  # 清空展开阶段的日志, 只保留切换阶段
    print("=== 已双击展开, 清空日志, 开始切换 ===")

    # 切换 centerScopeHighlight (区分 -> 不区分 -> 区分)
    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(2000)
    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(2000)

    print(f"=== 捕获到 {len(console_logs)} 条相关日志 ===")
    for typ, text in console_logs[:60]:
        print(f"[{typ}] {text[:400]}")

    after = page.evaluate("""() => {
        const d = window.__archPage.diag();
        const mm = d.render.filter(x => x.key === 'MM').map(x => x.collapsed);
        return {
            mmRender: mm,
            storeMM: d.store.filter(x => x.key === 'MM').map(x => x.collapsed),
            chartMM: d.chart.filter(x => x.key === 'MM').map(x => x.collapsed),
            groupManualSet: d.config.groupManualSet,
            expandLevelUserSet: d.config.expandLevel
        };
    }""")
    print("[after-toggle]", json.dumps(after))
finally:
    cli.close()

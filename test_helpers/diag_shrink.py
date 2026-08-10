# -*- coding: utf-8 -*-
"""展开到 BO 级后切换 centerScopeHighlight, 测量节点几何 + 截图对比.
目的: 决定性判断"图表缩小"是真实 SVG/节点几何变化, 还是 legend/颜色视觉差.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

def main():
    cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
    try:
        page = cli.authenticated_navigate("/system/archdata?preset=scp&mode=debug", timeout=20000)
        for _ in range(60):
            if page.evaluate("() => !!(window.__archPage && window.__archPage.debug && window.__archPage.debug.store)"):
                break
            page.wait_for_timeout(1500)
        page.wait_for_timeout(2000)

        # 展开到 领域 级 (用户指定复现场景)
        page.evaluate("() => window.__archPage.debug.setExpandLevel('domain')")
        page.wait_for_timeout(2500)

        def measure(tag):
            return page.evaluate("""() => {
                const chartSvg = document.querySelector('.mermaid-content svg, pre.mermaid svg');
                const vb = chartSvg ? chartSvg.getAttribute('viewBox') : null;
                const r = chartSvg ? chartSvg.getBoundingClientRect() : null;
                // 所有 BO 叶节点 rect 的中心点集合 (检测节点是否移动/缩放)
                let nodes = [];
                document.querySelectorAll('.mermaid-content g.node, .mermaid-content .node').forEach(n => {
                    const nlab = n.querySelector('.nodeLabel, .label');
                    if (!nlab) return;
                    let b;
                    try { b = n.getBBox(); } catch(e) { return; }
                    if (!b) return;
                    nodes.push({ cx: Math.round(b.x+b.width/2), cy: Math.round(b.y+b.height/2), w: Math.round(b.width), h: Math.round(b.height), t: (nlab.textContent||'').slice(0,12) });
                });
                const lr = window.__archPage.diag().renderMeta.lastRender;
                const legend = document.querySelector('.color-legend-panel');
                const legR = legend ? legend.getBoundingClientRect() : null;
                return {
                    svg: r ? {w:Math.round(r.width), h:Math.round(r.height)} : null,
                    viewBox: vb,
                    contentTransform: (document.querySelector('.mermaid-content')||{}).style ? document.querySelector('.mermaid-content').style.transform : null,
                    nodeCount: nodes.length,
                    nodes: nodes.slice(0, 8),
                    legend: legR ? {w:Math.round(legR.width), h:Math.round(legR.height)} : null,
                    render: lr ? {incremental: lr.incremental, nodeCount: lr.nodeCount} : undefined
                };
            }""")

        print("展开领域 初始(csh=true):", measure('t0'))
        toggles = [False, True, False, True, False, True]
        for i, val in enumerate(toggles):
            page.evaluate(f"() => window.__archPage.debug.store.updateCenterScopeHighlight({str(val).lower()})")
            page.wait_for_timeout(1200)
            print(f"csh={val}:", measure(i))
            cli.screenshot(f"shrink_domain_csh_{val}_{i}.png")
        cli.screenshot("shrink_domain_final.png")
    finally:
        cli.close()

if __name__ == "__main__":
    main()

# -*- coding: utf-8 -*-
"""精确复现: 先折叠到 domain, 再切换区分. 对比 legend 对象范围项."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

def legend(page):
    return page.evaluate("""() => {
        const panel = document.querySelector('.color-legend-panel');
        const list = panel ? panel.querySelector('div[style*="flex-direction: column"]') : null;
        const items = list ? Array.from(list.children).map(el => el.textContent.trim()).filter(Boolean) : null;
        const lr = window.__archPage.diag().renderMeta.lastRender;
        return { items, csh: window.__archPage.chartConfig.centerScopeHighlight, render: lr ? {incremental: lr.incremental, nodeCount: lr.nodeCount} : null };
    }""")

def main():
    cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
    try:
        page = cli.authenticated_navigate("/system/archdata?preset=scp&mode=debug", timeout=20000)
        for _ in range(60):
            if page.evaluate("() => !!(window.__archPage && window.__archPage.debug && window.__archPage.debug.store)"):
                break
            page.wait_for_timeout(1000)
        page.wait_for_timeout(1500)

        # 先折叠到领域级 (不区分)
        page.evaluate("() => window.__archPage.debug.setExpandLevel('domain')")
        page.wait_for_timeout(2000)
        print("domain折叠, 初始(区分默认):", legend(page))

        # 再切不区分
        page.evaluate("() => window.__archPage.chartConfig.centerScopeHighlight = false")
        page.wait_for_timeout(1500)
        print("domain折叠, 切不区分:", legend(page))

        # 再切区分
        page.evaluate("() => window.__archPage.chartConfig.centerScopeHighlight = true")
        page.wait_for_timeout(1500)
        print("domain折叠, 切回区分:", legend(page))
    finally:
        cli.close()

if __name__ == "__main__":
    main()
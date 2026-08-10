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

    # 双击展开 MM
    page.evaluate("""() => {
        const svg = document.querySelector('svg.flowchart');
        const nodes = svg.querySelectorAll('g.node[id*="COLLAPSE_SD_MM"]');
        nodes[0].dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
        return true;
    }""")
    page.wait_for_timeout(2000)

    # 捕获切换前后 EmbeddedChartView layoutControlConfig computed 的完整签名
    # 通过监听 console，但更可靠：直接在切换后立即读取 chartConfig 和 configStore 中 MM 的 collapsed
    # 对比三种源
    def snap():
        return page.evaluate("""() => {
            const pinia = document.querySelector('#app').__vue_app__.config.globalProperties.$pinia;
            const store = pinia._s.get('diagramConfig') || pinia._s.get('diagramConfigStore') || (Object.values(Object.fromEntries(pinia._s)).find(s => s.layoutControlConfig));
            const find = (list, key) => { for (const g of list||[]) { if ((g.elementCode||g.id)===key) return g; const r=find(g.children,key); if(r) return r; const r2=find(g.containers,key); if(r2) return r2; } return null; };
            const mmInStore = find(store.layoutControlConfig && store.layoutControlConfig.groups, 'MM');
            const mmInChart = find(window.__archPage.chartConfig.layoutControl && window.__archPage.chartConfig.layoutControl.groups, 'MM');
            // mergedGroups 来自 diagramData.layoutControlConfig (unified)
            const dd = window.__archPage.diagramData && (window.__archPage.diagramData.layoutControlConfig || window.__archPage.diagramData.diagramData?.layoutControlConfig);
            const mmInData = dd ? find(dd.groups, 'MM') : null;
            return {
                store: mmInStore ? { collapsed: mmInStore.collapsed, enabled: mmInStore.enabled, title: mmInStore.title } : 'not-found',
                chart: mmInChart ? { collapsed: mmInChart.collapsed, enabled: mmInChart.enabled, title: mmInChart.title } : 'not-found',
                data: mmInData ? { collapsed: mmInData.collapsed, enabled: mmInData.enabled, title: mmInData.title } : 'not-found'
            };
        }""")

    print("[before toggle]", json.dumps(snap(), ensure_ascii=False))
    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(1500)
    print("[mid toggle]", json.dumps(snap(), ensure_ascii=False))
    page.evaluate("() => { window.__archPage.chartConfig.centerScopeHighlight = !window.__archPage.chartConfig.centerScopeHighlight; return true; }")
    page.wait_for_timeout(1500)
    print("[after toggle]", json.dumps(snap(), ensure_ascii=False))
finally:
    cli.close()
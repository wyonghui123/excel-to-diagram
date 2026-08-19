# -*- coding: utf-8 -*-
"""诊断 v28: 检查 cluster 的 data-container-code 属性 + 当前 collectHiddenState 隐藏集合"""
import sys, time, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3004'
cli = PlaywrightCLI()
page = cli._ensure_browser()
page.on('pageerror', lambda e: print('PAGEERR:', str(e)[:200]))

page.goto(f"{BASE}/api/v1/auth/dev-login?username=admin", wait_until='domcontentloaded', timeout=15000)
page.goto(f"{BASE}/system/archdata?productCode=TTTTT000&versionCode=V11&view=chart&scopeCode=SCP&mode=debug",
          wait_until='domcontentloaded', timeout=20000)
for _ in range(12):
    time.sleep(2)
    if page.evaluate("() => !!document.querySelector('.mermaid svg')"):
        break
print('SVG ready')
page.evaluate("() => window.__archPage?.debug?.setExpandLevel('businessObject')")
time.sleep(4)

print('=== cluster 属性 ===')
print(json.dumps(page.evaluate("""() => {
    const svg = document.querySelector('.mermaid svg')
    return Array.from(svg.querySelectorAll('g.cluster')).map(c => ({
        id: c.id,
        dataContainerCode: c.getAttribute('data-container-code'),
        childRect: !!c.querySelector('rect')
    }))
}"""), ensure_ascii=False, default=str))

print('\n=== 面板树 DP 分组结构 (containers) ===')
print(json.dumps(page.evaluate("""() => {
    const lc = window.__archPage?.chartConfig?.layoutControl
    function walk(list) {
        for (const g of list || []) {
            if ((g.elementCode || g.id) === 'DP') {
                return { code: g.elementCode, id: g.id, title: g.title, containers: (g.containers||[]).map(c => ({ id: c.id, nodes: c.nodes, isVirtual: c.isVirtual })).slice(0,3) }
            }
            const r = walk(g.children); if (r) return r
        }
        return null
    }
    return walk(lc && lc.groups)
}"""), ensure_ascii=False, default=str))
cli.close()

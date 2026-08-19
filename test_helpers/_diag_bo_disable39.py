# -*- coding: utf-8 -*-
"""诊断 v39: 空自定义分组 → 合并树是否含它 + mermaid 代码是否有其 subgraph + SVG 集群"""
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

# 新建空自定义分组
print('新建:', page.evaluate("""() => {
    const lc = window.__archPage?.chartConfig?.layoutControl
    const copy = JSON.parse(JSON.stringify(lc))
    copy.groups.push({ id: 'grp_custom_empty', title: '空自定义分组', groupType: 'custom', direction: 'TB',
        visible: true, enabled: true, collapsed: false,
        style: { fill: '#ffffff', stroke: '#666666', strokeWidth: 2, strokeDasharray: '' },
        containers: [], children: [], parentId: undefined })
    Object.assign(window.__archPage.chartConfig.layoutControl, copy)
    return 'pushed'
}"""))
time.sleep(5)

print(json.dumps(page.evaluate("""() => {
    const out = {}
    // 1) 合并树 (debugLayout.steps.afterMembership) 是否含空分组
    const steps = window.__archPage?.debugLayout?.steps || window.__archPage?.debugLayout
    out.hasMergeSteps = !!steps
    // 2) mermaid 代码
    const code = window.__archPage?.mermaid?.lastRenderedCode || ''
    out.hasSubgraph = code.includes('grp_custom_empty')
    out.subgraphLines = code.split('\\n').filter(l => l.includes('grp_custom_empty') || l.includes('空自定义')).slice(0, 5)
    // 3) SVG 集群
    const svg = document.querySelector('.mermaid svg')
    out.svgClusters = svg ? Array.from(svg.querySelectorAll('g.cluster')).map(e => e.getAttribute('data-container-code') || e.id).filter(Boolean) : []
    return out
}"""), ensure_ascii=False, default=str))
cli.close()

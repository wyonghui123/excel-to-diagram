# -*- coding: utf-8 -*-
"""验证 [FIX 2026-08-19 二阶段]: 默认展开层级下新建(空)自定义分组 → 渲染为容器

覆盖两处:
1. applyContainerMembership 补入自定义分组到渲染树
2. expandLevel 不再折叠用户自定义分组 → 不渲染成 COLLAPSE 聚合节点
"""
import sys, time, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3004'
errs = []
cli = PlaywrightCLI()
page = cli._ensure_browser()
page.on('pageerror', lambda e: errs.append(str(e)[:300]))

page.goto(f"{BASE}/api/v1/auth/dev-login?username=admin", wait_until='domcontentloaded', timeout=15000)
page.goto(f"{BASE}/system/archdata?productCode=TTTTT000&versionCode=V11&view=chart&scopeCode=SCP&mode=debug",
          wait_until='domcontentloaded', timeout=20000)
for _ in range(12):
    time.sleep(2)
    if page.evaluate("() => !!document.querySelector('.mermaid svg')"):
        break
print('SVG ready')

def expand_level():
    return page.evaluate("() => window.__archPage?.expandState?.expandLevel || '?'")

def add_empty_group(title='自定义分组E2E'):
    return page.evaluate("""(title) => {
        const lc = window.__archPage?.chartConfig?.layoutControl
        if (!lc || !lc.groups) return 'no layoutControl'
        const copy = JSON.parse(JSON.stringify(lc))
        const id = 'grp_custom_e2e'
        copy.groups = copy.groups.filter(g => g.id !== id)
        copy.groups.push({id, title, groupType: 'custom', direction: 'TB',
            visible: true, enabled: true, collapsed: false, containers: [], children: [], parentId: null})
        Object.assign(window.__archPage.chartConfig.layoutControl, copy)
        return 'added'
    }""", title)

def code_has_sub():
    return page.evaluate("""() => {
        const code = window.__archPage?.mermaid?.lastRenderedCode || ''
        return {
            subgraph: code.includes('subgraph G_grp_custom_e2e["自定义分组E2E"]'),
            collapse: code.includes('COLLAPSE_grp_custom_e2e')
        }
    }""")

def svg_cluster():
    return page.evaluate("""() => {
        const svg = document.querySelector('.mermaid svg')
        if (!svg) return { svg: false }
        const clusters = Array.from(svg.querySelectorAll('g.cluster'))
        const all = clusters.map(c => ({ id: c.id, label: (c.querySelector('.cluster-label') || {}).textContent || '', fo: !!(c.querySelector('.cluster-label foreignObject')) }))
        return { svg: true, clusterCount: clusters.length, custom: all.filter(c => c.id.includes('grp_custom_e2e') || c.label.includes('自定义分组E2E')) }
    }""")

print('expandLevel:', expand_level())
print('BEFORE clusters:', svg_cluster())
print('add:', add_empty_group())
time.sleep(8)
print('code:', json.dumps(code_has_sub(), ensure_ascii=False))
print('AFTER clusters:', json.dumps(svg_cluster(), ensure_ascii=False))

# 清理
page.evaluate("""() => {
    const lc = window.__archPage?.chartConfig?.layoutControl
    const copy = JSON.parse(JSON.stringify(lc))
    copy.groups = copy.groups.filter(g => g.id !== 'grp_custom_e2e')
    Object.assign(window.__archPage.chartConfig.layoutControl, copy)
    return 'cleaned'
}""")
time.sleep(6)
print('CLEAN clusters:', svg_cluster()['clusterCount'])
print('errors:', errs[:5])
cli.close()

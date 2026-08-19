# -*- coding: utf-8 -*-
"""验证 [FIX 2026-08-19 修订]: 图表的"空分组→节点, 非空分组→容器"统一逻辑

覆盖:
1. 空自定义分组(末端叶子, 无 BO) → 上提为 COLLAPSE 聚合节点 (非空容器框)
2. 拖入 BO 后 → 自动变 subgraph 容器 (有可见内容)
3. 移除 BO 后 → 回到 COLLAPSE 节点
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
page.evaluate("() => window.__archPage?.debug?.setExpandLevel('businessObject')")
time.sleep(5)

ID = 'grp_custom_e2e'
TITLE = '自定义分组E2E'

def mutate(fn):
    return page.evaluate("""(fnStr) => {
        const lc = window.__archPage?.chartConfig?.layoutControl
        if (!lc || !lc.groups) return 'no layoutControl'
        const copy = JSON.parse(JSON.stringify(lc))
        const fn = new Function('copy', 'id', 'title', 'return (' + fnStr + ')(copy, id, title)')
        const res = fn(copy, '""" + ID + """', '""" + TITLE + """')
        Object.assign(window.__archPage.chartConfig.layoutControl, copy)
        return res
    }""", fn)

def st():
    return page.evaluate("""() => {
        const code = window.__archPage?.mermaid?.lastRenderedCode || ''
        const svg = document.querySelector('.mermaid svg')
        const nodes = svg ? Array.from(svg.querySelectorAll('g.node')).map(n => (n.querySelector('text')||{}).textContent || '') : []
        return {
            subgraph: code.includes('subgraph G_grp_custom_e2e["自定义分组E2E"]'),
            collapse: code.includes('COLLAPSE_grp_custom_e2e'),
            hasCollapseNode: nodes.some(t => t.includes('自定义分组E2E')),
            cluster: svg ? !!Array.from(svg.querySelectorAll('g.cluster')).find(c => c.id.includes('grp_custom_e2e')) : null
        }
    }""")

# 场景1: 空分组 → COLLAPSE 节点
print('\n[场景1] 新增空自定义分组')
print('  add:', mutate("""(copy, id, title) => {
    copy.groups = copy.groups.filter(g => g.id !== id)
    copy.groups.push({id, title, groupType: 'custom', direction: 'TB',
        visible: true, enabled: true, collapsed: false, containers: [], children: [], parentId: null})
    return 'added-empty'
}"""))
time.sleep(8)
print('  状态:', json.dumps(st(), ensure_ascii=False), '→ 期望 collapse=true 且非 subgraph')

# 场景2: 拖入 BO → 变容器
print('\n[场景2] 拖入 1 个 BO')
# 先找一个 BO
bo = page.evaluate("""() => {
    const lc = window.__archPage?.chartConfig?.layoutControl
    function walk(list) {
        for (const g of list || []) {
            for (const c of g.containers || []) {
                if (c && typeof c === 'object' && c.isVirtual === true && c.nodes && c.nodes.length) return String(c.nodes[0])
            }
            const r = walk(g.children); if (r) return r
        }
        return null
    }
    return walk(lc && lc.groups)
}""")
print('  BO:', bo)
print('  addBO:', mutate("""(copy, id, title) => {
    const boCode = '""" + str(bo) + """'
    const grp = copy.groups.find(g => g.id === id)
    if (!grp) return 'no group'
    // 从原位置移除该 BO
    function removeFrom(list) {
        for (const g of list || []) {
            if (Array.isArray(g.containers)) {
                g.containers = g.containers.filter(c => !(c && typeof c === 'object' && c.isVirtual && c.nodes && String(c.nodes[0]) === boCode))
            }
            removeFrom(g.children)
            removeFrom(g.containers)
        }
    }
    removeFrom(copy.groups)
    grp.containers.push({ id: 'bo_' + boCode + '_e2e', name: boCode, elementCode: boCode,
        isVirtual: true, nodes: [boCode], enabled: true, visible: true })
    return 'added-' + boCode
}"""))
time.sleep(8)
print('  状态:', json.dumps(st(), ensure_ascii=False), '→ 期望 subgraph=true 且非 collapse')

# 场景3: 移除 BO → 回到节点
print('\n[场景3] 移出 BO')
print('  rmBO:', mutate("""(copy, id, title) => {
    const grp = copy.groups.find(g => g.id === id)
    if (!grp) return 'no group'
    grp.containers = []
    return 'removed'
}"""))
time.sleep(8)
print('  状态:', json.dumps(st(), ensure_ascii=False), '→ 期望 collapse=true')

print('\nerrors:', errs[:5])
cli.close()
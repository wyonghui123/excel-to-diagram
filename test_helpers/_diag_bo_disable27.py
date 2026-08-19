# -*- coding: utf-8 -*-
"""诊断 v27: 检查 SVG DOM 中节点是否嵌套在 cluster 内 + 当前分组隐藏行为"""
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

print('=== DOM 嵌套关系 ===')
print(json.dumps(page.evaluate("""() => {
    const svg = document.querySelector('.mermaid svg')
    const n = Array.from(svg.querySelectorAll('g.node')).find(e => (e.textContent||'').includes('DP10'))
    if (!n) return { dp10: 'NOT-FOUND' }
    let p = n.parentElement
    const ancestors = []
    while (p && p !== svg) {
        if (p.classList && p.classList.contains('cluster')) {
            ancestors.push({ id: p.id, code: p.getAttribute('data-container-code') })
        }
        p = p.parentElement
    }
    return { dp10AncestorClusters: ancestors }
}"""), ensure_ascii=False, default=str))

def mutate_panel(fn_src):
    return page.evaluate("""(fnSrc) => {
        const lc = window.__archPage?.chartConfig?.layoutControl
        if (!lc || !lc.groups) return 'no layoutControl'
        const copy = JSON.parse(JSON.stringify(lc))
        const fn = new Function('copy', 'return (' + fnSrc + ')(copy)')
        const res = fn(copy)
        Object.assign(window.__archPage.chartConfig.layoutControl, copy)
        return res
    }""", fn_src)

print('\n=== 隐藏 DP (visible=false, 级联容器) ===')
print('mutate:', mutate_panel("""(copy) => {
    function walk(list) {
        for (const g of list || []) {
            if ((g.elementCode || g.id) === 'DP') {
                g.visible = false
                for (const c of g.containers || []) { if (c && typeof c === 'object') c.visible = false }
                return 'hidden DP'
            }
            const r = walk(g.children); if (r) return r
        }
        return null
    }
    return walk(copy.groups)
}"""))
time.sleep(6)
print(json.dumps(page.evaluate("""() => {
    const svg = document.querySelector('.mermaid svg')
    const dpCluster = svg.querySelector('g.cluster[data-container-code="DP"], g.cluster[id*="G_SM_DP"]')
    const n = Array.from(svg.querySelectorAll('g.node')).find(e => (e.textContent||'').includes('DP10'))
    return {
        dpClusterDisplay: dpCluster ? (dpCluster.style.display || 'block') : 'NO-CLUSTER',
        dp10: n ? (n.style.display || 'block') : 'GONE',
        hiddenClusters: Array.from(svg.querySelectorAll('g.cluster')).filter(c => c.style.display === 'none').map(c => c.getAttribute('data-container-code') || c.id).slice(0, 10)
    }
}"""), ensure_ascii=False, default=str))
cli.close()

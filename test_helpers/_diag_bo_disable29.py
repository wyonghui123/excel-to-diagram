# -*- coding: utf-8 -*-
"""验证 v29: 分组隐藏新语义 - 只隐藏容器框, 子节点保留 + BO叶隐藏回归"""
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
time.sleep(4)

def state():
    return page.evaluate("""() => {
        const svg = document.querySelector('.mermaid svg')
        if (!svg) return { svg: false }
        const cluster = (code) => {
            const c = Array.from(svg.querySelectorAll('g.cluster')).find(e => e.getAttribute('data-container-code') === code)
            return c ? (c.style.display || 'block') : 'NO-CLUSTER'
        }
        const node = (code) => {
            const n = Array.from(svg.querySelectorAll('g.node')).find(e => (e.textContent||'').includes(code))
            return n ? (n.style.display || 'block') : 'GONE'
        }
        return {
            dpCluster: cluster('DP'), dp10: node('DP10'), dp01: node('DP01'),
            scpCluster: cluster('SCP'), extCluster: cluster('EXT'), ext10: node('EXT10'),
            totalNodes: svg.querySelectorAll('g.node').length,
            hiddenClusters: Array.from(svg.querySelectorAll('g.cluster')).filter(c => c.style.display === 'none').map(c => c.getAttribute('data-container-code'))
        }
    }""")

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

print('初始:', json.dumps(state(), ensure_ascii=False, default=str))

print('\n[1] 隐藏服务模块 DP (仅 visible=false, 不级联)')
print('  mutate:', mutate_panel("""(copy) => {
    function walk(list) {
        for (const g of list || []) {
            if ((g.elementCode || g.id) === 'DP') { g.visible = false; return 'hidden DP' }
            const r = walk(g.children); if (r) return r
        }
        return null
    }
    return walk(copy.groups)
}"""))
time.sleep(6)
print('  隐藏后:', json.dumps(state(), ensure_ascii=False, default=str))

print('  [恢复显示]', mutate_panel("""(copy) => {
    function walk(list) {
        for (const g of list || []) {
            if ((g.elementCode || g.id) === 'DP') { g.visible = true; return 'show DP' }
            const r = walk(g.children); if (r) return r
        }
        return null
    }
    return walk(copy.groups)
}"""))
time.sleep(6)
print('  恢复后:', json.dumps(state(), ensure_ascii=False, default=str))

print('\n[2] 隐藏子领域 SCP (仅 visible=false, 不级联)')
print('  mutate:', mutate_panel("""(copy) => {
    function walk(list) {
        for (const g of list || []) {
            if ((g.elementCode || g.id) === 'SCP') { g.visible = false; return 'hidden SCP' }
            const r = walk(g.children); if (r) return r
        }
        return null
    }
    return walk(copy.groups)
}"""))
time.sleep(6)
print('  隐藏后:', json.dumps(state(), ensure_ascii=False, default=str))

print('  [恢复显示]', mutate_panel("""(copy) => {
    function walk(list) {
        for (const g of list || []) {
            if ((g.elementCode || g.id) === 'SCP') { g.visible = true; return 'show SCP' }
            const r = walk(g.children); if (r) return r
        }
        return null
    }
    return walk(copy.groups)
}"""))
time.sleep(6)
print('  恢复后:', json.dumps(state(), ensure_ascii=False, default=str))

print('\n[3] 回归: BO 叶隐藏 (DP10 visible=false)')
print('  mutate:', mutate_panel("""(copy) => {
    let n = 0
    function walk(list) {
        for (const g of list || []) {
            for (const c of g.containers || []) {
                if (c && typeof c === 'object' && c.isVirtual === true && c.nodes && String(c.nodes[0]) === 'DP10') { c.visible = false; n++ }
            }
            walk(g.children)
        }
    }
    walk(copy.groups); return 'touched=' + n
}"""))
time.sleep(6)
print('  隐藏后:', json.dumps(state(), ensure_ascii=False, default=str))

print('\nerrors:', errs[:5])
cli.close()

# -*- coding: utf-8 -*-
"""验证 v15: 修正 mutate 调用方式, 验证三场景 (BO禁用/BO隐藏/分组隐藏)"""
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
print('setExpandLevel:', page.evaluate("() => window.__archPage?.debug?.setExpandLevel('businessObject')"))
time.sleep(4)

def st():
    return page.evaluate("""() => {
        const svg = document.querySelector('.mermaid svg')
        if (!svg) return { svg: false, nodes: -1 }
        const count = svg.querySelectorAll('g.node').length
        const find = (code) => {
            const n = Array.from(svg.querySelectorAll('g.node')).find(e => (e.getAttribute('data-code') === code) || (e.textContent||'').includes(code))
            return n ? (n.style.display || 'block') : 'GONE'
        }
        return { svg: true, nodes: count, dp10: find('DP10'), dp01: find('DP01') }
    }""")

def panel_dp10():
    return page.evaluate("""() => {
        const lc = window.__archPage?.chartConfig?.layoutControl
        function walk(list) {
            for (const g of list || []) {
                for (const c of g.containers || []) {
                    if (c && typeof c === 'object' && c.isVirtual === true && c.nodes && String(c.nodes[0]) === 'DP10') return { enabled: c.enabled, visible: c.visible }
                }
                const r = walk(g.children); if (r) return r
                const r2 = walk(g.containers); if (r2) return r2
            }
            return null
        }
        return walk(lc && lc.groups)
    }""")

def prop_disabled():
    return page.evaluate("""() => {
        let inst = null, p = (document.querySelector('.mermaid-container, .mermaid-wrapper') || {}).__vueParentComponent
        let guard = 0
        while (p && guard++ < 20) { if (p.props && p.props.layoutControlConfig !== undefined) { inst = p; break } p = p.parent }
        return inst ? ((inst.props.layoutControlConfig && inst.props.layoutControlConfig.disabledBoCodes) || []) : 'no-comp'
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

print('初始:', json.dumps(st(), ensure_ascii=False), '| panel.DP10:', json.dumps(panel_dp10(), ensure_ascii=False))

# ========== 场景1: BO 禁用 ==========
print('\n[场景1] 禁用 DP10')
print('  mutate:', mutate_panel("""(copy) => {
    let n = 0
    function walk(list) {
        for (const g of list || []) {
            for (const c of g.containers || []) {
                if (c && typeof c === 'object' && c.isVirtual === true && c.nodes && String(c.nodes[0]) === 'DP10') { c.enabled = false; n++ }
            }
            walk(g.children)
        }
    }
    walk(copy.groups); return 'touched=' + n
}"""))
time.sleep(6)
print('  禁用后:', json.dumps(st(), ensure_ascii=False), '| panel.DP10:', json.dumps(panel_dp10(), ensure_ascii=False), '| prop dBo:', json.dumps(prop_disabled(), ensure_ascii=False))

print('  恢复:', mutate_panel("""(copy) => {
    function walk(list) {
        for (const g of list || []) {
            for (const c of g.containers || []) {
                if (c && typeof c === 'object' && c.isVirtual === true && c.nodes && String(c.nodes[0]) === 'DP10') c.enabled = true
            }
            walk(g.children)
        }
    }
    walk(copy.groups); return 'ok'
}"""))
time.sleep(6)
print('  恢复后:', json.dumps(st(), ensure_ascii=False))

# ========== 场景2: BO 隐藏 ==========
print('\n[场景2] 隐藏 DP10 (visible=false)')
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
print('  隐藏后:', json.dumps(st(), ensure_ascii=False), '| panel.DP10:', json.dumps(panel_dp10(), ensure_ascii=False))

print('  恢复显示:', mutate_panel("""(copy) => {
    function walk(list) {
        for (const g of list || []) {
            for (const c of g.containers || []) {
                if (c && typeof c === 'object' && c.isVirtual === true && c.nodes && String(c.nodes[0]) === 'DP10') { c.visible = true }
            }
            walk(g.children)
        }
    }
    walk(copy.groups); return 'ok'
}"""))
time.sleep(6)
print('  恢复后:', json.dumps(st(), ensure_ascii=False))

# ========== 场景3: 分组隐藏 ==========
print('\n[场景3] 隐藏 DP 分组')
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
print('  隐藏DP后:', json.dumps(st(), ensure_ascii=False))

print('\nerrors:', errs[:5])
cli.close()

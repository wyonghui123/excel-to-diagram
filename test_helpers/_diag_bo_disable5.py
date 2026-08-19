# -*- coding: utf-8 -*-
"""诊断 v5: 复刻面板真实更新路径 (Object.assign 替换 groups) 是否触发重渲染"""
import sys, time, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3004'
errs = []
cli = PlaywrightCLI()
page = cli._ensure_browser()
page.on('pageerror', lambda e: errs.append(str(e)[:300]))

page.goto(f"{BASE}/api/v1/auth/dev-login?username=admin", wait_until='domcontentloaded', timeout=15000)
page.goto(f"{BASE}/system/archdata?productCode=TTTTT000&versionCode=V11&view=chart&scopeCode=SCP",
          wait_until='domcontentloaded', timeout=20000)
for _ in range(12):
    time.sleep(2)
    if page.evaluate("() => !!document.querySelector('.mermaid svg')"):
        break
for i in range(20):
    r = page.evaluate("""() => {
        const svg = document.querySelector('.mermaid svg')
        const agg = Array.from(svg.querySelectorAll('g.node')).find(n => /[\\[【]/.test(n.textContent||''))
        if (!agg) return false
        agg.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, detail: 2 }))
        return true
    }""")
    if not r:
        break
    time.sleep(3)

def has_bo(code):
    return page.evaluate("""(code) => {
        const svg = document.querySelector('.mermaid svg')
        return Array.from(svg.querySelectorAll('g.node')).some(n => (n.textContent||'').endsWith(code))
    }""", code)

print('DP10 before:', has_bo('DP10'))

# 复刻面板路径: 深拷贝 layoutControl → 改 DP10 enabled=false → Object.assign 回 chartConfig.layoutControl
mutated = page.evaluate("""() => {
    const lc = window.__archPage?.chartConfig?.layoutControl
    if (!lc || !lc.groups) return false
    const copy = JSON.parse(JSON.stringify(lc))
    function walk(list) {
        for (const g of list || []) {
            const leaf = (g.containers||[]).find(c => c && c.isVirtual === true && c.nodes && String(c.nodes[0]) === 'DP10')
            if (leaf) { leaf.enabled = false; return true }
            if (walk(g.children)) return true
            if (walk(g.containers)) return true
        }
        return false
    }
    walk(copy.groups)
    // 复刻 RelationScopeTree: Object.assign(injectedChartConfig.layoutControl, v)
    Object.assign(window.__archPage.chartConfig.layoutControl, copy)
    return true
}""")
print('Object.assign replaced:', mutated)
time.sleep(5)
print('DP10 after Object.assign (no reload):', has_bo('DP10'))

info = page.evaluate("""() => {
    const svg = document.querySelector('.mermaid svg')
    return { nodes: svg ? svg.querySelectorAll('g.node').length : -1 }
}""")
print('nodes:', info['nodes'])
print('errors:', errs[:3])
cli.close()

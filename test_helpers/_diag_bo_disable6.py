# -*- coding: utf-8 -*-
"""诊断 v6: 判断 layoutControlConfig computed 是否在 BO 叶子改动后重新求值"""
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

# 读 computed 内部写入的可观测 (debugLayout / expandState)
def snap():
    return page.evaluate("""() => ({
        debugLayout: !!window.__archPage?.debugLayout,
        debugLayoutPanelGroups: window.__archPage?.debugLayout?.panelGroups?.length,
        expandState: window.__archPage?.expandState
    })""")

s0 = snap()
print('== before ==', json.dumps(s0, ensure_ascii=False, default=str))

# Object.assign 替换 (复刻面板)
page.evaluate("""() => {
    const lc = window.__archPage?.chartConfig?.layoutControl
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
    Object.assign(window.__archPage.chartConfig.layoutControl, copy)
    return true
}""")
time.sleep(3)
s1 = snap()
print('== after ==', json.dumps(s1, ensure_ascii=False, default=str))
print('computed re-ran (debugLayout/expandState changed):', json.dumps(s1, ensure_ascii=False) != json.dumps(s0, ensure_ascii=False))
print('errors:', errs[:3])
cli.close()

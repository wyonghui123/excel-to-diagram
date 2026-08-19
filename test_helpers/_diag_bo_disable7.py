# -*- coding: utf-8 -*-
"""诊断 v7: 用 debugLayout.panelGroups 精确判断 computed 是否重算 + BO 叶子 enabled 是否被收集"""
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

def dp10_in_panel_debug():
    return page.evaluate("""() => {
        const pg = window.__archPage?.debugLayout?.panelGroups
        function find(list) {
            for (const g of list || []) {
                const leaf = (g.containers||[]).find(c => c && c.isVirtual === true && c.nodes && String(c.nodes[0]) === 'DP10')
                if (leaf) return { enabled: leaf.enabled, visible: leaf.visible }
                const r = find(g.children); if (r) return r
                const r2 = find(g.containers); if (r2) return r2
            }
            return null
        }
        return find(pg)
    }""")

# 记一个随机哨兵到 chartConfig.layoutControl 面板树, 判断 computed 是否读取到新引用
sentinel = page.evaluate("""() => {
    const lc = window.__archPage?.chartConfig?.layoutControl
    const copy = JSON.parse(JSON.stringify(lc))
    function walk(list) {
        for (const g of list || []) {
            const leaf = (g.containers||[]).find(c => c && c.isVirtual === true && c.nodes && String(c.nodes[0]) === 'DP10')
            if (leaf) { leaf.enabled = false; leaf.__sentinel = 'SENTINEL'; return true }
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
after = dp10_in_panel_debug()
print('after Object.assign, debugLayout.panelGroups DP10 leaf:', json.dumps(after, ensure_ascii=False, default=str))
# 若 after 为 null → computed 未重算 (panelGroups 还是旧引用); 若 enabled=false/__sentinel → 重算了
print('errors:', errs[:3])
cli.close()

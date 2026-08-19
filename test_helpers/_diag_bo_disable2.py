# -*- coding: utf-8 -*-
"""诊断 v2: 展开到 BO 层后, 禁用/隐藏 BO 叶子是否影响渲染"""
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

def counts():
    return page.evaluate("""() => {
        const svg = document.querySelector('.mermaid svg')
        const names = svg ? Array.from(svg.querySelectorAll('g.node')).map(n => (n.textContent||'').trim().slice(0,20)) : []
        return { nodes: svg ? svg.querySelectorAll('g.node').length : -1,
                 edges: svg ? svg.querySelectorAll('path.flowchart-link').length : -1,
                 names: names.slice(0,12) }
    }""")

# 1. 双击第一个 SM 聚合节点展开 (显示 BO)
clicked = page.evaluate("""() => {
    const g = document.querySelector('.mermaid svg g.node')
    if (!g) return false
    g.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, detail: 2 }))
    return true
}""")
print('dblclick SM:', clicked)
time.sleep(5)
print('== 展开后 counts ==', json.dumps(counts(), ensure_ascii=False, default=str))

# 2. 找面板树里第一个 enabled!=false 的 BO 叶子, 禁用它
target = page.evaluate("""() => {
    const lc = window.__archPage?.chartConfig?.layoutControl
    function find(list) {
        for (const g of list || []) {
            const leaf = (g.containers||[]).find(c => c && c.isVirtual === true && c.enabled !== false)
            if (leaf) return { leafId: leaf.id, nodes: leaf.nodes, gtitle: g.title }
            const r = find(g.children); if (r) return r
            const r2 = find(g.containers); if (r2) return r2
        }
        return null
    }
    return find(lc?.groups)
}""")
print('== 目标 BO ==', json.dumps(target, ensure_ascii=False, default=str))

if target:
    leaf_id = target['leafId']
    mutated = page.evaluate("""(id) => {
        const lc = window.__archPage?.chartConfig?.layoutControl
        let hit = false
        function walk(list) {
            for (const g of list || []) {
                const leaf = (g.containers||[]).find(c => c && c.id === id)
                if (leaf) { leaf.enabled = false; hit = true; return true }
                if (walk(g.children)) return true
                if (walk(g.containers)) return true
            }
            return false
        }
        walk(lc?.groups)
        return hit
    }""", leaf_id)
    print('mutated enabled=false:', mutated)
    time.sleep(5)
    print('== 禁用后 counts ==', json.dumps(counts(), ensure_ascii=False, default=str))

print('errors:', errs[:3])
cli.close()

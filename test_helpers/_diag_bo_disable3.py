# -*- coding: utf-8 -*-
"""诊断 v3: 展开全部 SM 到 BO 层后, 对可见 BO 执行 禁用/隐藏, 观察渲染变化"""
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
        const names = svg ? Array.from(svg.querySelectorAll('g.node')).map(n => (n.textContent||'').trim()) : []
        return { nodes: names.length, edges: svg ? svg.querySelectorAll('path.flowchart-link').length : -1, names }
    }""")

# 1. 双击所有聚合 SM 节点, 直到无聚合 (全部展开到 BO)
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
print('== 全展开后 counts ==')
c0 = counts()
print(json.dumps(c0, ensure_ascii=False, default=str)[:1500])

# 2. 收集所有 BO 代码 (非聚合节点)
bo_codes = [n for n in c0['names'] if not (n.startswith('[') or n.startswith('【'))]
print('visible BO count:', len(bo_codes), 'sample:', bo_codes[:6])

# 2b. 取面板树所有叶子 code 列表
panel_codes = page.evaluate("""() => {
    const lc = window.__archPage?.chartConfig?.layoutControl
    const codes = []
    function find(list) {
        for (const g of list || []) {
            for (const c of (g.containers||[])) {
                if (c && c.isVirtual === true && c.nodes && c.nodes.length) codes.push(String(c.nodes[0]))
            }
            find(g.children); find(g.containers)
        }
    }
    find(lc?.groups)
    return codes
}""")
print('panel BO code count:', len(panel_codes))

# 2c. 找第一个 SVG 文本以 panel code 结尾的 visible BO
def find_code():
    for text in bo_codes:
        for pc in panel_codes:
            if text.endswith(pc):
                return pc
    return None
target_code = find_code()
print('== 目标 visible BO code ==', target_code)

# 3. 找面板树中对应 target_code 的叶子, 禁用/隐藏
if not target_code:
    print('!! 未找到可见 BO 对应的面板叶子')
else:
    target = page.evaluate("""(code) => {
        const lc = window.__archPage?.chartConfig?.layoutControl
        function find(list) {
            for (const g of list || []) {
                for (const c of (g.containers||[])) {
                    if (c && c.isVirtual === true && c.nodes && String(c.nodes[0]) === code) {
                        return { leafId: c.id, code: code, gtitle: g.title }
                    }
                }
                const r = find(g.children); if (r) return r
                const r2 = find(g.containers); if (r2) return r2
            }
            return null
        }
        return find(lc?.groups)
    }""", target_code)
    print('== 目标叶子 ==', json.dumps(target, ensure_ascii=False, default=str))

if target:
    leaf_id = target['leafId']; code = target['code']
    # 3a. 禁用
    page.evaluate("""(id) => {
        const lc = window.__archPage?.chartConfig?.layoutControl
        function walk(list) {
            for (const g of list || []) {
                const leaf = (g.containers||[]).find(c => c && c.id === id)
                if (leaf) { leaf.enabled = false; return true }
                if (walk(g.children)) return true
                if (walk(g.containers)) return true
            }
            return false
        }
        walk(lc?.groups)
        return true
    }""", leaf_id)
    time.sleep(5)
    c1 = counts()
    print('== 禁用 %s 后 ==  nodes:%s  (删除%s)' % (code, c1['nodes'], len(c0['names']) - len(c1['names'])))
    print(json.dumps(c1['names'], ensure_ascii=False, default=str)[:600])
    # 3b. 恢复 enabled, 设 visible=false (隐藏)
    page.evaluate("""(id) => {
        const lc = window.__archPage?.chartConfig?.layoutControl
        function walk(list) {
            for (const g of list || []) {
                const leaf = (g.containers||[]).find(c => c && c.id === id)
                if (leaf) { leaf.enabled = true; leaf.visible = false; return true }
                if (walk(g.children)) return true
                if (walk(g.containers)) return true
            }
            return false
        }
        walk(lc?.groups)
        return true
    }""", leaf_id)
    time.sleep(5)
    c2 = counts()
    print('== 隐藏 %s 后 ==  nodes:%s  (删除%s)' % (code, c2['nodes'], len(c1['names']) - len(c2['names'])))
    print(json.dumps(c2['names'], ensure_ascii=False, default=str)[:600])

print('errors:', errs[:3])
cli.close()

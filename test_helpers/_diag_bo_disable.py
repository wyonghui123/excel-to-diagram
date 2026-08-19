# -*- coding: utf-8 -*-
"""诊断: 面板树 BO 叶子 enabled/visible 改动是否影响图表渲染"""
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
# 等图表渲染
for _ in range(12):
    time.sleep(2)
    if page.evaluate("() => !!document.querySelector('.mermaid svg')"):
        break

# 1. 检查面板树结构: 找 BO 叶子 (isVirtual=true 容器)
def dump_panel():
    return page.evaluate("""() => {
        const lc = window.__archPage?.chartConfig?.layoutControl
        const groups = lc?.groups || []
        const out = { groupCount: groups.length, groups: [] }
        function walk(list, depth) {
            for (const g of list || []) {
                const leafs = (g.containers||[]).filter(c => c && c.isVirtual === true)
                if (leafs.length) out.groups.push({
                    gid: g.id, title: g.title, groupType: g.groupType,
                    leafCount: leafs.length,
                    sampleLeaf: leafs.slice(0,3).map(c => ({ id: c.id, nodes: c.nodes, enabled: c.enabled, visible: c.visible, isVirtual: c.isVirtual }))
                })
                walk(g.children, depth+1)
                walk(g.containers, depth+1)
            }
        }
        walk(groups, 0)
        return out
    }""")

print('== 面板树 BO 叶子 ==')
try:
    print(json.dumps(dump_panel(), ensure_ascii=False, default=str)[:2500])
except Exception as e:
    print('dump_panel err', e)

# 2. 记录当前可见 BO 节点数 + disabledBoCodes
def counts():
    return page.evaluate("""() => {
        const svg = document.querySelector('.mermaid svg')
        const est = window.__archPage?.expandState || {}
        const lcc = window.__archPage?.chartConfig?.layoutControl
        return {
            svgNodes: svg ? svg.querySelectorAll('g.node').length : -1,
            svgEdges: svg ? svg.querySelectorAll('path.flowchart-link').length : -1,
            expandState: est
        }
    }""")

print('== 改前 counts ==', json.dumps(counts(), ensure_ascii=False, default=str))

# 3. 直接改面板树: 禁用第一个 BO 叶子 (enabled=false), 触发重渲染
r = page.evaluate("""() => {
    const lc = window.__archPage?.chartConfig?.layoutControl
    let target = null
    function find(list) {
        for (const g of list || []) {
            const leaf = (g.containers||[]).find(c => c && c.isVirtual === true && c.enabled !== false)
            if (leaf) return { g, leaf }
            const r = find(g.children)
            if (r) return r
            const r2 = find(g.containers)
            if (r2) return r2
        }
        return null
    }
    const t = find(lc?.groups)
    if (!t) return { ok: false }
    target = t
    return { ok: true, gid: t.g.id, leafId: t.leaf.id, nodes: t.leaf.nodes, enabledBefore: t.leaf.enabled, visibleBefore: t.leaf.visible }
}""")
print('== 目标 BO 叶子 ==', json.dumps(r, ensure_ascii=False, default=str))

if r.get('ok'):
    leaf_id = r['leafId']
    # 禁用
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
        // 触发重渲染: 强制 generateDiagram 重新走 layoutControlConfig 链路
        window.__archPage?.chartConfig?.layoutControl = JSON.parse(JSON.stringify(lc))
        return true
    }""", leaf_id)
    time.sleep(4)
    print('== 禁用后 counts ==', json.dumps(counts(), ensure_ascii=False, default=str))
    # 检查 disabledBoCodes 是否被收集 (通过布局控制配置的透传, 这里看渲染结果即可)

print('errors:', errs[:3])
cli.close()

# -*- coding: utf-8 -*-
"""诊断 v38: 新建自定义分组 → 分配 BO → 是否渲染成容器"""
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

def clusters():
    return page.evaluate("""() => {
        const svg = document.querySelector('.mermaid svg')
        if (!svg) return []
        return Array.from(svg.querySelectorAll('g.cluster')).map(e => e.getAttribute('data-container-code') || e.id).filter(Boolean)
    }""")

# 1) 新建分组 (模拟 handleAddGroup): 顶层 push 自定义分组
print('新建分组:', page.evaluate("""() => {
    const lc = window.__archPage?.chartConfig?.layoutControl
    const copy = JSON.parse(JSON.stringify(lc))
    copy.groups.push({
        id: 'grp_custom_1',
        title: '自定义分组A',
        groupType: 'custom',
        direction: 'TB',
        visible: true,
        enabled: true,
        collapsed: false,
        style: { fill: '#ffffff', stroke: '#666666', strokeWidth: 2, strokeDasharray: '' },
        containers: [],
        children: [],
        parentId: undefined
    })
    Object.assign(window.__archPage.chartConfig.layoutControl, copy)
    return 'pushed'
}"""))
time.sleep(4)
print('新建后 clusters:', json.dumps(clusters(), ensure_ascii=False))

# 2) 把 DP10 的容器移入新分组 (模拟拖拽)
print('分配 BO:', page.evaluate("""() => {
    const lc = window.__archPage?.chartConfig?.layoutControl
    const copy = JSON.parse(JSON.stringify(lc))
    let dp10 = null
    function findDp(list) {
        for (const g of list || []) {
            for (const c of g.containers || []) {
                if (c && c.isVirtual === true && c.nodes && String(c.nodes[0]) === 'DP10') { dp10 = c; return true }
            }
            if (findDp(g.children)) return true
        }
        return false
    }
    findDp(copy.groups)
    if (!dp10) return 'DP10 container not found'
    // 从原分组移除
    function removeFrom(list) {
        for (const g of list || []) {
            const idx = (g.containers || []).findIndex(c => c && c.isVirtual === true && c.nodes && String(c.nodes[0]) === 'DP10')
            if (idx !== -1) { g.containers.splice(idx, 1); return true }
            if (removeFrom(g.children)) return true
        }
        return false
    }
    removeFrom(copy.groups)
    // 加入新分组
    const grp = copy.groups.find(g => g.id === 'grp_custom_1')
    grp.containers.push(dp10)
    Object.assign(window.__archPage.chartConfig.layoutControl, copy)
    return 'DP10 moved into custom group'
}"""))
time.sleep(6)
print('分配后 clusters:', json.dumps(clusters(), ensure_ascii=False))
print('DP10 节点存在:', page.evaluate("""() => {
    const svg = document.querySelector('.mermaid svg')
    const n = Array.from(svg.querySelectorAll('g.node')).find(e => (e.textContent||'').includes('DP10'))
    return n ? (n.style.display || 'block') : 'GONE'
}"""))
cli.close()

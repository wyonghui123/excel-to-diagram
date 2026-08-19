# -*- coding: utf-8 -*-
"""验证 2026-08-19:
1. 自定义分组配色 → 清空(重置默认 style) → 渲染色从红回到默认
2. ELK 系统分组(无关系/有关系)默认无颜色
"""
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
time.sleep(5)

ID = 'grp_clear_e2e'

def set_group(style, withBo):
    return page.evaluate("""(args) => {
        const lc = window.__archPage?.chartConfig?.layoutControl
        const copy = JSON.parse(JSON.stringify(lc))
        const { id, style, withBo } = args
        if (withBo && withBo.length) {
            function rm(l){ for(const g of l||[]){ if(Array.isArray(g.containers)) g.containers=g.containers.filter(c=>!(c&&typeof c==='object'&&c.isVirtual&&c.nodes&&withBo.includes(String(c.nodes[0])))); rm(g.children); rm(g.containers) } }
            rm(copy.groups)
        }
        copy.groups = copy.groups.filter(g => g.id !== id)
        copy.groups.push({id, title:'清空测试分组', groupType:'custom', direction:'TB',
            visible:true, enabled:true, collapsed:false, style,
            containers: withBo ? withBo.map(code=>({id:'bo_'+code+'_e2e',name:code,elementCode:code,isVirtual:true,nodes:[code],enabled:true,visible:true})) : [],
            children:[], parentId:null})
        Object.assign(window.__archPage.chartConfig.layoutControl, copy)
        return 'ok'
    }""", {'id': ID, 'style': style, 'withBo': withBo})

def cluster_fill(gid):
    return page.evaluate("""(gid) => {
        const svg = document.querySelector('.mermaid svg')
        if (!svg) return null
        const c = Array.from(svg.querySelectorAll('g.cluster')).find(x => x.id.includes(gid))
        if (!c) return 'NO_CLUSTER'
        const r = c.querySelector('rect')
        return r ? (r.getAttribute('fill') || getComputedStyle(r).fill || r.style.fill) : 'NO_RECT'
    }""", gid)

def node_fill(cid):
    return page.evaluate("""(cid) => {
        const svg = document.querySelector('.mermaid svg')
        if (!svg) return null
        const el = Array.from(svg.querySelectorAll('g.node')).find(n => n.id.includes(cid))
        if (!el) return 'NO_NODE'
        const r = el.querySelector('rect')
        return r ? (r.getAttribute('fill') || getComputedStyle(r).fill || r.style.fill) : 'NO_RECT'
    }""", cid)

def cluster_ids():
    return page.evaluate("""() => {
        const svg = document.querySelector('.mermaid svg')
        if (!svg) return []
        return Array.from(svg.querySelectorAll('g.cluster')).map(c => c.id)
    }""")

# ===== 场景A: ELK 分组(无关系/有关系)默认无颜色 =====
print('\n[A] ELK 系统分组默认颜色检查')
# 展开到服务模块让 ELK 分组可见(无关系/有关系), 或检查已有 cluster
ids = cluster_ids()
print('  clusters:', ids)
# 找含 inner/boundary 的 cluster (无关系/有关系) 的 fill
elk_fill = page.evaluate("""() => {
    const svg = document.querySelector('.mermaid svg')
    if (!svg) return 'NO_SVG'
    const out = []
    for (const c of Array.from(svg.querySelectorAll('g.cluster'))) {
        if (/inner|boundary|无关系|有关系/.test(c.id + (c.querySelector('.cluster-label')||{}).textContent || '')) {
            const color = (c.querySelector('rect')?.getAttribute('fill') || '')
            out.push({ id: c.id, fill: color || 'empty/no-rect' })
        }
    }
    return out
}""")
print('  ELK 分组 fill:', json.dumps(elk_fill, ensure_ascii=False))

# ===== 场景B: 自定义分组 配色红 → 清空回默认 =====
bo = page.evaluate("""() => { const lc=window.__archPage?.chartConfig?.layoutControl; function walk(l){ for(const g of l||[]){ for(const c of g.containers||[]){ if(c&&typeof c==='object'&&c.isVirtual&&c.nodes&&c.nodes.length) return String(c.nodes[0])} const r=walk(g.children); if(r) return r } return null } return walk(lc&&lc.groups) }""")
print('\n[B] 自定义分组 配色→容器 fill 红')
print(' set红:', set_group({'fill':'#ff0000','stroke':'#0000ff','strokeWidth':2,'strokeDasharray':''}, [bo]))
time.sleep(8)
print('  配色红 cluster fill:', cluster_fill('grp_clear_e2e'))

print('\n 清空(重置默认 style #ffffff) → fill 白')
print(' set默认:', set_group({'fill':'#ffffff','stroke':'#666666','strokeWidth':2,'strokeDasharray':''}, [bo]))
time.sleep(8)
print('  清空后 cluster fill:', cluster_fill('grp_clear_e2e'))

# 清理
page.evaluate("""() => { const lc=window.__archPage?.chartConfig?.layoutControl; const copy=JSON.parse(JSON.stringify(lc)); copy.groups=copy.groups.filter(g=>g.id!='grp_clear_e2e'); Object.assign(window.__archPage.chartConfig.layoutControl, copy); return 'cleaned' }""")
time.sleep(5)
print('\nerrors:', errs[:5])
cli.close()
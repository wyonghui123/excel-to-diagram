# -*- coding: utf-8 -*-
"""验证 2026-08-19:
1. 自定义分组配 style 色 → 空(节点)用色 + 标题无省略号; 有 BO(容器)用色
2. 面板色点: custom 分组显示 style.fill
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

ID = 'grp_color_e2e'
TITLE = '彩色分组E2E'

def reset_group(style, withBo=None):
    """重建自定义分组; withBo=[code] 时拖入 BO"""
    return page.evaluate("""(args) => {
        const lc = window.__archPage?.chartConfig?.layoutControl
        if (!lc || !lc.groups) return 'no layoutControl'
        const copy = JSON.parse(JSON.stringify(lc))
        const { id, title, style, withBo } = args
        // 移除旧 BO (若 from原位置)
        if (withBo && withBo.length) {
            function removeFrom(list){
                for (const g of list||[]){
                    if(Array.isArray(g.containers)) g.containers = g.containers.filter(c=>!(c&&typeof c==='object'&&c.isVirtual&&c.nodes&&withBo.includes(String(c.nodes[0]))))
                    removeFrom(g.children); removeFrom(g.containers)
                }
            }
            removeFrom(copy.groups)
        }
        copy.groups = copy.groups.filter(g => g.id !== id)
        const containers = withBo ? withBo.map(code => ({id:'bo_'+code+'_e2e', name:code, elementCode:code, isVirtual:true, nodes:[code], enabled:true, visible:true})) : []
        copy.groups.push({id, title, groupType:'custom', direction:'TB',
            visible:true, enabled:true, collapsed:false, style, containers, children:[], parentId:null})
        Object.assign(window.__archPage.chartConfig.layoutControl, copy)
        return 'ok-with-' + (withBo ? withBo.join(',') : 'empty')
    }""", {'id': ID, 'title': TITLE, 'style': style, 'withBo': withBo})

def inspect():
    return page.evaluate("""() => {
        const code = window.__archPage?.mermaid?.lastRenderedCode || ''
        const svg = document.querySelector('.mermaid svg')
        function rectFill(idPart){
            if(!svg) return null
            const els = Array.from(svg.querySelectorAll('[id*="'+idPart+'"]'))
            for (const el of els){
                const r = el.querySelector('rect')
                if (r) return r.getAttribute('fill') || getComputedStyle(r).fill
            }
            return 'NOT_FOUND'
        }
        return {
            // 「…」: 空自定义分组节点标题不应含省略号 (检查是否紧邻出现省略号)
            collapseTitleHasEllipsis: code.includes('COLLAPSE_grp_color_e2e["彩色分组E2E…"]'),
            collapseTitleNoEllipsis: code.includes('COLLAPSE_grp_color_e2e["彩色分组E2E"]'),
            hasSubgraph: code.includes('subgraph G_grp_color_e2e["彩色分组E2E"]'),
            hasCollapse: code.includes('COLLAPSE_grp_color_e2e'),
            // 颜色: mermaid style 行 + SVG rect computed fill
            mermaidStyleLines: code.split('\\n').filter(l => l.includes('grp_color_e2e') && l.includes('fill')),
            nodeRectFill: rectFill('COLLAPSE_grp_color_e2e'),
            clusterRectFill: svg ? (() => { const c = Array.from(svg.querySelectorAll('g.cluster')).find(x=>x.id.includes('grp_color_e2e')); if(!c) return null; const r = c.querySelector('rect'); return r ? (r.getAttribute('fill') || getComputedStyle(r).fill || r.style.fill) : null })() : null
        }
    }""")

# 场景1: 空分组 + 配红色 → 节点, 标题无省略号, 节点 fill 红
print('\n[场景1] 空自定义分组 + style 红色')
print(' reset:', reset_group({'fill':'#ff0000','stroke':'#0000ff','strokeWidth':2,'strokeDasharray':''}))
time.sleep(8)
r1 = inspect()
print('  ', json.dumps(r1, ensure_ascii=False))
print('   → 期望 hasCollapse=true 且潜标不含"…"且红色')

# 场景2: 拖入 BO → 容器, fill 红
print('\n[场景2] 拖入 BO 变容器 (fill 红)')
bo = page.evaluate("""() => { const lc=window.__archPage?.chartConfig?.layoutControl; function walk(l){ for(const g of l||[]){ for(const c of g.containers||[]){ if(c&&typeof c==='object'&&c.isVirtual&&c.nodes&&c.nodes.length) return String(c.nodes[0])} const r=walk(g.children); if(r) return r } return null } return walk(lc&&lc.groups) }""")
print(' BO:', bo)
print(' reset:', reset_group({'fill':'#ff0000','stroke':'#0000ff','strokeWidth':2,'strokeDasharray':''}, withBo=[bo]))
time.sleep(8)
r2 = inspect()
print('  ', json.dumps(r2, ensure_ascii=False))
print('   → 期望 hasSubgraph=true, cluster rect fill 红')

# 清理
page.evaluate("""() => { const lc=window.__archPage?.chartConfig?.layoutControl; const copy=JSON.parse(JSON.stringify(lc)); copy.groups=copy.groups.filter(g=>g.id!='grp_color_e2e'); Object.assign(window.__archPage.chartConfig.layoutControl, copy); return 'cleaned' }""")
time.sleep(5)
print('\nerrors:', errs[:5])
cli.close()
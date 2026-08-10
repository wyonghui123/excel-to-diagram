# -*- coding: utf-8 -*-
"""Reproduce issue 2: double-click expand 供应链云 -> switch colorGroupBy -> reload + auto-expand."""
import sys, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3004'

def read_observe(page):
    return page.evaluate("""
        () => {
            const a = window.__archPage || {}
            const app = document.querySelector('#app')?.__vue_app__
            const pinia = app?.config?.globalProperties?.$pinia
            const st = pinia?._s?.get('diagramConfig')
            const cfg = st?.$state || {}
            let panelCollapsed = null
            try {
                const chartCfg = a.chartConfig
                const rec = (list) => {
                    const out = {}
                    ;(list||[]).forEach(g=>{
                        if(g && (g.elementCode||g.id)){
                            const code = g.elementCode||g.id
                            const t = g.groupType||g.type||''
                            out[code] = {t, collapsed: g.collapsed, title: g.title||g.name}
                        }
                        if(g?.children) Object.assign(out, rec(g.children))
                        if(g?.containers) Object.assign(out, rec(g.containers))
                    })
                    return out
                }
                panelCollapsed = rec(chartCfg?.layoutControl?.groups)
            } catch(e){ panelCollapsed = 'ERR:'+e.message }
            // capture computed's mergedGroups evolution (debugLayout snapshots)
            let dbg = null
            try {
                const d = a.debugLayout || {}
                const compact = (list) => {
                    const out = {}
                    ;(list||[]).forEach(g=>{
                        if(g && (g.elementCode||g.id)){
                            const code = g.elementCode||g.id
                            out[code] = {collapsed: g.collapsed, t: g.groupType||''}
                        }
                        if(g?.children) Object.assign(out, compact(g.children))
                        if(g?.containers) Object.assign(out, compact(g.containers))
                    })
                    return out
                }
                dbg = {
                    afterStates: compact(d.afterStates),
                    afterScopeExpand: compact(d.afterScopeExpand)
                }
            } catch(e){ dbg = 'ERR:'+e.message }
            return {
                colorState: a.colorState ? {
                    colorGroupBy: a.colorState.colorGroupBy,
                    nodeColorMappingsCount: a.colorState.nodeColorMappingsCount,
                    legendRefreshSkipped: a.colorState.legendRefreshSkipped,
                    unifiedColorMapKeys: a.colorState.unifiedColorMapKeys
                } : null,
                expandState: a.expandState ? {...a.expandState, groupManualSet: st?.groupManualSet} : null,
                store: { groupManualSet: st?.groupManualSet, expandLevel: st?.expandLevel, colorGroupBy: st?.colorGroupBy, expandLevelUserSet: st?.expandLevelUserSet },
                panelCollapsed,
                dbg
            }
        }
    """)

def wait_svg(page, timeout=45):
    import time as _t
    _t.sleep(2)  # let initial navigation settle
    t0 = _t.time()
    while _t.time()-t0 < timeout:
        try:
            n = page.evaluate("() => document.querySelectorAll('svg g.node').length")
            if n:
                return True, n
        except Exception:
            pass
        _t.sleep(1)
    return False, 0

def main():
    with PlaywrightCLI(headless=True) as cli:
        cli.goto(BASE + '/api/v1/auth/dev-login?username=admin', wait_until='domcontentloaded')
        cli.goto(BASE + '/system/archdata?preset=scp', wait_until='domcontentloaded')
        cli._wait_for_store_ready(timeout=25000)
        ok, n = wait_svg(cli._page)
        print('svg ready:', ok, 'nodeCount=', n)
        cli.wait_for_timeout(2000)
        print('=== BASELINE (scope default) ===')
        print(json.dumps(read_observe(cli._page), ensure_ascii=False, indent=1))

        # Set 展开层级=领域 (collapse to domain), matching user issue-1 setup
        cli.evaluate("""
            () => {
                const app = document.querySelector('#app').__vue_app__
                const pinia = app.config.globalProperties.$pinia
                pinia._s.get('diagramConfig').setExpandLevel('domain')
            }
        """)
        cli.wait_for_timeout(4000)
        ok2, n2 = wait_svg(cli._page)
        print('svg after expand=domain:', ok2, n2)
        print('=== AFTER setExpandLevel(domain) ===')
        print(json.dumps(read_observe(cli._page), ensure_ascii=False, indent=1))
        lbl = cli.evaluate("() => Array.from(document.querySelectorAll('svg g.node .nodeLabel')).map(e=>e.textContent)")
        print('node labels:', json.dumps(lbl, ensure_ascii=False))

        # Now real double-click on 供应链云 (the domain COLLAPSE node in SVG)
        dbl = cli.evaluate("""
            () => {
                const nodes = Array.from(document.querySelectorAll('svg g.node'))
                let target = null
                for (const n of nodes) {
                    const lbl = (n.querySelector('.nodeLabel')||{}).textContent || ''
                    if (lbl.includes('供应链云')) { target = n; break }
                }
                if (!target) {
                    return {ok:false, reason:'node 供应链云 not found', labels: nodes.map(n=>(n.querySelector('.nodeLabel')||{}).textContent).slice(0,20)}
                }
                const rect = target.getBoundingClientRect()
                const x = rect.x + rect.width/2, y = rect.y + rect.height/2
                const evt = new MouseEvent('dblclick', {bubbles:true, cancelable:true, clientX:x, clientY:y, view:window})
                target.dispatchEvent(evt)
                return {ok:true, rect:{x:Math.round(x),y:Math.round(y)}}
            }
        """)
        print('DBLCLICK result:', json.dumps(dbl, ensure_ascii=False))
        cli.wait_for_timeout(4000)
        ok3, n3 = wait_svg(cli._page)
        print('svg after dblclick:', ok3, n3)
        print('=== AFTER dblclick 供应链云 ===')
        print(json.dumps(read_observe(cli._page), ensure_ascii=False, indent=1))
        lbl2 = cli.evaluate("() => Array.from(document.querySelectorAll('svg g.node .nodeLabel')).map(e=>e.textContent)")
        print('node labels after dblclick:', json.dumps(lbl2, ensure_ascii=False))

        # Switch colorGroupBy to serviceModule
        cli.evaluate("""
            () => {
                const app = document.querySelector('#app').__vue_app__
                const pinia = app.config.globalProperties.$pinia
                pinia._s.get('diagramConfig').updateColorGroupBy('serviceModule')
            }
        """)
        cli.wait_for_timeout(4500)
        ok4, n4 = wait_svg(cli._page)
        print('svg after color=serviceModule:', ok4, n4)
        print('=== AFTER dblclick + colorGroupBy=serviceModule ===')
        print(json.dumps(read_observe(cli._page), ensure_ascii=False, indent=1))
        lbl3 = cli.evaluate("() => Array.from(document.querySelectorAll('svg g.node .nodeLabel')).map(e=>e.textContent)")
        print('node labels after color switch:', json.dumps(lbl3, ensure_ascii=False))

if __name__ == '__main__':
    main()

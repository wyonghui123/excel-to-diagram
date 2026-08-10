# -*- coding: utf-8 -*-
"""Debug issue2: find what overwrites panel collapsed on colorGroupBy switch."""
import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3004'

def main():
    with PlaywrightCLI(headless=True) as cli:
        cli.goto(BASE + '/api/v1/auth/dev-login?username=admin', wait_until='domcontentloaded')
        cli.goto(BASE + '/system/archdata?preset=scp', wait_until='domcontentloaded')
        cli._wait_for_store_ready(timeout=25000)
        time.sleep(4)

        # expand to domain
        cli.evaluate("""
            () => {
                const app = document.querySelector('#app').__vue_app__
                const pinia = app.config.globalProperties.$pinia
                pinia._s.get('diagramConfig').setExpandLevel('domain')
            }
        """)
        time.sleep(3)
        # dblclick 供应链云
        cli.evaluate("""
            () => {
                const nodes = Array.from(document.querySelectorAll('svg g.node'))
                let target = null
                for (const n of nodes) {
                    const lbl = (n.querySelector('.nodeLabel')||{}).textContent || ''
                    if (lbl.includes('供应链云')) { target = n; break }
                }
                if (!target) return {ok:false}
                const rect = target.getBoundingClientRect()
                const x = rect.x + rect.width/2, y = rect.y + rect.height/2
                target.dispatchEvent(new MouseEvent('dblclick', {bubbles:true, cancelable:true, clientX:x, clientY:y, view:window}))
                return {ok:true}
            }
        """)
        time.sleep(3)
        # snapshot panel collapsed before
        def panel():
            return cli.evaluate("""
                () => {
                    const a = window.__archPage || {}
                    const chartCfg = a.chartConfig
                    const out = {}
                    const rec=(list)=>{;(list||[]).forEach(g=>{if(g&&(g.elementCode||g.id)){const c=g.elementCode||g.id; out[c]={collapsed:g.collapsed,t:g.groupType||g.type||''}; if(g.children)rec(g.children); if(g.containers)rec(g.containers)}})}
                    rec(chartCfg?.layoutControl?.groups)
                    return out
                }
            """)
        before = panel()
        print('BEFORE color switch panel SCM/SCP/MFG/MKT:', {k: before[k] for k in ['SCM','SCP','MFG','MKT'] if k in before})

        # clear console buffer
        cli._console_errors = []
        cli._page.on('console', lambda m: print('[CONSOLE]', m.type, m.text[:200]))

        # switch colorGroupBy
        cli.evaluate("""
            () => {
                const app = document.querySelector('#app').__vue_app__
                const pinia = app.config.globalProperties.$pinia
                pinia._s.get('diagramConfig').updateColorGroupBy('serviceModule')
            }
        """)
        time.sleep(4)
        after = panel()
        print('AFTER color switch panel SCM/SCP/MFG/MKT:', {k: after[k] for k in ['SCM','SCP','MFG','MKT'] if k in after})
        print('SCP changed:', before.get('SCP'), '->', after.get('SCP'))
        print('MFG changed:', before.get('MFG'), '->', after.get('MFG'))

if __name__ == '__main__':
    main()

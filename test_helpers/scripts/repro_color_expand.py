# -*- coding: utf-8 -*-
"""Reproduce color-group + expand-level issues on the archdata chart (SCP scope)."""
import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3004'

def get_store(page, name='diagramConfig'):
    return page.evaluate("""
        () => {
            const app = document.querySelector('#app')?.__vue_app__
            const pinia = app?.config?.globalProperties?.$pinia
            return pinia?._s?.get('%s')
        }
    """ % name)

def read_observe(page):
    return page.evaluate("""
        () => {
            const a = window.__archPage || {}
            return {
                colorState: a.colorState || null,
                expandState: a.expandState || null,
                renderSkip: a.mermaid ? a.mermaid.renderSkippedCount : null
            }
        }
    """)

def read_legend(page):
    return page.evaluate("""
        () => {
            const svg = document.querySelector('.mermaid-container svg')
            const legend = document.querySelector('.color-legend, .legend-panel')
            const links = svg ? Array.from(svg.querySelectorAll('path.flowchart-link, .edgePaths > path')).slice(0,20).map(p => p.getAttribute('stroke')) : []
            const nodes = svg ? Array.from(svg.querySelectorAll('g.node')).map(n => (n.id||'') + ':' + ((n.querySelector('.nodeLabel')||{}).textContent||'').slice(0,30)) : []
            return { links, nodeLabels: nodes.slice(0,30), legendText: legend ? legend.textContent.slice(0,500) : null }
        }
    """)

def main():
    with PlaywrightCLI(headless=True) as cli:
        url = BASE + '/system/archdata?preset=scp'
        # dev-login then goto preset URL directly
        cli.goto(BASE + '/api/v1/auth/dev-login?username=admin', wait_until='domcontentloaded')
        cli.goto(url, wait_until='domcontentloaded')
        cli._wait_for_store_ready(timeout=25000)
        try:
            cli.wait_for_selector('svg g.node', timeout=40000)
        except Exception as e:
            print('wait g.node failed:', e)
        cli.wait_for_timeout(3000)
        print('=== BASELINE ===')
        print(json.dumps(read_observe(cli._page), ensure_ascii=False, indent=1))

        # --- Issue 1: expandLevel=domain, colorGroupBy=subDomain ---
        cli.evaluate("""
            () => {
                const app = document.querySelector('#app').__vue_app__
                const pinia = app.config.globalProperties.$pinia
                const s = pinia._s.get('diagramConfig')
                s.setExpandLevel('domain')
                s.updateColorGroupBy('subDomain')
            }
        """)
        cli.wait_for_timeout(4000)
        print('=== AFTER expand=domain, color=subDomain ===')
        print(json.dumps(read_observe(cli._page), ensure_ascii=False, indent=1))
        print(json.dumps(read_legend(cli._page), ensure_ascii=False, indent=1))

        # --- Issue 2: double-click expand (mark manual), then color=serviceModule ---
        cli.evaluate("""
            () => {
                const app = document.querySelector('#app').__vue_app__
                const pinia = app.config.globalProperties.$pinia
                const s = pinia._s.get('diagramConfig')
                s.markGroupManualSet()
            }
        """)
        cli.evaluate("""
            () => {
                const app = document.querySelector('#app').__vue_app__
                const pinia = app.config.globalProperties.$pinia
                const s = pinia._s.get('diagramConfig')
                s.updateColorGroupBy('serviceModule')
            }
        """)
        cli.wait_for_timeout(4000)
        print('=== AFTER groupManualSet + color=serviceModule ===')
        print(json.dumps(read_observe(cli._page), ensure_ascii=False, indent=1))

if __name__ == '__main__':
    main()

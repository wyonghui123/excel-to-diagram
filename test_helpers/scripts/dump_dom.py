# -*- coding: utf-8 -*-
import sys, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3004'
def main():
    with PlaywrightCLI(headless=True) as cli:
        cli.goto(BASE + '/api/v1/auth/dev-login?username=admin', wait_until='domcontentloaded')
        cli.goto(BASE + '/system/archdata?preset=scp', wait_until='domcontentloaded')
        cli._wait_for_store_ready(timeout=25000)
        try:
            cli.wait_for_selector('svg', timeout=40000)
        except Exception as e:
            print('wait svg failed:', e)
        cli.wait_for_timeout(2500)
        info = cli.evaluate("""
            () => {
                const svgs = Array.from(document.querySelectorAll('svg')).map(s => ({id:s.id, cls: s.getAttribute('class'), nodes: s.querySelectorAll('g.node').length, g: s.querySelectorAll('g').length}))
                const mermaidContainer = document.querySelector('.mermaid-container')
                const mermaidContent = document.querySelector('.mermaid-content')
                const allLabels = Array.from(document.querySelectorAll('g.node .nodeLabel')).map(e=>e.textContent).slice(0,40)
                const allNodeIds = Array.from(document.querySelectorAll('g.node')).map(e=>e.id).slice(0,40)
                return { svgs, hasMermaidContainer: !!mermaidContainer, hasContent: !!mermaidContent, allLabels, allNodeIds }
            }
        """)
        print(json.dumps(info, ensure_ascii=False, indent=1))
if __name__ == '__main__':
    main()

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
        cli.wait_for_timeout(3000)
        info = cli.evaluate("""
            () => {
                return {
                    url: location.href,
                    title: document.title,
                    bodyText: (document.body.innerText||'').slice(0,600),
                    appChildren: document.querySelector('#app') ? Array.from(document.querySelector('#app').children).map(c=>c.tagName+'.'+c.className) : [],
                    hasArchdata: !!document.querySelector('.archdata, .arch-data, .embedded-chart, .chart-container')
                }
            }
        """)
        print(json.dumps(info, ensure_ascii=False, indent=1))
if __name__ == '__main__':
    main()

# -*- coding: utf-8 -*-
import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3004'
def wait_svg(page, timeout=45):
    t0 = time.time()
    while time.time()-t0 < timeout:
        n = page.evaluate("() => document.querySelectorAll('svg g.node').length")
        if n:
            return True, n
        time.sleep(1)
    return False, 0

def main():
    with PlaywrightCLI(headless=True) as cli:
        cli.goto(BASE + '/api/v1/auth/dev-login?username=admin', wait_until='domcontentloaded')
        cli.goto(BASE + '/system/archdata?preset=scp', wait_until='domcontentloaded')
        cli._wait_for_store_ready(timeout=25000)
        ok, n = wait_svg(cli._page)
        print('svg ready:', ok, 'nodeCount=', n)
        cli.wait_for_timeout(1500)
        labels = cli.evaluate("() => Array.from(document.querySelectorAll('svg g.node .nodeLabel')).map(e=>e.textContent).slice(0,30)")
        print('labels:', json.dumps(labels, ensure_ascii=False))
if __name__ == '__main__':
    main()

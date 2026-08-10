"""列出 window.__archPage.debug 可用方法."""
import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

def wait_svg(cli, timeout=120):
    for _ in range(timeout):
        try:
            if cli.evaluate("() => !!document.querySelector('.mermaid-content svg') && !!(window.__archPage&&window.__archPage.debug)"):
                time.sleep(1.5)
                return True
        except Exception:
            pass
        time.sleep(1)
    return False

def main():
    with PlaywrightCLI() as cli:
        cli.authenticated_navigate('/system/archdata?preset=scp&mode=debug',
                                   wait_for_selector=None, timeout=60000)
        wait_svg(cli)
        r = cli.evaluate("() => { const d = window.__archPage && window.__archPage.debug; return { archKeys: Object.keys(window.__archPage||{}), debugKeys: d?Object.keys(d):null }; }")
        print('[KEYS]', json.dumps(r, ensure_ascii=False))

if __name__ == '__main__':
    main()

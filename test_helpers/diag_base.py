# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
try:
    page = cli._ensure_browser()
    # dev-login
    page.goto("http://localhost:3004/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded", timeout=10000)
    print("[dev-login] status:", page.title())
    # 首页
    page.goto("http://localhost:3004/", wait_until="domcontentloaded", timeout=10000)
    page.wait_for_timeout(3000)
    print("[base] title:", page.title())
    print("[base] url:", page.url)
    # 检查 app/pinia
    info = page.evaluate("""() => {
        const app = document.querySelector('#app');
        const pinia = app?.__vue_app__?.config?.globalProperties?.$pinia;
        const stores = pinia ? Array.from(pinia._s.keys()) : null;
        return { hasApp: !!app, hasVueApp: !!(app?.__vue_app__), stores };
    }""")
    print("[app/pinia]", info)
    # console message (pageerror)
    errs = getattr(cli, '_page_errors', [])
    print("[pageerrors]", errs)
    cli.screenshot("diag_base.png")
finally:
    cli.close()
# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
try:
    page = cli._ensure_browser()
    # 通过 3004 proxy 访问 dev-login
    resp = page.goto("http://localhost:3004/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded", timeout=10000)
    print("[dev-login thru 3004] status:", resp.status if resp else None)
    print("[body]", page.content()[:200])
    cookies = page.context.cookies()
    print("[cookies after dev-login]:")
    for c in cookies:
        print("   ", c.get('name'), "=", (c.get('value') or '')[:20], "domain=", c.get('domain'), "path=", c.get('path'))
finally:
    cli.close()
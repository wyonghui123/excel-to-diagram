# -*- coding: utf-8 -*-
"""识别 500 错误资源"""
import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=False)
page = cli._ensure_browser()

# Track failing requests
failed = []
page.on("response", lambda resp: failed.append(f"[{resp.status}] {resp.url}") if resp.status >= 400 else None)
page.on("requestfailed", lambda req: failed.append(f"[FAILED] {req.url}: {req.failure}"))

page.goto("http://localhost:3004/",
          wait_until="domcontentloaded", timeout=30000)
time.sleep(5)

print("Failed requests:")
for f in failed:
    print(f"  {f[:200]}")

cli.close()

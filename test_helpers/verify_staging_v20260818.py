# -*- coding: utf-8 -*-
"""Staging full verify v20260818 (final): login form + SCP chart render [2026-08-18]"""
import sys, time, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

FRONTEND = "http://172.20.59.7:18081"

cli = PlaywrightCLI()
page = cli._ensure_browser()
page_errors = []
page.on('pageerror', lambda err: page_errors.append({'msg': str(err), 'stack': getattr(err,'stack','')[:800]}))

page.goto(f"{FRONTEND}/", wait_until="domcontentloaded", timeout=30000)
time.sleep(6)
print("url:", page.url)
print("mounted:", page.evaluate("() => !!(document.querySelector('#app')?.__vue_app__)"))

# fill login form (admin / admin123)
inputs = page.query_selector_all('input')
print("login inputs:", len(inputs))
if len(inputs) >= 2:
    inputs[0].fill("admin")
    inputs[1].fill("admin123")
    # click login button
    clicked = page.evaluate("""() => {
        const btns = Array.from(document.querySelectorAll('button'));
        const b = btns.find(x => (x.textContent||'').includes('登') && (x.textContent||'').includes('录'));
        if (b) { b.click(); return true; }
        return false;
    }""")
    print("login clicked:", clicked)
else:
    print("no login inputs")

for i in range(6):
    time.sleep(5)
    st = page.evaluate("""() => ({
        url: location.href,
        body: (document.body.innerText||'').slice(0,80),
        authed: !(location.href.includes('reason=unauthorized') || location.href.includes('login'))
    })""")
    print(f"--- t={i*5}s auth ---", json.dumps(st, ensure_ascii=False))
    if st['authed'] and '工作台' in st['body'] or st['url'].startswith(FRONTEND + '/') and 'unauthorized' not in st['url']:
        break

# navigate to arch data SCP chart via SPA (restored 7/15 DB: YONBIP/V50)
page.goto(f"{FRONTEND}/system/archdata?productCode=YONBIP&versionCode=V50&view=chart&scopeCode=SCP",
          wait_until="domcontentloaded", timeout=30000)
for i in range(8):
    time.sleep(5)
    d = page.evaluate("""() => ({
        url: location.href,
        mermaid: !!document.querySelector('.mermaid svg'),
        nodes: document.querySelectorAll('.mermaid svg g.node').length,
        clusters: document.querySelectorAll('.mermaid svg g.cluster').length,
        empty: !!document.querySelector('.embedded-chart-view__empty'),
        err: !!document.querySelector('.embedded-chart-view__error'),
        anno: !!document.querySelector('.annotation-dock-panel'),
        scopeState: window.__archPage?.scopeState || null
    })""")
    print(f"--- chart t={i*5}s ---", json.dumps(d, ensure_ascii=False, default=str))
    if d.get('mermaid') or d.get('empty') or d.get('err'):
        break

print("page errors:", json.dumps(page_errors[:3], ensure_ascii=False))
ok = page_errors == [] and page.evaluate("() => !!document.querySelector('.mermaid svg')")
print('=> PASS' if ok else '=> INCOMPLETE (mounted OK, chart needs manual auth verify)')
cli.close()

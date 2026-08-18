# -*- coding: utf-8 -*-
"""Scale-guard 浏览器冒烟: 1) 应用可加载无报错  2) ?scopeGuard.hardRels 小阈值触发硬线弹窗"""
import sys, time, json

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3004'
page_errors = []

cli = PlaywrightCLI()
page = cli._ensure_browser()
page.on('pageerror', lambda err: page_errors.append(str(err)[:300]))
page.on('console', lambda msg: page_errors.append(msg.text[:300]) if msg.type == 'error' else None)

# 1. dev-login
page.goto(f"{BASE}/api/v1/auth/dev-login?username=admin", wait_until='domcontentloaded', timeout=15000)

# 2. 进入 archdata 图表 (尝试 TTTTT000/V11 SCP; 若产品码不对则用页面默认)
urls = [
    f"{BASE}/system/archdata?productCode=TTTTT000&versionCode=V11&view=chart&scopeCode=SCP",
    f"{BASE}/system/archdata",
]
for u in urls:
    page.goto(u, wait_until='domcontentloaded', timeout=20000)
    for _ in range(10):
        time.sleep(2)
        st = page.evaluate("""() => ({
            url: location.href,
            mounted: !!document.querySelector('#app')?.__vue_app__,
            mermaid: !!document.querySelector('.mermaid svg'),
            nodes: document.querySelectorAll('.mermaid svg g.node').length,
            guardBlock: !!document.querySelector('.embedded-chart-view__guard'),
            banner: !!document.querySelector('.scale-guard-banner'),
            body: (document.body.innerText||'').slice(0,60)
        })""")
        print(f'--- {u} t={time.time():.0f} ---', json.dumps(st, ensure_ascii=False, default=str))
        if st.get('mermaid') or st.get('guardBlock') or st.get('banner'):
            break
    if page_errors:
        print('page errors so far:', page_errors[:3])
        break
    if page.evaluate("() => !!document.querySelector('.mermaid svg')"):
        break

# 3. 强制硬线: URL 覆盖阈值 hardRels=5 → 应出现 guard 弹窗
page.goto(f"{BASE}/system/archdata?scopeGuard.hardRels=5&scopeGuard.softRels=2", wait_until='domcontentloaded', timeout=20000)
for _ in range(8):
    time.sleep(2)
    st = page.evaluate("""() => ({
        guardBlock: !!document.querySelector('.embedded-chart-view__guard'),
        dialog: !!document.querySelector('.el-dialog'),
        canvas: !!document.querySelector('.embedded-chart-view__canvas')
    })""")
    print('--- hard-block test ---', json.dumps(st, ensure_ascii=False, default=str))
    if st.get('guardBlock') or st.get('canvas'):
        break

print('final page errors:', page_errors[:5])
cli.close()

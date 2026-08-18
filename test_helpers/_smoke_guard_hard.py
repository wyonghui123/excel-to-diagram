# -*- coding: utf-8 -*-
"""硬线拦截验证: 带产品/版本 + scopeGuard 小阈值"""
import sys, time, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

BASE = 'http://localhost:3004'
errs = []
cli = PlaywrightCLI()
page = cli._ensure_browser()
page.on('pageerror', lambda e: errs.append(str(e)[:300]))
page.on('console', lambda m: errs.append(m.text[:300]) if m.type == 'error' else None)

page.goto(f"{BASE}/api/v1/auth/dev-login?username=admin", wait_until='domcontentloaded', timeout=15000)

# 硬线: hardRels=5 (几乎任何非空图都超) + softRels=2 → 应出现 guard 弹窗 (canvas 不渲染)
u = f"{BASE}/system/archdata?productCode=TTTTT000&versionCode=V11&view=chart&scopeCode=SCP&scopeGuard.hardRels=5&scopeGuard.softRels=2"
page.goto(u, wait_until='domcontentloaded', timeout=20000)
for _ in range(10):
    time.sleep(2)
    st = page.evaluate("""() => ({
        guardBlock: !!document.querySelector('.embedded-chart-view__guard'),
        dialog: !!document.querySelector('.el-dialog__wrapper, .el-overlay'),
        canvas: !!document.querySelector('.embedded-chart-view__canvas'),
        mermaid: !!document.querySelector('.mermaid svg'),
        banner: !!document.querySelector('.scale-guard-banner')
    })""")
    print('--- hard ---', json.dumps(st, ensure_ascii=False))
    if st.get('guardBlock') or st.get('canvas'):
        break

print('errors:', errs[:5])
cli.close()

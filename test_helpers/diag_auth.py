# -*- coding: utf-8 -*-
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from browser_auth_cli import PlaywrightCLI

cli = PlaywrightCLI(headless=True, screenshot_dir="test_output")
try:
    page = cli._ensure_browser()
    page.goto("http://localhost:3004/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded", timeout=10000)
    page.wait_for_timeout(500)
    page.goto("http://localhost:3004/", wait_until="domcontentloaded", timeout=10000)
    # 等待 auth store user 出现
    for i in range(10):
        st = page.evaluate("""() => {
            const pinia = document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia;
            const auth = pinia ? pinia._s.get('auth') : null;
            return { sessionReady: auth?.sessionReady, isLoggedIn: auth?.isLoggedIn, user: !!auth?.user, userName: auth?.user?.username || null };
        }""")
        print(f"[{i}] auth:", st)
        if st.get('user'):
            break
        page.wait_for_timeout(1000)
except Exception as e:
    print("[ERR]", e)
finally:
    cli.close()
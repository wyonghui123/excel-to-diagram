"""Quick check of homepage loading"""
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import time

cli = PlaywrightCLI()
try:
    page = cli.goto('http://localhost:3010/api/v1/auth/dev-login?username=admin', wait_until='domcontentloaded')
    print('dev-login done')
    page = cli.goto('http://localhost:3004', wait_until='networkidle')
    print('homepage done')
    time.sleep(5)
    body_html = cli.evaluate('() => document.body.outerHTML.substring(0, 2000)')
    print(f'body_html={body_html}')
    overlay = cli.evaluate('() => document.querySelector("vite-error-overlay")?.shadowRoot?.querySelector(".message-body")?.textContent || ""')
    print(f'overlay={overlay}')
    title = cli.evaluate('() => document.title')
    print(f'title={title}')
    body_html = cli.evaluate('() => document.body.innerHTML.length')
    print(f'body_length={body_html}')
    app_html = cli.evaluate('() => document.querySelector("#app")?.innerHTML.length || 0')
    print(f'app_length={app_html}')
    body_text = cli.evaluate('() => document.body.innerText.substring(0, 200)')
    print(f'body_text={body_text!r}')
    has_vue = cli.evaluate('() => !!document.querySelector("#app")?.__vue_app__')
    print(f'has_vue={has_vue}')
    auth_ready = cli.evaluate('() => { const a = document.querySelector("#app")?.__vue_app__; const p = a?.config?.globalProperties?.$pinia; const s = p?._s?.get("auth"); return !!(s && s.sessionReady && s.user) }')
    print(f'auth_ready={auth_ready}')
    current_url = cli.evaluate('() => window.location.href')
    print(f'current_url={current_url}')
except Exception as e:
    print(f'ERROR: {e}')
    import traceback
    traceback.print_exc()
finally:
    cli.close()

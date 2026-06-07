import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import json

cli = PlaywrightCLI(headless=True, screenshot_dir='d:/filework/excel-to-diagram/test_helpers/screenshots')

try:
    print("[1] 测试 dev-login ...")
    page = cli._ensure_browser()
    page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded", timeout=10000)
    print(f"  dev-login URL: {page.url}")

    print("[2] 加载首页 ...")
    page.goto("http://localhost:3004/", wait_until="domcontentloaded", timeout=10000)
    print(f"  首页 URL: {page.url}")
    print(f"  首页 title: {page.title()}")

    page.wait_for_timeout(3000)

    body_text = page.evaluate("() => document.body.innerText.substring(0, 300)")
    print(f"  页面内容: {body_text[:200]}")

    cli.screenshot('diagnose_home.png')

    print("[3] 等待 store 就绪 ...")
    try:
        cli._wait_for_store_ready(timeout=15000)
        print("  Store 就绪!")
    except Exception as e:
        print(f"  Store 等待失败: {e}")
        body_text2 = page.evaluate("() => document.body.innerText.substring(0, 300)")
        print(f"  当前页面内容: {body_text2[:200]}")

    print("[4] SPA 导航到 /system/role ...")
    page.evaluate("""
        () => {
            const router = document.querySelector('#app').__vue_app__
                .config.globalProperties.$router
            router.push('/system/role')
        }
    """)
    page.wait_for_timeout(5000)

    body_text3 = page.evaluate("() => document.body.innerText.substring(0, 500)")
    print(f"  导航后内容: {body_text3[:300]}")

    current_url = page.evaluate("() => window.location.href")
    print(f"  当前URL: {current_url}")

    has_table = page.evaluate("() => !!document.querySelector('.el-table')")
    print(f"  有表格: {has_table}")

    cli.screenshot('diagnose_role.png')

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
finally:
    cli.close()

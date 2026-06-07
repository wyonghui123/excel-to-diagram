import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import json

cli = PlaywrightCLI(headless=True, screenshot_dir='d:/filework/excel-to-diagram/test_helpers/screenshots')

try:
    print("[1] 认证 + 导航 ...")
    page = cli._ensure_browser()
    page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded", timeout=10000)
    page.goto("http://localhost:3004/", wait_until="domcontentloaded", timeout=10000)
    cli._wait_for_store_ready(timeout=15000)
    print("  Store 就绪!")

    print("[2] SPA 导航到 /system/role ...")
    page.evaluate("""
        () => {
            const router = document.querySelector('#app').__vue_app__
                .config.globalProperties.$router
            router.push('/system/role')
        }
    """)

    # 等待更长时间
    print("  等待页面渲染 ...")
    page.wait_for_timeout(8000)

    # 检查路由
    current_route = page.evaluate("""
        () => {
            const app = document.querySelector('#app').__vue_app__;
            const router = app.config.globalProperties.$router;
            return {
                currentPath: router.currentRoute.value.path,
                currentName: router.currentRoute.value.name,
                url: window.location.href
            };
        }
    """)
    print(f"  当前路由: {json.dumps(current_route, ensure_ascii=False)}")

    # 检查页面内容
    body_text = page.evaluate("() => document.body.innerText.substring(0, 800)")
    print(f"  页面内容: {body_text[:500]}")

    # 检查是否有错误
    has_error = page.evaluate("""
        () => {
            const errors = document.querySelectorAll('.el-message--error, .el-notification--error');
            return errors.length > 0 ? Array.from(errors).map(e => e.textContent) : [];
        }
    """)
    if has_error:
        print(f"  页面错误: {has_error}")

    # 检查是否有 loading
    has_loading = page.evaluate("""
        () => {
            const loading = document.querySelectorAll('.el-loading-mask, .el-loading-spinner');
            return loading.length;
        }
    """)
    print(f"  Loading 元素: {has_loading}")

    # 检查主内容区域
    main_content = page.evaluate("""
        () => {
            const main = document.querySelector('.main-content, .app-main, .layout-main, [class*="main"], [class*="content"]');
            if (!main) return 'no main content area found';
            return main.innerHTML.substring(0, 500);
        }
    """)
    print(f"  主内容区: {str(main_content)[:300]}")

    cli.screenshot('role_page_debug.png')

    # 尝试等待表格出现
    print("\n[3] 等待表格 ...")
    try:
        page.wait_for_selector('.el-table', timeout=15000)
        print("  表格出现!")
    except:
        print("  表格仍未出现，再等5秒 ...")
        page.wait_for_timeout(5000)
        body_text2 = page.evaluate("() => document.body.innerText.substring(0, 800)")
        print(f"  页面内容: {body_text2[:500]}")
        cli.screenshot('role_page_debug2.png')

        # 检查是否有API错误
        api_error = page.evaluate("""
            () => {
                const app = document.querySelector('#app').__vue_app__;
                const pinia = app.config.globalProperties.$pinia;
                const stores = {};
                for (const [name, store] of pinia._s) {
                    if (store.error || store.loading !== undefined) {
                        stores[name] = {
                            error: store.error,
                            loading: store.loading
                        };
                    }
                }
                return stores;
            }
        """)
        print(f"  Store 状态: {json.dumps(api_error, ensure_ascii=False, default=str)[:500]}")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
finally:
    cli.close()

import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import json

cli = PlaywrightCLI(headless=True, screenshot_dir='d:/filework/excel-to-diagram/test_helpers/screenshots')

try:
    print("[1] 认证 + 加载首页 ...")
    page = cli._ensure_browser()
    page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded", timeout=10000)
    page.goto("http://localhost:3004/", wait_until="domcontentloaded", timeout=10000)
    cli._wait_for_store_ready(timeout=15000)
    print("  Store 就绪!")

    # 查找并点击"系统管理"导航项
    print("\n[2] 点击'系统管理'导航项 ...")
    nav_clicked = cli.click('.nav-item:has-text("系统管理")', timeout=5000, wait_after=2000)
    print(f"  点击结果: {nav_clicked}")

    # 检查当前URL和页面内容
    current_url = page.evaluate("() => window.location.href")
    print(f"  当前URL: {current_url}")

    body_text = page.evaluate("() => document.body.innerText.substring(0, 800)")
    print(f"  页面内容: {body_text[:400]}")

    cli.screenshot('system_nav_clicked.png')

    # 查找"角色"相关的导航项
    print("\n[3] 查找角色管理入口 ...")
    role_entries = page.evaluate("""
        () => {
            const allElements = document.querySelectorAll('*');
            const matches = [];
            for (const el of allElements) {
                const text = el.textContent?.trim() || '';
                if (text.includes('角色') && el.children.length === 0 && text.length < 20) {
                    matches.push({
                        tag: el.tagName,
                        text: text.substring(0, 30),
                        className: (el.className || '').toString().substring(0, 80),
                        parent: el.parentElement?.className?.substring(0, 80) || '',
                        parentTag: el.parentElement?.tagName || ''
                    });
                }
            }
            return matches.slice(0, 10);
        }
    """)
    print(f"  角色入口: {json.dumps(role_entries, ensure_ascii=False, default=str)[:800]}")

    # 检查子导航
    print("\n[4] 检查子导航 ...")
    sub_nav = page.evaluate("""
        () => {
            const navItems = document.querySelectorAll('.nav-item, .sub-nav-item, .nav-sub-item, [class*="nav"]');
            return Array.from(navItems).slice(0, 20).map(item => ({
                text: item.textContent.trim().substring(0, 40),
                className: (item.className || '').toString().substring(0, 80),
                href: item.getAttribute('href') || '',
                dataIndex: item.getAttribute('data-index') || ''
            }));
        }
    """)
    print(f"  子导航: {json.dumps(sub_nav, ensure_ascii=False, default=str)[:800]}")

    # 尝试查找角色管理链接
    print("\n[5] 查找角色管理链接 ...")
    role_link = page.evaluate("""
        () => {
            const links = document.querySelectorAll('a, [role="link"], [role="menuitem"], .nav-item');
            for (const link of links) {
                const text = link.textContent?.trim() || '';
                if (text.includes('角色管理') || text.includes('角色列表')) {
                    return {
                        text: text.substring(0, 50),
                        href: link.getAttribute('href') || '',
                        className: (link.className || '').toString().substring(0, 80),
                        onclick: link.getAttribute('onclick') || ''
                    };
                }
            }
            return null;
        }
    """)
    print(f"  角色管理链接: {json.dumps(role_link, ensure_ascii=False, default=str)}")

    # 尝试直接导航到角色管理页面（使用hash路由）
    print("\n[6] 尝试 hash 路由导航 ...")
    page.evaluate("() => { window.location.hash = '#/system/role'; }")
    page.wait_for_timeout(3000)
    current_url2 = page.evaluate("() => window.location.href")
    print(f"  当前URL: {current_url2}")

    has_table2 = page.evaluate("() => !!document.querySelector('.el-table')")
    print(f"  有表格: {has_table2}")

    if not has_table2:
        # 尝试通过 router.push
        print("\n[7] 尝试 router.push ...")
        route_result = page.evaluate("""
            () => {
                const app = document.querySelector('#app').__vue_app__;
                const router = app.config.globalProperties.$router;
                const routes = router.getRoutes();
                const systemRoutes = routes.filter(r => r.path.startsWith('/system'));
                return systemRoutes.map(r => r.path);
            }
        """)
        print(f"  /system 路由: {route_result}")

        # 检查是否有 bo=role 参数路由
        bo_routes = page.evaluate("""
            () => {
                const app = document.querySelector('#app').__vue_app__;
                const router = app.config.globalProperties.$router;
                const routes = router.getRoutes();
                return routes.filter(r => r.path.includes('bo') || r.path.includes('meta')).map(r => r.path);
            }
        """)
        print(f"  bo/meta 路由: {bo_routes}")

        # 尝试导航到 /system/archdata?bo=role
        print("\n[8] 尝试 /system/archdata?bo=role ...")
        page.evaluate("""
            () => {
                const app = document.querySelector('#app').__vue_app__;
                const router = app.config.globalProperties.$router;
                router.push({ path: '/system/archdata', query: { bo: 'role' } });
            }
        """)
        page.wait_for_timeout(5000)

        current_url3 = page.evaluate("() => window.location.href")
        print(f"  当前URL: {current_url3}")

        has_table3 = page.evaluate("() => !!document.querySelector('.el-table')")
        print(f"  有表格: {has_table3}")

        body_text3 = page.evaluate("() => document.body.innerText.substring(0, 500)")
        print(f"  页面内容: {body_text3[:300]}")

        cli.screenshot('archdata_bo_role.png')

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
finally:
    cli.close()

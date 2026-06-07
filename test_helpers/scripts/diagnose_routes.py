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

    # 检查所有路由
    print("\n[2] 检查所有路由 ...")
    all_routes = page.evaluate("""
        () => {
            const app = document.querySelector('#app').__vue_app__;
            const router = app.config.globalProperties.$router;
            const routes = router.getRoutes();
            return routes.map(r => ({
                path: r.path,
                name: r.name,
                meta: r.meta?.title || ''
            }));
        }
    """)
    system_routes = [r for r in all_routes if 'system' in r.get('path', '').lower() or 'role' in r.get('path', '').lower() or '系统' in r.get('meta', '')]
    print(f"  系统/角色相关路由:")
    for r in system_routes:
        print(f"    {r['path']} (name={r['name']}, meta={r['meta']})")

    # 检查侧边栏菜单
    print("\n[3] 检查侧边栏菜单 ...")
    sidebar = page.evaluate("""
        () => {
            const sidebar = document.querySelector('.sidebar, .el-menu, [class*="sidebar"], [class*="menu"], [class*="nav"]');
            if (!sidebar) return { found: false, allClasses: document.body.innerHTML.substring(0, 200) };

            const items = sidebar.querySelectorAll('a, .menu-item, .nav-item, li');
            return {
                found: true,
                className: sidebar.className.substring(0, 100),
                itemCount: items.length,
                items: Array.from(items).slice(0, 20).map(item => ({
                    text: item.textContent.trim().substring(0, 30),
                    href: item.getAttribute('href') || ''
                }))
            };
        }
    """)
    print(f"  侧边栏: {json.dumps(sidebar, ensure_ascii=False, default=str)[:800]}")

    # 检查完整的菜单结构
    print("\n[4] 检查完整菜单结构 ...")
    menu_structure = page.evaluate("""
        () => {
            const elMenu = document.querySelector('.el-menu');
            if (!elMenu) return { found: false };

            const allItems = elMenu.querySelectorAll('.el-menu-item, .el-sub-menu__title, .el-menu-item-group__title');
            return {
                found: true,
                items: Array.from(allItems).map(item => ({
                    text: item.textContent.trim().substring(0, 40),
                    className: item.className.substring(0, 60),
                    dataIndex: item.getAttribute('data-index') || ''
                }))
            };
        }
    """)
    print(f"  菜单结构: {json.dumps(menu_structure, ensure_ascii=False, default=str)[:800]}")

    # 检查左侧导航
    print("\n[5] 检查左侧导航 ...")
    nav_info = page.evaluate("""
        () => {
            const navLinks = document.querySelectorAll('a[href], [data-path], [data-route]');
            return Array.from(navLinks).slice(0, 30).map(link => ({
                text: link.textContent.trim().substring(0, 30),
                href: link.getAttribute('href') || '',
                dataPath: link.getAttribute('data-path') || link.getAttribute('data-route') || ''
            }));
        }
    """)
    print(f"  导航链接: {json.dumps(nav_info, ensure_ascii=False, default=str)[:800]}")

    # 查找"系统管理"或"角色"相关的可点击元素
    print("\n[6] 查找系统管理入口 ...")
    system_entry = page.evaluate("""
        () => {
            const allElements = document.querySelectorAll('*');
            const matches = [];
            for (const el of allElements) {
                const text = el.textContent?.trim() || '';
                if ((text.includes('系统管理') || text.includes('角色')) && el.children.length === 0 && text.length < 20) {
                    matches.push({
                        tag: el.tagName,
                        text: text.substring(0, 30),
                        className: (el.className || '').toString().substring(0, 80),
                        parent: el.parentElement?.className?.substring(0, 80) || ''
                    });
                }
            }
            return matches.slice(0, 15);
        }
    """)
    print(f"  系统管理入口: {json.dumps(system_entry, ensure_ascii=False, default=str)[:800]}")

    cli.screenshot('home_page_full.png')

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
finally:
    cli.close()

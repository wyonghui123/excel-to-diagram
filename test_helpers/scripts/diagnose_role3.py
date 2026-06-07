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

    # 检查路由配置
    print("\n[2] 检查路由配置 ...")
    routes_info = page.evaluate("""
        () => {
            const app = document.querySelector('#app').__vue_app__;
            const router = app.config.globalProperties.$router;
            const routes = router.getRoutes();
            const roleRoutes = routes.filter(r => r.path.includes('role'));
            return roleRoutes.map(r => ({
                path: r.path,
                name: r.name,
                component: r.components?.default?.name || 'unknown',
                meta: r.meta
            }));
        }
    """)
    print(f"  角色相关路由: {json.dumps(routes_info, ensure_ascii=False, default=str)[:500]}")

    # 检查菜单项
    print("\n[3] 检查菜单项 ...")
    menu_items = page.evaluate("""
        () => {
            const menuItems = document.querySelectorAll('.el-menu-item, .el-sub-menu__title');
            return Array.from(menuItems).map(item => ({
                text: item.textContent.trim().substring(0, 50),
                href: item.getAttribute('href') || item.dataset?.path || ''
            }));
        }
    """)
    print(f"  菜单项: {json.dumps(menu_items, ensure_ascii=False, indent=2)[:500]}")

    # 尝试通过菜单导航
    print("\n[4] 通过菜单导航 ...")
    # 先找到"系统管理"子菜单
    system_menu = page.evaluate("""
        () => {
            const items = document.querySelectorAll('.el-sub-menu__title');
            for (const item of items) {
                if (item.textContent.includes('系统管理')) {
                    return true;
                }
            }
            return false;
        }
    """)
    print(f"  系统管理菜单存在: {system_menu}")

    if system_menu:
        # 点击系统管理
        clicked = cli.click('.el-sub-menu__title:has-text("系统管理")', timeout=5000, wait_after=1000)
        print(f"  点击系统管理: {clicked}")

        # 检查子菜单
        submenu = page.evaluate("""
            () => {
                const items = document.querySelectorAll('.el-menu-item');
                return Array.from(items).map(item => ({
                    text: item.textContent.trim().substring(0, 50),
                    index: item.getAttribute('data-index') || ''
                }));
            }
        """)
        print(f"  子菜单项: {json.dumps(submenu, ensure_ascii=False)[:500]}")

        # 点击角色管理
        role_clicked = cli.click('.el-menu-item:has-text("角色")', timeout=5000, wait_after=3000)
        print(f"  点击角色管理: {role_clicked}")

        # 检查页面
        page.wait_for_timeout(3000)
        current_url = page.evaluate("() => window.location.href")
        print(f"  当前URL: {current_url}")

        has_table = page.evaluate("() => !!document.querySelector('.el-table')")
        print(f"  有表格: {has_table}")

        body_text = page.evaluate("() => document.body.innerText.substring(0, 500)")
        print(f"  页面内容: {body_text[:300]}")

        cli.screenshot('role_via_menu.png')

        if has_table:
            print("\n[5] 表格已加载! 开始测试过滤功能 ...")

            # 检查表头
            headers = page.evaluate("""
                () => {
                    const ths = document.querySelectorAll('.el-table__header th');
                    return Array.from(ths).map((th, i) => ({
                        index: i,
                        text: th.textContent.trim().substring(0, 30),
                        hasFilter: !!th.querySelector('.el-table__column-filter-trigger')
                    }));
                }
            """)
            print(f"  表头: {json.dumps(headers, ensure_ascii=False)[:500]}")

            # 检查 is_system 列
            is_system_col = page.evaluate("""
                () => {
                    const ths = document.querySelectorAll('.el-table__header th');
                    for (let i = 0; i < ths.length; i++) {
                        if (ths[i].textContent.includes('系统角色')) {
                            return {
                                index: i,
                                hasFilter: !!ths[i].querySelector('.el-table__column-filter-trigger'),
                                classList: Array.from(ths[i].classList)
                            };
                        }
                    }
                    return null;
                }
            """)
            print(f"  is_system 列: {json.dumps(is_system_col, ensure_ascii=False)}")

            # 检查 API filters
            api_filters = page.evaluate("""
                () => {
                    const app = document.querySelector('#app').__vue_app__;
                    const pinia = app.config.globalProperties.$pinia;
                    const boCrud = pinia._s.get('boCrud');
                    if (boCrud && boCrud.apiFilterConfigs) {
                        return JSON.stringify(boCrud.apiFilterConfigs);
                    }
                    return 'apiFilterConfigs not found';
                }
            """)
            print(f"  API filters: {str(api_filters)[:500]}")

            # 检查 columns filterType
            columns_info = page.evaluate("""
                () => {
                    const app = document.querySelector('#app').__vue_app__;
                    const pinia = app.config.globalProperties.$pinia;
                    const metaList = pinia._s.get('metaList');
                    if (metaList && metaList.columns) {
                        const isSystemCol = metaList.columns.find(c => c.prop === 'is_system' || c.key === 'is_system');
                        if (isSystemCol) {
                            return JSON.stringify({
                                prop: isSystemCol.prop,
                                label: isSystemCol.label,
                                filterType: isSystemCol.filterType,
                                filters: isSystemCol.filters,
                                filterable: isSystemCol.filterable
                            });
                        }
                        return 'is_system column not found';
                    }
                    return 'metaList store not found';
                }
            """)
            print(f"  columns filterType: {str(columns_info)[:500]}")

            # 点击过滤图标
            if is_system_col and is_system_col.get('hasFilter'):
                print("\n  点击过滤图标 ...")
                idx = is_system_col['index']
                cli.click(f'.el-table__header th:nth-child({idx + 1}) .el-table__column-filter-trigger', timeout=5000, wait_after=1000)
                cli.screenshot('role_filter_opened.png')

                filter_content = page.evaluate("""
                    () => {
                        const poppers = document.querySelectorAll('.el-popper');
                        for (const p of poppers) {
                            if (p.offsetHeight > 0 && p.textContent.trim().length > 0) {
                                return {
                                    text: p.textContent.substring(0, 300),
                                    hasSelect: !!p.querySelector('.el-select'),
                                    hasCheckbox: !!p.querySelector('.el-checkbox'),
                                    html: p.innerHTML.substring(0, 500)
                                };
                            }
                        }
                        return { found: false };
                    }
                """)
                print(f"  过滤面板内容: {json.dumps(filter_content, ensure_ascii=False)[:500]}")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
finally:
    cli.close()

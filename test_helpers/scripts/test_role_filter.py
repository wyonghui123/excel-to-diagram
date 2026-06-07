import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
import json

SCREENSHOT_DIR = 'd:/filework/excel-to-diagram/test_helpers/screenshots'
cli = PlaywrightCLI(headless=True, screenshot_dir=SCREENSHOT_DIR)

print("=" * 60)
print("角色列表过滤功能 - 完整诊断")
print("=" * 60)

try:
    print("\n[Step 1] 认证并导航到角色管理 ...")
    page = cli._ensure_browser()
    page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin", wait_until="domcontentloaded", timeout=10000)
    page.goto("http://localhost:3004/", wait_until="domcontentloaded", timeout=10000)
    cli._wait_for_store_ready(timeout=15000)
    print("  Store 就绪!")

    page.evaluate("""
        () => {
            const router = document.querySelector('#app').__vue_app__
                .config.globalProperties.$router
            router.push({ path: '/user-permission', query: { tab: 'roles' } })
        }
    """)
    page.wait_for_timeout(5000)
    print("  导航完成!")

    # Step 2: 在浏览器中调用 API（带认证 cookie）
    print("\n[Step 2] 在浏览器中调用 /api/v2/bo/role ...")
    api_response = page.evaluate("""
        async () => {
            try {
                const resp = await fetch('/api/v2/bo/role?page=1&page_size=5');
                const data = await resp.json();
                return {
                    status: resp.status,
                    keys: Object.keys(data),
                    success: data.success,
                    hasData: !!data.data,
                    dataKeys: data.data ? Object.keys(data.data) : [],
                    hasFilters: data.data ? 'filters' in data.data : false,
                    filtersValue: data.data && data.data.filters ? JSON.stringify(data.data.filters).substring(0, 500) : 'N/A',
                    itemsCount: data.data && data.data.items ? data.data.items.length : 0,
                    firstItem: data.data && data.data.items && data.data.items[0] ? Object.keys(data.data.items[0]) : [],
                    code: data.code || null,
                    error: data.error || null
                };
            } catch (e) {
                return { error: e.message };
            }
        }
    """)
    print(f"  API 响应: {json.dumps(api_response, ensure_ascii=False, default=str)[:800]}")

    # Step 3: 检查表头中的过滤图标（使用正确的选择器）
    print("\n[Step 3] 检查'系统角色'列过滤图标 ...")
    filter_info = page.evaluate("""
        () => {
            const tables = document.querySelectorAll('.el-table');
            for (let i = 0; i < tables.length; i++) {
                const ths = tables[i].querySelectorAll('.el-table__header th');
                for (const th of ths) {
                    if (th.textContent.includes('系统角色')) {
                        const filterTrigger = th.querySelector('.filter-trigger, .el-table__column-filter-trigger');
                        return {
                            tableIndex: i,
                            hasFilterTrigger: !!filterTrigger,
                            triggerClassName: filterTrigger ? filterTrigger.className : 'not found',
                            triggerHTML: filterTrigger ? filterTrigger.outerHTML.substring(0, 300) : 'not found'
                        };
                    }
                }
            }
            return 'not found';
        }
    """)
    print(f"  过滤图标: {json.dumps(filter_info, ensure_ascii=False, default=str)[:500]}")

    # Step 4: 点击过滤图标
    if isinstance(filter_info, dict) and filter_info.get('hasFilterTrigger'):
        print("\n[Step 4] 点击过滤图标 ...")
        table_idx = filter_info['tableIndex']
        page.evaluate(f"""
            () => {{
                const tables = document.querySelectorAll('.el-table');
                const ths = tables[{table_idx}].querySelectorAll('.el-table__header th');
                for (const th of ths) {{
                    if (th.textContent.includes('系统角色')) {{
                        const trigger = th.querySelector('.filter-trigger, .el-table__column-filter-trigger');
                        if (trigger) trigger.click();
                        return true;
                    }}
                }}
                return false;
            }}
        """)
        page.wait_for_timeout(1500)

        cli.screenshot('role_filter_panel_opened.png')

        # 检查过滤面板
        panel_info = page.evaluate("""
            () => {
                const poppers = document.querySelectorAll('.el-popper, .filter-panel, .table-header-filter, [class*="filter-popover"], [class*="filter-panel"]');
                const visiblePanels = [];
                for (const p of poppers) {
                    if (p.offsetHeight > 0 && p.textContent.trim().length > 0) {
                        visiblePanels.push({
                            className: p.className.substring(0, 100),
                            text: p.textContent.substring(0, 200),
                            hasSelect: !!p.querySelector('.el-select'),
                            hasCheckbox: !!p.querySelector('.el-checkbox'),
                            hasRadio: !!p.querySelector('.el-radio'),
                            html: p.innerHTML.substring(0, 500)
                        });
                    }
                }
                return visiblePanels;
            }
        """)
        print(f"  可见面板: {json.dumps(panel_info, ensure_ascii=False, default=str)[:800]}")

        # V1 验证
        has_select = any(p.get('hasSelect') for p in panel_info) if panel_info else False
        has_checkbox = any(p.get('hasCheckbox') for p in panel_info) if panel_info else False
        if has_select:
            print("  [V1 PASS] 过滤面板包含 select 下拉选择框")
        elif has_checkbox:
            print("  [V1 PASS] 过滤面板包含 checkbox 复选框")
        else:
            print("  [V1 INFO] 过滤面板没有 select/checkbox，检查面板内容 ...")
            for p in panel_info:
                print(f"    面板文本: {p.get('text', '')[:100]}")

    # Step 5: 检查 Pinia store 中的 useMetaList 实例
    print("\n[Step 5] 检查 useMetaList composable 实例 ...")
    meta_list_info = page.evaluate("""
        () => {
            const app = document.querySelector('#app').__vue_app__;
            const pinia = app.config.globalProperties.$pinia;
            const allStores = [];
            for (const [name, store] of pinia._s) {
                const keys = Object.keys(store);
                const hasColumns = keys.includes('columns');
                const hasApiFilterConfigs = keys.includes('apiFilterConfigs');
                const hasFilterFields = keys.includes('filterFields');
                if (hasColumns || hasApiFilterConfigs || hasFilterFields) {
                    allStores.push({
                        name,
                        hasColumns,
                        hasApiFilterConfigs,
                        hasFilterFields,
                        keyCount: keys.length,
                        sampleKeys: keys.slice(0, 20)
                    });
                }
            }
            return allStores;
        }
    """)
    print(f"  相关 stores: {json.dumps(meta_list_info, ensure_ascii=False, default=str)[:800]}")

    # Step 6: 检查 GenericObjectList 组件中的 MetaListPage
    print("\n[Step 6] 检查 MetaListPage 组件实例 ...")
    component_info = page.evaluate("""
        () => {
            const app = document.querySelector('#app').__vue_app__;
            const pinia = app.config.globalProperties.$pinia;
            const result = [];
            for (const [name, store] of pinia._s) {
                const keys = Object.keys(store);
                if (keys.includes('columns')) {
                    const isSystemCol = store.columns.find(c => c.prop === 'is_system');
                    if (isSystemCol) {
                        result.push({
                            storeName: name,
                            filterType: isSystemCol.filterType,
                            filters: isSystemCol.filters,
                            filterable: isSystemCol.filterable,
                            colKeys: Object.keys(isSystemCol)
                        });
                    }
                }
            }
            return result.length > 0 ? result : 'no store with is_system column found';
        }
    """)
    print(f"  组件信息: {json.dumps(component_info, ensure_ascii=False, default=str)[:800]}")

    print("\n" + "=" * 60)
    print("诊断完成!")
    print("=" * 60)

except Exception as e:
    print(f"\n[ERROR] {e}")
    import traceback
    traceback.print_exc()
    try:
        cli.screenshot('error_screenshot.png')
    except:
        pass
finally:
    cli.close()

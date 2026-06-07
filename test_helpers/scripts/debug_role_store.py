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

    page.evaluate("""
        () => {
            const router = document.querySelector('#app').__vue_app__
                .config.globalProperties.$router
            router.push({ path: '/user-permission', query: { tab: 'roles' } })
        }
    """)
    page.wait_for_selector('.el-table', timeout=15000)
    print("  页面加载完成!")

    # 列出所有 Pinia stores
    print("\n[2] 列出所有 Pinia stores ...")
    stores = page.evaluate("""
        () => {
            const app = document.querySelector('#app').__vue_app__;
            const pinia = app.config.globalProperties.$pinia;
            const storeNames = [];
            for (const [name, store] of pinia._s) {
                const keys = Object.keys(store).filter(k => !k.startsWith('_'));
                storeNames.push({ name, keys: keys.slice(0, 30) });
            }
            return storeNames;
        }
    """)
    for s in stores:
        print(f"  Store: {s['name']} -> keys: {s['keys'][:15]}")

    # 查找包含 apiFilterConfigs 的 store
    print("\n[3] 查找 apiFilterConfigs ...")
    api_filter_store = page.evaluate("""
        () => {
            const app = document.querySelector('#app').__vue_app__;
            const pinia = app.config.globalProperties.$pinia;
            for (const [name, store] of pinia._s) {
                if (store.apiFilterConfigs !== undefined) {
                    return { store: name, value: JSON.stringify(store.apiFilterConfigs) };
                }
            }
            return 'not found in any store';
        }
    """)
    print(f"  apiFilterConfigs: {str(api_filter_store)[:500]}")

    # 查找包含 columns 的 store
    print("\n[4] 查找 columns ...")
    columns_store = page.evaluate("""
        () => {
            const app = document.querySelector('#app').__vue_app__;
            const pinia = app.config.globalProperties.$pinia;
            for (const [name, store] of pinia._s) {
                if (store.columns && Array.isArray(store.columns)) {
                    const isSystemCol = store.columns.find(c => c.prop === 'is_system' || c.key === 'is_system');
                    if (isSystemCol) {
                        return {
                            store: name,
                            prop: isSystemCol.prop,
                            label: isSystemCol.label,
                            filterType: isSystemCol.filterType,
                            filters: isSystemCol.filters,
                            filterable: isSystemCol.filterable,
                            allKeys: Object.keys(isSystemCol)
                        };
                    }
                }
            }
            return 'is_system column not found in any store';
        }
    """)
    print(f"  columns store: {json.dumps(columns_store, ensure_ascii=False, default=str)[:500]}")

    # 检查"系统角色"列的 th 元素详细属性
    print("\n[5] 检查'系统角色'列 th 详细属性 ...")
    th_detail = page.evaluate("""
        () => {
            const ths = document.querySelectorAll('.el-table__header th');
            for (let i = 0; i < ths.length; i++) {
                if (ths[i].textContent.includes('系统角色')) {
                    return {
                        index: i,
                        className: ths[i].className,
                        innerHTML: ths[i].innerHTML.substring(0, 1000),
                        cellClassName: ths[i].querySelector('.cell')?.className || 'no cell'
                    };
                }
            }
            return null;
        }
    """)
    if th_detail:
        print(f"  索引: {th_detail['index']}")
        print(f"  className: {th_detail['className'][:200]}")
        print(f"  innerHTML: {th_detail['innerHTML'][:500]}")

    # 检查 API 请求
    print("\n[6] 检查 API /api/v2/bo/role 响应 ...")
    api_response = page.evaluate("""
        async () => {
            try {
                const resp = await fetch('/api/v2/bo/role?page=1&page_size=1');
                const data = await resp.json();
                return {
                    hasFilters: !!data.filters,
                    filtersLength: data.filters ? data.filters.length : 0,
                    filters: data.filters ? JSON.stringify(data.filters) : 'no filters',
                    itemKeys: data.items && data.items[0] ? Object.keys(data.items[0]) : []
                };
            } catch (e) {
                return { error: e.message };
            }
        }
    """)
    print(f"  API 响应: {json.dumps(api_response, ensure_ascii=False, default=str)[:800]}")

    cli.screenshot('role_debug_final.png')

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
finally:
    cli.close()

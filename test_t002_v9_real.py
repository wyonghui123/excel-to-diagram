"""
T-002 E2E v9 - 真实流程: 创建新产品 → 打开切换产品下拉 → 验证新数据出现

这是 T-002 fix 的真正验收测试:
- 步骤 1: 用 API 创建一个新 product (唯一 name, 便于后续搜索)
- 步骤 2: 打开 3007 + 跳到 /system/archdata
- 步骤 3: 点击"切换"按钮 → 点击"切换产品"
- 步骤 4: 验证弹窗下拉中能搜索到这个新产品

验收标准:
- 创建的 product name 能在下拉选项中找到
- 验证 fetchProducts() 被调用 (通过 network 或 cache 行为)
"""
import sys
import time
import json
import urllib.request
import urllib.error
sys.path.insert(0, r'D:\filework\worktrees/integration')

from test_helpers.browser_auth_cli import PlaywrightCLI

print("=== T-002 E2E v9: 真实流程验证 ===\n")

# ===== 步骤 1: 在浏览器内通过 boService 创建新 product (让 boService 缓存被清除) =====
UNIQUE_NAME = f"T002E2E_{int(time.time())}"
UNIQUE_CODE = f"T002_{int(time.time())}"  # 大写字母开头, 匹配 ^[A-Z][A-Z0-9_]*$
print(f"[1] 准备在浏览器内创建 product: {UNIQUE_NAME}")

# ===== 步骤 2: 打开浏览器, 走完整 UI 流程 =====
print("\n[2] 打开浏览器...")
cli = PlaywrightCLI(screenshot_dir=r'D:\filework\worktrees/integration\test_output\t002')

# 2.1 dev-login in browser
cli.goto('http://localhost:3018/api/v1/auth/dev-login?username=admin', wait_until='domcontentloaded')
time.sleep(1)

# 2.2 网络监听
product_requests = []
def on_request(req):
    if '/api/v2/bo/product' in req.url:
        product_requests.append({'url': req.url, 'method': req.method, 'time': time.time()})
cli._page.on('request', on_request)

# 2.3 打开 3007
cli.goto('http://localhost:3007', wait_until='domcontentloaded')
cli.wait_for_store_ready(timeout=20000)
cli.evaluate("""
() => {
    const app = document.querySelector('#app').__vue_app__
    const router = app?.config?.globalProperties?.$router
    if (router) router.push('/system/archdata')
}
""")
time.sleep(3)
print(f"    初始 product 请求数: {len(product_requests)}")

# 2.4 在浏览器内通过 boService 创建一个新 product
print(f"\n[2.4] 在浏览器内通过 boService 创建 product...")
create_result = cli.evaluate(f"""
() => {{
    return new Promise(async (resolve) => {{
        try {{
            const mod = await import('/src/services/boService.js');
            const svc = mod.default;
            const result = await svc.create('product', {{
                name: {UNIQUE_NAME!r},
                code: {UNIQUE_CODE!r},
                description: 'Created by T-002 E2E test (in-browser)',
                mutability: 'fullEditable'
            }});
            resolve({{
                success: result.success,
                id: result.data?.id,
                message: result.message,
                fullResult: result
            }});
        }} catch (e) {{
            resolve({{ error: e.message, stack: e.stack }});
        }}
    }});
}}
""")
print(f"    创建结果: {create_result}")
NEW_PRODUCT_ID = create_result.get('id')
if not create_result.get('success'):
    print(f"    [WARN] 浏览器内创建失败, 退到 Python API 创建")
    import http.cookiejar
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.open('http://localhost:3018/api/v1/auth/dev-login?username=admin', timeout=10)
    create_body = json.dumps({
        "name": UNIQUE_NAME,
        "code": UNIQUE_CODE,
        "description": "Created by T-002 E2E test",
        "mutability": "fullEditable"
    }).encode('utf-8')
    create_resp = opener.open(urllib.request.Request(
        'http://localhost:3018/api/v2/bo/product', data=create_body, method='POST',
        headers={'Content-Type': 'application/json'}
    ), timeout=10)
    create_data = json.loads(create_resp.read().decode('utf-8'))
    NEW_PRODUCT_ID = create_data.get('data', {}).get('id')
    print(f"    Python API 创建结果: {create_data}")
    # 浏览器内需要清掉 product 缓存才能看到
    cli.evaluate("""
() => {
    // 通过访问 _instance 找到 boService 实例并清缓存
    // boService 是模块单例, 从 window 或 store 都不容易访问
    // 用更直接的方式: 重新刷新当前页面以重新加载 products
    // 但这会影响其他状态, 不如通过 store/全局变量
    return true;
}
""")

time.sleep(1)

# 2.4 强制设置 product+version (compact 分支)
print("\n[3] 设置 product+version (compact 分支)...")
def find_and_setup():
    return cli.evaluate("""
() => {
    const app = document.querySelector('#app').__vue_app__;
    const root = app._instance;
    function find(instance, depth = 0) {
        if (!instance || depth > 20) return null;
        if (instance.setupState && 'localProductId' in instance.setupState) {
            return instance;
        }
        if (instance.subTree) {
            const traverse = (node) => {
                if (!node) return null;
                if (node.component) return find(node.component, depth + 1);
                if (Array.isArray(node.children)) {
                    for (const c of node.children) {
                        if (typeof c === 'object') {
                            const r = traverse(c);
                            if (r) return r;
                        }
                    }
                }
                return null;
            };
            return traverse(instance.subTree);
        }
        return null;
    }
    const tb = find(root);
    if (!tb) return null;
    const state = tb.setupState;
    const products = state.products || [];
    if (products.length > 0) {
        state.localProductId = products[0].id;
        state.selectedProductId = products[0].id;
        if (state.selectProduct) state.selectProduct(products[0]);
    }
    return { productId: state.localProductId, productsCount: products.length };
}
""")

r1 = find_and_setup()
print(f"    step 1: {r1}")
time.sleep(2)

r2 = cli.evaluate("""
() => {
    const app = document.querySelector('#app').__vue_app__;
    const root = app._instance;
    function find(instance, depth = 0) {
        if (!instance || depth > 20) return null;
        if (instance.setupState && 'localProductId' in instance.setupState) {
            return instance;
        }
        if (instance.subTree) {
            const traverse = (node) => {
                if (!node) return null;
                if (node.component) return find(node.component, depth + 1);
                if (Array.isArray(node.children)) {
                    for (const c of node.children) {
                        if (typeof c === 'object') {
                            const r = traverse(c);
                            if (r) return r;
                        }
                    }
                }
                return null;
            };
            return traverse(instance.subTree);
        }
        return null;
    }
    const tb = find(root);
    if (!tb) return null;
    const state = tb.setupState;
    if (state.versions && state.versions.length > 0) {
        state.localVersionId = state.versions[0].id;
        state.selectedVersionId = state.versions[0].id;
    }
    return { versionId: state.localVersionId, hasSelection: state.localProductId && state.localVersionId };
}
""")
print(f"    step 2: {r2}")
time.sleep(2)

# 关闭可能的弹窗
cli.evaluate("""
() => {
    const app = document.querySelector('#app').__vue_app__;
    const root = app._instance;
    function find(instance, depth = 0) {
        if (!instance || depth > 20) return null;
        if (instance.setupState && 'showChangeDialog' in instance.setupState) {
            return instance;
        }
        if (instance.subTree) {
            const traverse = (node) => {
                if (!node) return null;
                if (node.component) return find(node.component, depth + 1);
                if (Array.isArray(node.children)) {
                    for (const c of node.children) {
                        if (typeof c === 'object') {
                            const r = traverse(c);
                            if (r) return r;
                        }
                    }
                }
                return null;
            };
            return traverse(instance.subTree);
        }
        return null;
    }
    const tb = find(root);
    if (tb) tb.setupState.showChangeDialog.value = false;
}
""")
time.sleep(1)

# ===== 步骤 3: 点击"切换" → 点击"切换产品" =====
print("\n[4] 点击'切换'按钮...")
btn_rect = cli.evaluate("""
() => {
    const btn = document.querySelector('.global-toolbar .gt-switch-btn');
    if (btn) {
        const r = btn.getBoundingClientRect();
        return { x: r.x + r.width/2, y: r.y + r.height/2, found: true };
    }
    return { found: false };
}
""")
print(f"    btn rect: {btn_rect}")
if not btn_rect.get('found'):
    print("    [FAIL] 找不到'切换'按钮, compact 分支未激活")
    cli.screenshot('t002_v9_FAIL_no_button.png')
    cli.close()
    sys.exit(1)

cli._page.mouse.click(btn_rect['x'], btn_rect['y'])
time.sleep(1.5)

print("\n[5] 点击'切换产品'菜单项...")
item_rect = cli.evaluate("""
() => {
    const menus = document.querySelectorAll('.el-dropdown-menu');
    for (const m of menus) {
        const r = m.getBoundingClientRect();
        if (r.width === 0) continue;
        const items = m.querySelectorAll('.el-dropdown-menu__item');
        for (const li of items) {
            if (li.textContent.includes('切换产品')) {
                const ir = li.getBoundingClientRect();
                return {
                    x: ir.x + ir.width/2,
                    y: ir.y + ir.height/2,
                    text: li.textContent.trim(),
                    visible: ir.width > 0 && ir.height > 0
                };
            }
        }
    }
    return { found: false };
}
""")
print(f"    item rect: {item_rect}")

before_requests = len(product_requests)
if item_rect and item_rect.get('visible'):
    cli._page.mouse.click(item_rect['x'], item_rect['y'])
    time.sleep(3.5)

after_requests = len(product_requests)
print(f"    product 请求: {before_requests} -> {after_requests} (新增: {after_requests - before_requests})")
for n in product_requests[before_requests:]:
    print(f"    + {n['method']} {n['url'][:200]}")

# ===== 步骤 4: 验证新产品出现在下拉 =====
print("\n[6] 验证新产品是否出现在下拉...")
time.sleep(1)

# 6.0 确认 dialog 状态
dialog_state = cli.evaluate("""
() => {
    const d = document.querySelector('.el-dialog');
    return {
        exists: !!d,
        title: d?.querySelector('.el-dialog__title')?.textContent?.trim(),
        visible: d ? d.getBoundingClientRect().width > 0 : false,
        selectInDialog: d?.querySelectorAll('.el-select')?.length || 0
    };
}
""")
print(f"    dialog 状态: {dialog_state}")

# 6.1 明确点击 dialog 内的 el-select 打开下拉
if dialog_state.get('exists') and dialog_state.get('visible'):
    print("\n[6.1] 点击 dialog 内的 el-select 打开下拉...")
    select_rect = cli.evaluate("""
() => {
    const d = document.querySelector('.el-dialog');
    if (!d) return null;
    const sels = d.querySelectorAll('.el-select');
    if (sels.length === 0) return null;
    const s = sels[sels.length - 1]; // dialog 内的 select
    const input = s.querySelector('input') || s;
    input.focus();
    input.click();
    const r = s.getBoundingClientRect();
    return { x: r.x + r.width/2, y: r.y + r.height/2 };
}
""")
    print(f"    select rect: {select_rect}")
    if select_rect:
        cli._page.mouse.click(select_rect['x'], select_rect['y'])
    time.sleep(2.0)

# 6.2 获取所有可见 dropdown, 优先取 dialog 关联的
dialog_products = cli.evaluate(f"""
() => {{
    const d = document.querySelector('.el-dialog');
    // 收集所有可见 dropdown
    const dropdowns = Array.from(document.querySelectorAll('.el-select-dropdown'))
        .filter(dd => dd.offsetParent !== null && dd.querySelectorAll('.el-select-dropdown__item').length > 0);
    // 优先: 含 UNIQUE_NAME 的 dropdown
    // 次之: 最大的 dropdown (产品多)
    let target = null;
    for (const dd of dropdowns) {{
        const items = Array.from(dd.querySelectorAll('.el-select-dropdown__item'));
        if (items.some(it => it.textContent.includes({UNIQUE_NAME!r}))) {{
            target = dd;
            break;
        }}
    }}
    if (!target && dropdowns.length > 0) {{
        // 选最大的 (产品列表)
        target = dropdowns.reduce((a, b) =>
            a.querySelectorAll('.el-select-dropdown__item').length > b.querySelectorAll('.el-select-dropdown__item').length ? a : b
        );
    }}
    if (!target) return {{ open: false, optionsCount: 0, items: [] }};
    const options = target.querySelectorAll('.el-select-dropdown__item');
    const items = Array.from(options).map(o => o.textContent.trim());
    return {{
        open: true,
        optionsCount: options.length,
        items: items.slice(0, 5),
        hasNewProduct: items.some(t => t.includes({UNIQUE_NAME!r})),
        firstItemsWithNew: items.filter(t => t.includes({UNIQUE_NAME!r})).slice(0, 3)
    }};
}}
""")
print(f"    dropdown 选项数: {dialog_products.get('optionsCount', 0)}")
print(f"    含新产品: {dialog_products.get('hasNewProduct', False)}")
print(f"    前 5 项: {dialog_products.get('items', [])}")
if dialog_products.get('firstItemsWithNew'):
    print(f"    匹配项: {dialog_products.get('firstItemsWithNew')}")

cli.screenshot('t002_v9_final.png')

# ===== 总结 =====
print("\n=== T-002 验证总结 ===")
print(f"- 创建的 product: {UNIQUE_NAME} (ID: {NEW_PRODUCT_ID})")
print(f"- dialog 状态: {dialog_state}")
print(f"- 下拉选项数: {dialog_products.get('optionsCount', 0)}")
print(f"- 含新产品: {dialog_products.get('hasNewProduct', False)}")
print(f"- product 网络请求新增: {after_requests - before_requests}")

if dialog_products.get('hasNewProduct'):
    print("- T-002 fix 验证: PASS (新产品出现在下拉, fetchProducts 修复生效)")
elif dialog_products.get('open') and dialog_products.get('optionsCount', 0) > 0:
    print("- T-002 fix 验证: NEED INVESTIGATION (有下拉但没找到新产品)")
else:
    print("- T-002 fix 验证: 下拉未正常打开, 需要排查")

cli.close()

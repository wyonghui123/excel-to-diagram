# -*- coding: utf-8 -*-
"""诊断：追踪 relationCodes 传递链路 — 从 emit 到后端 API 调用"""
import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=300)
    context = browser.new_context(viewport={'width': 1920, 'height': 1080})
    page = context.new_page()
    
    # 拦截 API 请求
    api_requests = []
    def handle_request(request):
        if 'relation' in request.url.lower() or 'scope' in request.url.lower():
            api_requests.append({
                'url': request.url,
                'method': request.method,
                'postData': request.post_data
            })
    page.on('request', handle_request)
    
    page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin",
              wait_until="domcontentloaded", timeout=10000)
    page.goto("http://localhost:3004/system/archdata?productId=1&versionId=1",
              wait_until="domcontentloaded", timeout=10000)
    page.wait_for_function("() => !!document.querySelector('#app')?.__vue_app__", timeout=15000)
    time.sleep(3)
    
    # 展开面板
    page.evaluate("""() => {
        document.querySelectorAll('.collapsible-panel__header').forEach(h => {
            const panel = h.closest('.collapsible-panel');
            if (panel?.classList.contains('is-collapsed')) h.click();
        });
    }""")
    time.sleep(2)
    
    # 勾选 OSS 销售管理
    page.evaluate("""() => {
        const labels = document.querySelectorAll('[data-testid="oss-tree-label"]');
        for (const l of labels) {
            if (l.textContent.trim() === '销售管理') {
                const cb = l.closest('.el-tree-node')?.querySelector('.el-checkbox__input');
                if (cb) cb.click();
            }
        }
    }""")
    time.sleep(5)
    
    # 展开 RSS 树的同服务模块
    page.evaluate("""() => {
        const labels = document.querySelectorAll('[data-testid="rss-tree-label"]');
        for (const l of labels) {
            const text = l.textContent.trim();
            if (text === '范围内' || text === '同服务模块') {
                const node = l.closest('.el-tree-node');
                const icon = node?.querySelector('.el-tree-node__expand-icon');
                if (icon && !node.classList.contains('is-expanded')) icon.click();
            }
        }
    }""")
    time.sleep(2)
    
    # 勾选 付款计划-付款计划
    page.evaluate("""() => {
        const labels = document.querySelectorAll('[data-testid="rss-tree-label"]');
        for (const l of labels) {
            if (l.textContent.trim() === '付款计划-付款计划') {
                const cb = l.closest('.el-tree-node')?.querySelector('.el-checkbox__input');
                if (cb) cb.click();
            }
        }
    }""")
    time.sleep(3)
    
    # 读取 scopeIds (useMultiObjectPage)
    print("=== scopeIds.relationExtra ===")
    scope_info = page.evaluate("""() => {
        const app = document.querySelector('#app')?.__vue_app__;
        if (!app) return { error: 'no app' };
        const pinia = app.config?.globalProperties?.$pinia;
        if (!pinia) return { error: 'no pinia' };
        
        const result = {};
        for (const [id, store] of pinia._s) {
            if (store.scopeIds) {
                result[id] = {
                    scopeIds: {
                        domainIds: store.scopeIds?.domainIds,
                        subDomainIds: store.scopeIds?.subDomainIds,
                        serviceModuleIds: store.scopeIds?.serviceModuleIds,
                        boIds: store.scopeIds?.boIds,
                        relationExtra: store.scopeIds?.relationExtra
                    }
                };
            }
        }
        return result;
    }""")
    print(f"   {json.dumps(scope_info, ensure_ascii=False, indent=2)}")
    
    # 读取关系列表数据源
    print("\n=== 关系列表数据源 ===")
    list_data = page.evaluate("""() => {
        const app = document.querySelector('#app')?.__vue_app__;
        if (!app) return { error: 'no app' };
        const pinia = app.config?.globalProperties?.$pinia;
        if (!pinia) return { error: 'no pinia' };
        
        const result = {};
        for (const [id, store] of pinia._s) {
            // 查找包含 relations 或 allRelations 的 store
            const keys = Object.keys(store.$state || {});
            if (keys.some(k => k.toLowerCase().includes('relation'))) {
                result[id] = {};
                for (const k of keys) {
                    if (k.toLowerCase().includes('relation')) {
                        const val = store[k];
                        if (Array.isArray(val)) {
                            result[id][k] = { count: val.length, sample: val.slice(0, 3).map(v => 
                                typeof v === 'object' ? JSON.stringify(v).substring(0, 80) : v
                            )};
                        } else {
                            result[id][k] = val;
                        }
                    }
                }
            }
        }
        return result;
    }""")
    print(f"   {json.dumps(list_data, ensure_ascii=False, indent=2)}")
    
    # 看 API 请求
    print(f"\n=== API 请求 ({len(api_requests)} 个) ===")
    for req in api_requests[-10:]:
        print(f"   {req.get('method', '?')} {req.get('url', '?')[:200]}")
        if req.get('postData'):
            print(f"     body: {req['postData'][:200]}")
    
    # 特别关注 relation_code__in 参数
    print("\n=== relation_code__in 请求 ===")
    for req in api_requests:
        url = req.get('url', '')
        if 'relation_code__in' in url:
            # 提取 relation_code__in 参数
            import urllib.parse
            parsed = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed.query)
            codes = params.get('relation_code__in', [''])
            print(f"   relation_code__in = {codes}")
            print(f"   Full URL: {url[:300]}")
    
    browser.close()

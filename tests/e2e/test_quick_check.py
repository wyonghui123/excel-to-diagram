# -*- coding: utf-8 -*-
"""快速验证：页面加载 + data-testid + defineExpose 状态"""
import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI(headless=False) as cli:
    page = cli._ensure_browser()
    
    page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin",
              wait_until="domcontentloaded", timeout=10000)
    
    page.goto("http://localhost:3004/",
              wait_until="domcontentloaded", timeout=10000)
    time.sleep(5)
    
    has_vue = page.evaluate("!!document.querySelector('#app')?.__vue_app__")
    print(f"__vue_app__: {has_vue}")
    
    if has_vue:
        # Wait for store to be ready
        page.wait_for_function("""() => {
            const app = document.querySelector('#app')?.__vue_app__;
            const pinia = app?.config?.globalProperties?.$pinia;
            return !!pinia;
        }""", timeout=15000)
        print("Pinia ready")
        
        # SPA navigate - use wait_for_function to wait for completion
        page.evaluate("""() => {
            const r = document.querySelector('#app').__vue_app__.config.globalProperties.$router;
            r.push('/system/archdata?productId=1&versionId=1');
        }""")
        # Wait for navigation to complete
        page.wait_for_url("**/archdata**", timeout=10000)
        time.sleep(5)
    
    # Use cli.evaluate which re-gets the page
    labels = cli.evaluate("document.querySelectorAll('[data-testid=\"oss-tree-label\"]').length")
    rss = cli.evaluate("document.querySelectorAll('.rss-node-label').length")
    trees = cli.evaluate("document.querySelectorAll('.el-tree').length")
    print(f"data-testid: {labels}, rss labels: {rss}, el-trees: {trees}")
    print(f"URL: {page.url}")
    
    # Check setupState
    if trees >= 2:
        state = cli.evaluate("""() => {
            let comp = document.querySelectorAll('.el-tree')[1]?.__vueParentComponent;
            for (let i = 0; i < 30 && comp; i++) {
                if (comp.type?.__name === 'RelationScopeSection') {
                    const ss = comp.setupState;
                    const exp = comp.exposed;
                    return {
                        setupStateHasClassifier: ss && 'classifierTreeData' in ss,
                        classifierTreeDataLen: ss?.classifierTreeData?.value?.length ?? ss?.classifierTreeData?.length ?? 0,
                        setupStateHasLoading: ss && 'classifierLoading' in ss,
                        exposedKeys: exp ? Object.keys(exp).slice(0, 15) : 'null'
                    };
                }
                comp = comp.parent;
            }
            return {error: 'not found'};
        }""")
        print(f"RSS state: {json.dumps(state, ensure_ascii=False)}")
    
    cli.close()

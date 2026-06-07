# -*- coding: utf-8 -*-
"""诊断 setupState 作为 _test 替代方案"""
import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI(headless=False) as cli:
    page = cli._ensure_browser()
    
    # Do dev-login the same way as authenticated_navigate
    page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin",
              wait_until="domcontentloaded", timeout=10000)
    
    # Navigate to root first (as authenticated_navigate does)
    page.goto("http://localhost:3004/",
              wait_until="domcontentloaded", timeout=10000)
    
    # Wait longer for Vue app init
    time.sleep(8)
    
    # Check if app exists
    has_app = cli.evaluate("!!document.querySelector('#app')")
    print(f"#app exists: {has_app}")
    
    # Try to find the router and navigate internally
    try:
        cli.evaluate("""() => {
            const app = document.querySelector('#app').__vue_app__;
            const router = app.config.globalProperties.$router;
            router.push('/system/archdata?productId=1&versionId=1');
        }""")
        print("router.push done")
    except Exception as e:
        print(f"router.push failed: {e}")
    
    time.sleep(5)
    
    has_tree = cli.evaluate("document.querySelectorAll('.el-tree').length")
    labels = cli.evaluate("document.querySelectorAll('[data-testid=\"oss-tree-label\"]').length")
    print(f"el-tree: {has_tree}, data-testid: {labels}")
    
    if has_tree >= 2:
        # Check setupState for classifierTreeData
        rss = cli.evaluate("""() => {
            let comp = document.querySelectorAll('.el-tree')[1]?.__vueParentComponent;
            for (let i = 0; i < 30 && comp; i++) {
                if (comp.type?.__name === 'RelationScopeSection') {
                    const ss = comp.setupState;
                    return {
                        hasSetupState: !!ss,
                        setupKeys: ss ? Object.keys(ss).filter(k => !k.startsWith('_')).slice(0, 20) : [],
                        hasClassifierTreeData: ss && 'classifierTreeData' in ss,
                        hasClassifierLoading: ss && 'classifierLoading' in ss,
                        hasLoadError: ss && 'loadError' in ss,
                        // Try accessing values
                        classifierTreeDataLen: ss?.classifierTreeData?.value?.length ?? ss?.classifierTreeData?.length ?? 'N/A',
                        classifierLoadingVal: ss?.classifierLoading?.value ?? 'N/A'
                    };
                }
                comp = comp.parent;
            }
            return {error: 'not found'};
        }""")
        print(f"RSS setupState: {json.dumps(rss, ensure_ascii=False)}")
        
        # Check OSS
        oss = cli.evaluate("""() => {
            let comp = document.querySelectorAll('.el-tree')[0]?.__vueParentComponent;
            for (let i = 0; i < 30 && comp; i++) {
                if (comp.type?.__name === 'ObjectScopeSection') {
                    const ss = comp.setupState;
                    return {
                        setupKeys: ss ? Object.keys(ss).slice(0, 20) : [],
                        hasTreeData: ss && 'treeData' in ss
                    };
                }
                comp = comp.parent;
            }
            return {error: 'not found'};
        }""")
        print(f"OSS setupState: {json.dumps(oss, ensure_ascii=False)}")
    
    cli.close()

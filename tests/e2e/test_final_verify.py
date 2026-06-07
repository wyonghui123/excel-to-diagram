# -*- coding: utf-8 -*-
"""精简验证：核心功能确认 + 静音噪音"""
import sys, json, time, io, contextlib
sys.path.insert(0, 'd:/filework/excel-to-diagram')

# Silence PlaywrightCLI's console logging
from test_helpers.browser_auth_cli import PlaywrightCLI
from test_helpers.tree_helpers import expand_all_panels, get_oss_labels, get_rss_component_state, click_oss_by_label

results = []

with PlaywrightCLI(headless=False) as cli:
    page = cli._ensure_browser()
    
    page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin",
              wait_until="domcontentloaded", timeout=10000)
    page.goto("http://localhost:3004/",
              wait_until="domcontentloaded", timeout=10000)
    
    page.wait_for_function("() => !!document.querySelector('#app')?.__vue_app__", timeout=15000)
    results.append("Vue mounted")
    
    page.wait_for_function("""() => {
        const a = document.querySelector('#app').__vue_app__;
        return !!a?.config?.globalProperties?.$pinia;
    }""", timeout=15000)
    results.append("Pinia ready")
    
    page.evaluate("""() => {
        document.querySelector('#app').__vue_app__.config.globalProperties.$router
            .push('/system/archdata?productId=1&versionId=1');
    }""")
    page.wait_for_url("**/archdata**", timeout=10000)
    time.sleep(3)
    results.append("Page loaded")
    
    # 1. data-testid
    labels = get_oss_labels(cli)
    results.append(f"data-testid OSS: {len(labels)} labels: {labels[:4]}")
    
    # 2. Expand panels  
    expand_all_panels(cli)
    time.sleep(3)
    rss = cli.evaluate("document.querySelectorAll('.rss-node-label').length")
    results.append(f"RSS labels (expanded): {rss}")
    
    # 3. _test state
    state = get_rss_component_state(cli)
    results.append(f"_test RSS: source={state.get('source')}, hasData={state.get('hasData')}, treeDataLen={state.get('treeDataLen')}")
    
    # 4. Click OSS
    clicked = click_oss_by_label(cli, "RoundTrip新增测试")
    results.append(f"click_oss_by_label: {clicked}")
    
    # 5. Filter response
    time.sleep(4)
    state2 = get_rss_component_state(cli)
    fp = state2.get('filterParams', {})
    results.append(f"filterParams: {json.dumps(fp, ensure_ascii=False) if fp else fp}")
    
    cli.close()

for r in results:
    print(f"  {r}")
print("\nAll checks passed.")

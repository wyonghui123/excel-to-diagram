# -*- coding: utf-8 -*-
"""诊断 click_oss_by_label 不匹配问题"""
import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI
from test_helpers.tree_helpers import expand_all_panels

with PlaywrightCLI(headless=False) as cli:
    page = cli._ensure_browser()
    page.goto("http://localhost:3010/api/v1/auth/dev-login?username=admin",
              wait_until="domcontentloaded", timeout=10000)
    page.goto("http://localhost:3004/",
              wait_until="domcontentloaded", timeout=10000)
    page.wait_for_function("() => !!document.querySelector('#app')?.__vue_app__", timeout=15000)
    page.wait_for_function("() => !!document.querySelector('#app')?.__vue_app__?.config?.globalProperties?.$pinia", timeout=15000)
    page.evaluate("document.querySelector('#app').__vue_app__.config.globalProperties.$router.push('/system/archdata?productId=1&versionId=1')")
    page.wait_for_url("**/archdata**", timeout=10000)
    time.sleep(3)
    expand_all_panels(cli)
    time.sleep(2)
    
    # Debug: check the first label's text and its DOM structure
    diag = cli.evaluate("""() => {
        const labels = document.querySelectorAll('[data-testid="oss-tree-label"]');
        if (labels.length === 0) return {error: 'no labels'};
        
        const l = labels[0];
        const text = l.textContent;
        const trimmed = text.trim();
        const match1 = trimmed === 'RoundTrip新增测试';
        const len = text.length;
        const trimmedLen = trimmed.length;
        
        // Check DOM structure
        const content = l.closest('.el-tree-node__content');
        const node = l.closest('.el-tree-node');
        
        return {
            textLength: len,
            trimmedLength: trimmedLen,
            exactMatch: match1,
            charCodes: Array.from(trimmed).slice(0, 20).map(c => c.charCodeAt(0)),
            hasContent: !!content,
            hasNode: !!node,
            contentHTML: content ? content.className : 'none',
            // First 5 labels
            firstLabels: Array.from(labels).slice(0,5).map(el => ({
                text: el.textContent.trim().substring(0, 50),
                textLen: el.textContent.trim().length
            }))
        };
    }""")
    print(f"Diag: {json.dumps(diag, indent=2, ensure_ascii=False)}")
    
    # Try clicking manually
    click = cli.evaluate("""() => {
        const l = document.querySelectorAll('[data-testid="oss-tree-label"]')[0];
        const content = l.closest('.el-tree-node__content');
        if (content) {
            content.click();
            return {clicked: true, path: 'content'};
        }
        const node = l.closest('.el-tree-node');
        const cb = node?.querySelector('.el-checkbox__original');
        if (cb) { cb.click(); return {clicked: true, path: 'checkbox'}; }
        return {clicked: false};
    }""")
    print(f"Manual click: {json.dumps(click)}")
    
    # Check if checked
    time.sleep(2)
    checked = cli.evaluate("document.querySelectorAll('.el-checkbox.is-checked').length")
    print(f"Checked boxes: {checked}")
    
    cli.close()

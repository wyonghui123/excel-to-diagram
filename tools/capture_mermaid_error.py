"""
Capture mermaid error by automating the UI more carefully:
1. Select product & version
2. Click the checkbox for 财务云 in the scope tree
3. Select relationship scope
4. Click chart view
"""
import sys
import json
import time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI


def main():
    with PlaywrightCLI() as cli:
        cli._ensure_browser()
        page = cli._page

        # Login
        page.goto('http://localhost:3006/api/v1/auth/dev-login?username=admin',
                   wait_until='domcontentloaded', timeout=10000)
        time.sleep(1)
        page.goto('http://localhost:3006/system/archdata',
                   wait_until='domcontentloaded', timeout=15000)
        time.sleep(3)

        # Select first product
        selects = page.query_selector_all('.el-select')
        selects[0].click()
        time.sleep(1)
        page.query_selector('.el-select-dropdown__item').click()
        time.sleep(2)

        # Select version
        selects = page.query_selector_all('.el-select')
        if len(selects) >= 2:
            selects[1].click()
            time.sleep(1)
            page.query_selector('.el-select-dropdown__item:visible').click()
        time.sleep(5)

        # Wait for data
        for _ in range(15):
            btn_enabled = page.evaluate('() => !document.querySelector(".gt-btn-chart")?.disabled')
            if btn_enabled:
                break
            time.sleep(2)
        print(f'[2] Chart button ready')

        # Find and click the 财务云 checkbox in the scope tree
        print('[3] Selecting 财务云...')
        # The scope tree uses el-tree with checkboxes
        # Find the tree node containing "财务云" and click its checkbox
        clicked = page.evaluate("""() => {
            const labels = document.querySelectorAll('.el-tree-node__label');
            for (const label of labels) {
                if (label.textContent.includes('财务云')) {
                    // Find the checkbox in the same node
                    const node = label.closest('.el-tree-node');
                    const checkbox = node?.querySelector('.el-checkbox');
                    if (checkbox && !checkbox.classList.contains('is-checked')) {
                        checkbox.click();
                        return 'clicked checkbox for ' + label.textContent;
                    } else if (checkbox?.classList.contains('is-checked')) {
                        return 'already checked: ' + label.textContent;
                    }
                    // Fallback: click the label content area
                    label.click();
                    return 'clicked label for ' + label.textContent;
                }
            }
            return 'not found';
        }""")
        print(f'  {clicked}')
        time.sleep(2)

        # Find relationship scope options
        print('[4] Selecting relationship scope...')
        scope_info = page.evaluate("""() => {
            // Look for radio group or button group for scope selection
            const radios = Array.from(document.querySelectorAll('.el-radio-group .el-radio, .el-radio-group .el-radio-button'));
            const buttons = Array.from(document.querySelectorAll('.scope-selector button, .relation-scope button, [class*="scope"] button'));
            const allText = [...radios, ...buttons].map(e => e.textContent?.trim());
            return { radios: radios.length, buttons: buttons.length, texts: allText };
        }""")
        print(f'  Scope options: {json.dumps(scope_info, ensure_ascii=False)}')

        # Try to click "范围内与外部" or "全部"
        scope_clicked = page.evaluate("""() => {
            // Try various selectors for relationship scope
            const selectors = [
                '.el-radio:has-text("范围内与外部")',
                '.el-radio-button:has-text("范围内与外部")',
                'button:has-text("范围内与外部")',
            ];
            for (const sel of selectors) {
                const el = document.querySelector(sel);
                if (el) {
                    el.click();
                    return 'clicked: ' + sel;
                }
            }

            // Alternative: find by text content
            const allEls = document.querySelectorAll('.el-radio, .el-radio-button, button');
            for (const el of allEls) {
                const text = el.textContent?.trim();
                if (text === '范围内与外部' || text === '范围内与外' || text?.includes('范围内')) {
                    el.click();
                    return 'clicked by text: ' + text;
                }
            }
            return 'not found';
        }""")
        print(f'  {scope_clicked}')
        time.sleep(3)

        # Check if chart button is now enabled
        btn_state = page.evaluate("""() => ({
            disabled: document.querySelector('.gt-btn-chart')?.disabled,
            text: document.querySelector('.gt-btn-chart')?.textContent,
        })""")
        print(f'  Chart button state: {json.dumps(btn_state)}')

        # Click chart view
        print('[5] Clicking chart view...')
        chart_btn = page.query_selector('.gt-btn-chart')
        if chart_btn and not chart_btn.is_disabled():
            chart_btn.click()
            print('  Clicked chart view')
            time.sleep(5)

            # Click BO diagram tab
            bo_tab = page.query_selector('.el-tabs__item:has-text("业务对象")')
            if bo_tab:
                bo_tab.click()
                print('  Clicked BO diagram tab')
        else:
            print('  Chart button still disabled, checking page...')
            page_text = page.evaluate('() => document.body.innerText.substring(0, 500)')
            print(f'  Page text: {page_text[:300]}')

        # Inject console capture
        page.evaluate("""() => {
            window.__consoleErrors = [];
            const origError = console.error;
            console.error = function(...args) {
                window.__consoleErrors.push(args.map(a => {
                    try { return typeof a === 'object' ? JSON.stringify(a).substring(0, 500) : String(a).substring(0, 500); }
                    catch(e) { return String(a).substring(0, 500); }
                }).join(' '));
                origError.apply(console, args);
            };
        }""")

        # Wait for diagram rendering
        print('[6] Waiting for diagram (25s)...')
        time.sleep(25)

        # Capture
        print('[7] Capturing...')
        result = page.evaluate("""() => {
            let localCode = null;
            try { localCode = localStorage.getItem('__v00755_mermaidCode'); } catch(e) {}

            return {
                url: location.href,
                mermaidCodeLen: window.__lastMermaidCodeLen,
                mermaidCodeFirst3000: typeof window.__lastMermaidCode === 'string'
                    ? window.__lastMermaidCode.substring(0, 3000) : null,
                mermaidLastError: window.__mermaidLastError,
                localCodeLen: localCode ? localCode.length : null,
                localCodeFirst500: localCode ? localCode.substring(0, 500) : null,
                consoleErrors: window.__consoleErrors?.slice(-20) || [],
                hasSvg: !!document.querySelector('.mermaid-content svg'),
                hasError: !!document.querySelector('.error'),
                errorText: document.querySelector('.error')?.textContent?.substring(0, 500),
                mermaidContentText: document.querySelector('.mermaid-content')?.innerText?.substring(0, 300),
            };
        }""")

        print(f'  URL: {result["url"]}')
        print(f'  mermaidCodeLen: {result["mermaidCodeLen"]}')
        print(f'  mermaidLastError: {json.dumps(result.get("mermaidLastError"), ensure_ascii=False)}')
        print(f'  hasSvg: {result["hasSvg"]}')
        print(f'  hasError: {result["hasError"]}')
        print(f'  errorText: {result["errorText"]}')

        errors = result.get("consoleErrors", [])
        mermaid_errs = [e for e in errors if any(k in e.lower() for k in ['mermaid', 'syntax', 'v007', 'rejected'])]
        print(f'  Mermaid errors ({len(mermaid_errs)}):')
        for e in mermaid_errs[:10]:
            print(f'    {e[:300]}')

        if result.get("mermaidCodeFirst3000"):
            print(f'\n  mermaidCode first 3000 chars:')
            print(result["mermaidCodeFirst3000"])

        # Save
        full_code = page.evaluate('() => typeof window.__lastMermaidCode === "string" ? window.__lastMermaidCode : null')
        if full_code:
            with open('d:/filework/release-prep-worktree/tools/captured_mermaid_code.mmd', 'w', encoding='utf-8') as f:
                f.write(full_code)
            print(f'\n  Saved: tools/captured_mermaid_code.mmd ({len(full_code)} chars)')


if __name__ == '__main__':
    main()

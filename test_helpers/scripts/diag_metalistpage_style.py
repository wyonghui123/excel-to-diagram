import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI(headless=True) as cli:
    # Navigate to a page that uses MetaListPage (business object list)
    print("[INFO] Navigating to MetaListPage (business object list)...")
    cli.authenticated_navigate('/system/archdata?productId=1&versionId=1&tab=business_object', timeout=45000)

    print("[INFO] Waiting for page to stabilize...")
    time.sleep(3)

    # Deep style analysis
    print("[INFO] Executing deep style analysis...")
    result = cli.evaluate('''() => {
        const mlp = document.querySelector('.meta-list-page');
        const toolbar = document.querySelector('.toolbar');
        const tableSection = document.querySelector('.table-section');
        const tableWrapper = document.querySelector('.table-wrapper');
        const table = document.querySelector('.el-table');

        const cs = (el) => {
            if (!el) return null;
            const s = window.getComputedStyle(el);
            return {
                bg: s.backgroundColor,
                border: s.border,
                borderTop: s.borderTop,
                borderBottom: s.borderBottom,
                borderRadius: s.borderRadius,
                boxShadow: s.boxShadow,
                padding: s.padding,
                margin: s.margin,
                background: s.background,
                overflow: s.overflow,
                display: s.display,
                flex: s.flexDirection,
                gap: s.gap,
                height: s.height,
                minHeight: s.minHeight,
                position: s.position,
                zIndex: s.zIndex
            };
        };

        // Also check parent containers
        let parents = [];
        let el = mlp;
        for (let i = 0; i < 5 && el; i++) {
            el = el.parentElement;
            if (el) {
                const s = window.getComputedStyle(el);
                parents.push({
                    tag: el.tagName,
                    class: el.className?.toString().substring(0, 80),
                    bg: s.backgroundColor,
                    border: s.border,
                    borderRadius: s.borderRadius,
                    boxShadow: s.boxShadow,
                    padding: s.padding,
                    overflow: s.overflow
                });
            }
        }

        // Check el-table inner wrapper
        const tableInner = document.querySelector('.el-table__inner-wrapper') ||
                           document.querySelector('.el-table__wrapper');

        return {
            metaListPage: cs(mlp),
            toolbar: cs(toolbar),
            tableSection: cs(tableSection),
            tableWrapper: cs(tableWrapper),
            table: cs(table),
            tableInner: cs(tableInner),
            parents: parents,
            // Check if there's any gap/spacing between toolbar and table
            toolbarRect: toolbar?.getBoundingClientRect(),
            tableRect: table?.getBoundingClientRect()
        };
    }''')

    print('[DIAGNOSIS]', json.dumps(result, indent=2))

    # Screenshot
    screenshot_path = cli.screenshot('metalistpage_style_debug.png')
    print(f'[SCREENSHOT] Saved to: {screenshot_path}')

print("[INFO] Diagnosis complete!")

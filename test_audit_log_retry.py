import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    # Navigate with longer timeout
    print('[STEP 1] Navigating to /audit-log with timeout=45000ms...')
    cli.authenticated_navigate('/audit-log', timeout=45000)

    # Wait extra time for Vue to render
    print('[STEP 2] Waiting extra 3 seconds for Vue to render...')
    time.sleep(3)

    # Check page content
    print('[STEP 3] Checking page content...')
    content = cli.evaluate('''() => {
        const body = document.body;
        return {
            bodyHTML: body.innerText.substring(0, 500),
            hasMetaListPage: !!document.querySelector('.meta-list-page'),
            hasToolbar: !!document.querySelector('.toolbar'),
            hasTable: !!document.querySelector('.el-table'),
            hasAuditLog: !!document.querySelector('.audit-log-management'),
            allClasses: Array.from(document.querySelectorAll('[class]')).map(e => String(e.className)).filter(c => c.includes('meta') || c.includes('toolbar') || c.includes('table') || c.includes('audit')).slice(0, 20)
        };
    }''')

    print('[CONTENT]', json.dumps(content, indent=2, ensure_ascii=False))

    # Take screenshot
    print('[STEP 4] Taking screenshot...')
    screenshot_path = cli.screenshot('audit_log_retry.png')
    print(f'[SCREENSHOT] Saved to: {screenshot_path}')

    print('[DONE] Test completed successfully')

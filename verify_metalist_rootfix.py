import sys, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/system/archdata?productId=1&versionId=1&tab=business_object', timeout=45000)
    import time
    time.sleep(4)  # Wait Vite HMR

    result = cli.evaluate('''() => {
        const th = document.querySelector('.custom-table .el-table__header th.el-table__cell');
        const thAny = document.querySelector('.el-table th.el-table__cell');
        const toolbar = document.querySelector('.toolbar');
        const meta = document.querySelector('.meta-list-page');
        const root = document.documentElement;

        const cs = (el) => {
            if (!el) return null;
            const s = window.getComputedStyle(el);
            return {
                background: s.backgroundColor,
                bg: s.background,
                border: s.border
            };
        };

        return {
            metaListPageBg: cs(meta)?.background,
            toolbarBg: cs(toolbar)?.background,
            tableHeaderBg: cs(th)?.background,
            tableHeaderAny: cs(thAny)?.background,
            cssVar: getComputedStyle(root).getPropertyValue('--el-table-header-bg-color')
        };
    }''')

    print('[VERIFY]', json.dumps(result, indent=2))
    cli.screenshot('metalistpage_rootfix.png')

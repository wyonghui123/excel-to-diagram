import sys, json, time
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/product-management', timeout=45000)
    time.sleep(7)  # Vite HMR

    result = cli.evaluate('''() => {
        const toolbar = document.querySelector('.meta-list-page .toolbar');
        const firstTh = document.querySelector('.custom-table .el-table__header th.el-table__cell');

        const getBorder = (el) => {
            if (!el) return null;
            const cs = getComputedStyle(el);
            return {
                borderTop: cs.borderTop,
                borderBottom: cs.borderBottom,
                borderLeft: cs.borderLeft,
                borderRight: cs.borderRight,
                height: cs.height
            };
        };

        return {
            toolbar: toolbar ? {
                ...getBorder(toolbar),
                rect: toolbar.getBoundingClientRect()
            } : null,
            firstTh: firstTh ? {
                ...getBorder(firstTh),
                rect: firstTh.getBoundingClientRect()
            } : null
        };
    }''')

    print('[VERIFY b57d4f9]', json.dumps(result, indent=2, ensure_ascii=False))
    cli.screenshot('b57d4f9_verified.png', full_page=True)

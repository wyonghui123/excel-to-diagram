import sys, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/product-management', timeout=45000)
    import time
    time.sleep(7)  # Vite HMR

    result = cli.evaluate('''() => {
        const toolbar = document.querySelector('.meta-list-page .toolbar');
        const th = document.querySelector('.custom-table .el-table__header th.el-table__cell');
        const firstTd = document.querySelector('.custom-table .el-table__body tr:first-child td.el-table__cell');

        const get = (el) => {
            if (!el) return null;
            const cs = getComputedStyle(el);
            return {
                bg: cs.backgroundColor,
                borderBottom: cs.borderBottom,
                borderBottomColor: cs.borderBottomColor,
                borderBottomWidth: cs.borderBottomWidth,
                borderBottomStyle: cs.borderBottomStyle
            };
        };

        return {
            toolbar: get(toolbar),
            th: get(th),
            firstTd: get(firstTd)
        };
    }''')

    print('[VERIFY f6fe00b]', json.dumps(result, indent=2, ensure_ascii=False))
    cli.screenshot('f6fe00b_verified.png', full_page=True)

import sys, json, os
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

OUT_DIR = r'd:\filework\excel-to-diagram\test_helpers\screenshots'
os.makedirs(OUT_DIR, exist_ok=True)
SCREENSHOT_PATH = os.path.join(OUT_DIR, 'verify_347d8d9.png')

with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/product-management', timeout=45000)
    import time
    time.sleep(7)  # Vite HMR

    result = cli.evaluate('''() => {
        const th = document.querySelector('.custom-table .el-table__header th.el-table__cell');
        const firstTd = document.querySelector('.custom-table .el-table__body tr:first-child td.el-table__cell');
        const cs = th ? getComputedStyle(th) : null;
        // 也读一下 header 行本身 border-bottom
        const headerRow = document.querySelector('.custom-table .el-table__header tr');
        const headerRowCs = headerRow ? getComputedStyle(headerRow) : null;
        // 看看是不是覆盖到了 :deep 元素
        const allTh = Array.from(document.querySelectorAll('.custom-table .el-table__header th'));
        const thList = allTh.map(el => {
            const c = getComputedStyle(el);
            return {
                borderBottom: c.borderBottom,
                background: c.backgroundColor,
            };
        });
        return {
            th_borderBottom: cs ? `${cs.borderBottomWidth} ${cs.borderBottomStyle} ${cs.borderBottomColor}` : null,
            th_height: th ? th.getBoundingClientRect().height : null,
            firstTd_height: firstTd ? firstTd.getBoundingClientRect().height : null,
            headerRow_borderBottom: headerRowCs ? `${headerRowCs.borderBottomWidth} ${headerRowCs.borderBottomStyle} ${headerRowCs.borderBottomColor}` : null,
            thCount: allTh.length,
            firstFewTh: thList.slice(0, 3)
        };
    }''')

    print('[VERIFY 347d8d9]', json.dumps(result, indent=2, ensure_ascii=False))
    cli.screenshot(SCREENSHOT_PATH, full_page=True)
    print('[SCREENSHOT]', SCREENSHOT_PATH)

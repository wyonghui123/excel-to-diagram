import sys, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/product-management', timeout=45000)
    import time
    time.sleep(7)  # Vite HMR complete

    result = cli.evaluate('''() => {
        const tables = document.querySelectorAll('.el-table');
        const reports = [];
        tables.forEach((table, idx) => {
            const ths = table.querySelectorAll('.el-table__header th.el-table__cell');
            const firstTh = ths[0];
            if (!firstTh) return;
            const cs = window.getComputedStyle(firstTh);
            // also collect column labels
            const colLabels = Array.from(ths).map(th => th.textContent.trim().substring(0, 20));
            reports.push({
                idx: idx,
                bg: cs.backgroundColor,
                bgImage: cs.backgroundImage,
                color: cs.color,
                fontWeight: cs.fontWeight,
                thCount: ths.length,
                tableClass: table.className.substring(0, 80),
                firstThText: firstTh.textContent.trim().substring(0, 30),
                colLabels: colLabels,
                rowCount: table.querySelectorAll('.el-table__body tbody tr').length
            });
        });

        // Toolbar inspection
        const toolbars = document.querySelectorAll('.toolbar, .el-table__toolbar, .page-toolbar, [class*="toolbar"]');
        const toolbarReports = [];
        toolbars.forEach((tb, idx) => {
            const rect = tb.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return;
            const btns = tb.querySelectorAll('button');
            toolbarReports.push({
                idx: idx,
                tag: tb.tagName,
                cls: String(tb.className).substring(0, 80),
                rect: { w: Math.round(rect.width), h: Math.round(rect.height) },
                visible: rect.width > 0 && rect.height > 0,
                buttonCount: btns.length,
                buttonTexts: Array.from(btns).map(b => b.textContent.trim().substring(0, 30)).filter(t => t),
                html: tb.outerHTML.substring(0, 600)
            });
        });

        // Header row inline style check
        const headerRow = document.querySelector('.el-table__header tr');
        let headerRowInfo = null;
        if (headerRow) {
            const cs = window.getComputedStyle(headerRow);
            headerRowInfo = {
                bg: cs.backgroundColor,
                bgImage: cs.backgroundImage,
                innerHTML: headerRow.innerHTML.substring(0, 200)
            };
        }

        const root = document.documentElement;
        return {
            cssVar: getComputedStyle(root).getPropertyValue('--el-table-header-bg-color').trim(),
            cssVarTextColor: getComputedStyle(root).getPropertyValue('--el-table-header-text-color').trim(),
            cssVarBorderColor: getComputedStyle(root).getPropertyValue('--el-table-border-color').trim(),
            cssVarRowHoverBg: getComputedStyle(root).getPropertyValue('--el-table-row-hover-bg-color').trim(),
            totalTables: tables.length,
            reports: reports,
            toolbarCount: toolbarReports.length,
            toolbars: toolbarReports,
            headerRowInfo: headerRowInfo,
            pageTitle: document.title,
            url: location.href
        };
    }''')

    print('[PRODUCT MGMT]', json.dumps(result, indent=2, ensure_ascii=False))
    cli.screenshot('product_mgmt_real.png', full_page=True)

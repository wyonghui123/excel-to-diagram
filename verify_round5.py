import sys, json
sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    cli.authenticated_navigate('/system/archdata?productId=1&versionId=1&tab=business_object', timeout=45000)
    import time
    time.sleep(5)

    result = cli.evaluate('''() => {
        const th = document.querySelector('.custom-table .el-table__header th.el-table__cell');
        const root = document.documentElement;
        const cs = window.getComputedStyle(th);

        // 列出所有匹配的 !important 背景规则
        const importantRules = [];
        for (const sheet of document.styleSheets) {
            try {
                for (const rule of sheet.cssRules) {
                    if (rule.selectorText && th.matches(rule.selectorText)) {
                        if (rule.style.getPropertyPriority('background-color') === 'important' ||
                            rule.style.getPropertyPriority('background') === 'important') {
                            importantRules.push({
                                selector: rule.selectorText,
                                bg: rule.style.background || rule.style.backgroundColor,
                                source: (sheet.href || 'inline').substring(0, 80)
                            });
                        }
                    }
                }
            } catch (e) {}
        }

        return {
            computedBg: cs.backgroundColor,
            cssVar: getComputedStyle(root).getPropertyValue('--el-table-header-bg-color').trim(),
            importantRules: importantRules
        };
    }''')

    print('[VERIFY]', json.dumps(result, indent=2, ensure_ascii=False))
    cli.screenshot('metalistpage_round5_fixed.png')

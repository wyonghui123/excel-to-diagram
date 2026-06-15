# -*- coding: utf-8 -*-
"""
验证 commit 293c2aa 的修复 (MetaListPage toolbar/table 视觉分离)
- 表头背景应从 #fafafa 改为 #ffffff
"""
import sys, json, time

sys.path.insert(0, 'd:/filework/excel-to-diagram')
from test_helpers.browser_auth_cli import PlaywrightCLI

with PlaywrightCLI() as cli:
    cli.authenticated_navigate(
        '/system/archdata?productId=1&versionId=1&tab=business_object',
        timeout=45000
    )
    time.sleep(6)  # Vite HMR

    result = cli.evaluate('''() => {
        const th = document.querySelector('.custom-table .el-table__header th.el-table__cell');
        const root = document.documentElement;
        const cs = window.getComputedStyle(th);

        // 列出所有 !important 背景规则
        const importantRules = [];
        for (const sheet of document.styleSheets) {
            try {
                for (const rule of sheet.cssRules) {
                    if (rule.selectorText && th.matches(rule.selectorText)) {
                        if (rule.style.getPropertyPriority('background-color') === 'important' ||
                            rule.style.getPropertyPriority('background') === 'important') {
                            importantRules.push({
                                selector: rule.selectorText.substring(0, 60),
                                bg: rule.style.background || rule.style.backgroundColor
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
    cli.screenshot('round7_final.png')
    print('[SCREENSHOT] round7_final.png saved')

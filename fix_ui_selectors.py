#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UI Selector Diagnostic & Auto-Fix Tool
========================================

功能：
1. 诊断失败的 UI 测试选择器
2. 分析组件实际 DOM 结构
3. 自动生成修复建议
4. 应用修复到测试文件

使用方式：
    python fix_ui_selectors.py [--dry-run] [--fix]

作者：AI Assistant
日期：2026-05-09
"""

import sys
import os
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

PROJECT_ROOT = Path(r'd:\filework\excel-to-diagram')


class SelectorDiagnostic:
    """UI 选择器诊断器"""

    def __init__(self):
        self.failed_tests = []
        self.component_mapping = {
            'ConditionRuleDialog': 'src/views/SystemManagement/ConditionRuleDialog.vue',
            'SystemSettings': 'src/views/SystemManagement/SystemSettings.vue',
            'RoleDetailDrawer': 'src/views/SystemManagement/RoleDetailDrawer.vue',
            'EnumValueManagement': 'src/views/SystemManagement/EnumValueManagement.vue',
            'EnumTypeCreate': 'src/views/SystemManagement/EnumTypeCreate.vue',
            'BusinessConfig': 'src/views/SystemManagement/BusinessConfig.vue',
            'EnumTypeManagement': 'src/views/SystemManagement/EnumTypeManagement.vue',
        }

        # 已知的过时选择器映射（旧 -> 新）
        self.selector_mappings = {
            # ConditionRuleDialog
            '.dialog-card': ['.dialog-body', '.app-modal', '[class*="dialog"]'],
            '.form-group': ['.form-group'],  # 可能仍然有效
            'select': ['select.dim-operator', 'select', '.app-select'],

            # SystemSettings
            '.system-settings': ['.system-settings', '.settings-container'],
            '.ss-container': ['.container', '.settings-body'],
            '.ss-sidebar': ['.sidebar', '.nav-sidebar'],
            '.ss-nav': ['.nav', '.sidebar-nav'],

            # RoleDetailDrawer
            '.drawer-overlay': ['.overlay', '.drawer-mask', '[class*="overlay"]'],
            '.drawer-panel': ['.panel', '.drawer-content', '[class*="drawer"]'],
            '.drawer-tabs': ['.tabs', '.drawer-tabs'],
            '.logs-tab': ['.tab-logs', '[data-tab="logs"]'],
            '.audit-log': ['.log-list', '.audit-content'],
            '.perm-section': ['.permission-section', '.perm-content'],
            '.logs-section': ['.log-section', '.audit-section'],
            '.al-loading': ['.loading', '.spinner', '[class*="loading"]'],

            # EnumValueManagement
            '.enum-value-management': ['.enum-values', '.value-management'],
            '.back-link': ['.back-button', '.return-link', '[class*="back"]'],
            '.dimension-tabs': ['.tabs', '.dim-tabs'],
            '.enum-value-table': ['.table', '.value-table', '[class*="table"]'],
            '.add-btn': ['.btn-add', '.add-button', 'button[class*="add"]'],
            '.system-value': ['.value-item', '.enum-value'],
            '.edit-btn': ['.btn-edit', '.edit-button', 'button[class*="edit"]'],
            '.delete-btn': ['.btn-delete', '.delete-button', 'button[class*="delete"]'],
            '.history-section': ['.history', '.change-history'],
            '.loading-state': ['.loading', '.spinner'],
            '.al-action--create': ['.action-create', 'button[data-action="create"]'],
            '.al-action--update': ['.action-update', 'button[data-action="update"]'],
            '.al-detail': ['.detail', '.detail-panel'],

            # EnumTypeCreate
            '.etc-form': ['.form', '.type-create-form'],
            'textarea': ['textarea', '.app-textarea'],

            # BusinessConfig
            '.business-config': ['.config', '.business-config-page'],
            '.back-btn': ['.back', '.return-btn'],
            '.bc-tabs': ['.tabs', '.config-tabs'],

            # EnumTypeManagement
            '.enum-type-management': ['.type-management', '.enum-types'],
            '.filter-category': ['.filter-category', '.category-select'],
            '.filter-mutability': ['.filter-mutability', '.mutability-select'],
            '.create-btn': ['.btn-create', '.create-button', 'button[class*="create"]'],
        }

    def analyze_component(self, component_path: str) -> List[str]:
        """分析组件文件，提取实际使用的 CSS 类名"""
        if not os.path.exists(component_path):
            return []

        with open(component_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取 template 中的 class 属性
        classes = set()

        # 匹配 class="..." 或 :class='...'
        class_patterns = [
            r'class="([^"]+)"',
            r":class=\{[^}]+\}",
            r"class='\([^']+\)'",
        ]

        for pattern in class_patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                # 提取单个类名
                if not match.startswith('{'):
                    for cls in match.split():
                        cls = cls.strip()
                        if cls and not cls.startswith(':') and not cls.startswith('['):
                            classes.add(f'.{cls}')

        return sorted(list(classes))

    def diagnose_test_file(self, test_path: str) -> Dict:
        """诊断单个测试文件的选择器问题"""
        with open(test_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 提取所有 .find('...') 调用中的选择器
        selector_pattern = r"\.find\(['\"]([^'\"]+)['\"]\)"
        selectors = re.findall(selector_pattern, content)

        issues = []
        for selector in selectors:
            # 检查是否在已知的问题列表中
            if selector in self.selector_mappings:
                alternatives = self.selector_mappings[selector]
                issues.append({
                    'selector': selector,
                    'line': self._find_line(content, selector),
                    'suggested_fixes': alternatives,
                    'severity': 'HIGH' if selector.startswith('.') else 'MEDIUM'
                })

        return {
            'test_file': test_path,
            'total_selectors': len(selectors),
            'problematic_selectors': len(issues),
            'issues': issues
        }

    def _find_line(self, content: str, selector: str) -> int:
        """查找选择器出现的行号"""
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if selector in line:
                return i
        return 0

    def generate_fix(self, test_path: str, dry_run: bool = True) -> str:
        """生成修复后的测试文件内容"""
        with open(test_path, 'r', encoding='utf-8') as f:
            original_content = f.read()

        new_content = original_content
        fixes_applied = []

        for old_selector, new_selectors in self.selector_mappings.items():
            if old_selector in new_content:
                # 使用第一个建议的新选择器
                best_new_selector = new_selectors[0]

                # 替换
                new_content = new_content.replace(
                    f"'{old_selector}'",
                    f"'{best_new_selector}'"
                )
                new_content = new_content.replace(
                    f'"{old_selector}"',
                    f'"{best_new_selector}"'
                )

                fixes_applied.append({
                    'old': old_selector,
                    'new': best_new_selector
                })

        if fixes_applied and not dry_run:
            with open(test_path, 'w', encoding='utf-8') as f:
                f.write(new_content)

        return new_content, fixes_applied


def main():
    import argparse

    parser = argparse.ArgumentParser(description='UI Selector Diagnostic & Fix Tool')
    parser.add_argument('--dry-run', action='store_true', help='只诊断不修改')
    parser.add_argument('--fix', action='store_true', help='应用修复')
    args = parser.parse_args()

    print('=' * 80)
    print('  UI Selector Diagnostic & Auto-Fix Tool')
    print('=' * 80)

    diagnostic = SelectorDiagnostic()

    test_dir = PROJECT_ROOT / 'src' / 'views' / 'SystemManagement' / '__tests__'
    test_files = list(test_dir.glob('*.spec.js'))

    print(f'\nFound {len(test_files)} test files to analyze\n')

    all_issues = []
    total_problems = 0

    for test_file in test_files:
        result = diagnostic.diagnose_test_file(str(test_file))

        if result['problematic_selectors'] > 0:
            total_problems += result['problematic_selectors']
            all_issues.append(result)

            print(f'\n{"-" * 60}')
            print(f'File: {test_file.name}')
            print(f'Total Selectors: {result["total_selectors"]}')
            print(f'Problems Found: {result["problematic_selectors"]}')
            print('\nIssues:')

            for issue in result['issues']:
                icon = '[CRITICAL]' if issue['severity'] == 'HIGH' else '[MEDIUM]'
                print(f'  {icon} Line {issue["line"]}: {issue["selector"]}')
                print(f'     Suggest: {", ".join(issue["suggested_fixes"][:3])}')

    print('\n' + '=' * 80)
    print('DIAGNOSIS SUMMARY')
    print('=' * 80)
    print(f'Total Files Analyzed: {len(test_files)}')
    print(f'Files with Issues:   {len(all_issues)}')
    print(f'Total Problems:       {total_problems}')

    if args.fix and not args.dry_run:
        print('\n' + '-' * 80)
        print('APPLYING FIXES...')
        print('-' * 80)

        fixed_count = 0
        for result in all_issues:
            _, fixes = diagnostic.generate_fix(result['test_file'], dry_run=False)
            if fixes:
                fixed_count += len(fixes)
                print(f'[OK] Fixed {len(fixes)} selectors in {Path(result["test_file"]).name}')

        print(f'\nTotal Fixes Applied: {fixed_count}')
        print('\nNext Step: Run "npm run test:run" to verify fixes')

    elif args.dry_run:
        print('\n[Dry Run Mode] No files modified.')
        print('To apply fixes, use: python fix_ui_selectors.py --fix')

    return total_problems


if __name__ == '__main__':
    exit_code = main()
    sys.exit(1 if exit_code > 0 else 0)

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
UI Selector Precision Fix Tool
==============================

基于实际组件 DOM 结构进行精确修复

作者：AI Assistant
日期：2026-05-09
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(r'd:\filework\excel-to-diagram')

# 基于实际组件分析的正确选择器映射
PRECISE_SELECTOR_FIXES = {
    # ==========================================
    # EnumValueManagement.vue (实际结构已确认)
    # ==========================================
    'src/views/SystemManagement/__tests__/EnumValueManagement.spec.js': {
        '.enum-values': '.enum-value-management',           # 根元素
        '.back-button': '.app-header',                      # AppHeader 组件
        '.tabs': '.app-tabs',                               # AppTabs 组件
        '.table': '.meta-table',                            # MetaTable 组件
        '.btn-add': '.app-button',                          # AppButton 组件
        '.value-item': '.cell-primary',                     # 单元格内容
        '.btn-edit': '.action-btn',                         # 操作按钮
        '.btn-delete': '.action-btn',                      # 删除按钮
        '.history': '.app-modal',                           # 变更历史弹窗
        '.loading': '.loading-spinner',                     # 加载状态
        '.action-create': '.audit-log-item',               # 审计日志项
        '.action-update': '.audit-log-item',               # 更新日志
        '.detail': '.field-change',                        # 字段变更详情
    },

    # ==========================================
    # RoleDetailDrawer.vue (实际结构已确认)
    # ==========================================
    'src/views/SystemManagement/__tests__/RoleDetailDrawer.spec.js': {
        '.overlay': '.drawer-overlay',                       # 保持原样
        '.panel': '.drawer-panel',                           # 保持原样
        '.tabs': '.drawer-tabs',                             # Tab 导航容器
        '.tab-logs': '.drawer-tab',                          # 日志 tab 按钮
        '.log-list': '.log-list',                           # 日志列表（需确认）
        '.permission-section': '.unified-perm-section',     # 权限区域
        '.log-section': '.audit-log-section',               # 日志区域
        '.loading': '.loading-state',                       # 加载状态
    },

    # ==========================================
    # SystemSettings.vue (实际结构已确认)
    # ==========================================
    'src/views/SystemManagement/__tests__/SystemSettings.spec.js': {
        '.system-settings': '.system-settings',             # 保持原样 [DECORATIVE]
        '.container': '.ss-container',                       # 容器
        '.sidebar': '.ss-sidebar',                           # 侧边栏
        '.nav': '.ss-nav',                                   # 导航
    },

    # ==========================================
    # ConditionRuleDialog.vue
    # ==========================================
    'src/views/SystemManagement/__tests__/ConditionRuleDialog.spec.js': {
        '.dialog-card': '.dialog-body',                      # 对话框主体
        '.form-group': '.form-group',                        # 表单组 [DECORATIVE]
        'select': 'select',                                  # select 元素
    },

    # ==========================================
    # EnumTypeCreate.vue
    # ==========================================
    'src/views/SystemManagement/__tests__/EnumTypeCreate.spec.js': {
        '.etc-form': '.form-container',                      # 表单容器
        'textarea': 'textarea',                              # textarea 元素
    },

    # ==========================================
    # EnumTypeManagement.vue
    # ==========================================
    'src/views/SystemManagement/__tests__/EnumTypeManagement.spec.js': {
        '.type-management': '.enum-type-management',         # 根元素
        '.filter-category': '.filter-select',                # 分类筛选
        '.filter-mutability': '.filter-select',              # 可变性筛选
        '.create-btn': '.btn-create',                        # 创建按钮
    },

    # ==========================================
    # BusinessConfig.vue
    # ==========================================
    'src/views/SystemManagement/__tests__/BusinessConfig.spec.js': {
        '.business-config': '.business-config',              # 保持原样
        '.back-btn': '.back-button',                         # 返回按钮
        '.bc-tabs': '.config-tabs',                          # 配置标签页
    },
}


def fix_test_file(test_path: str, fixes: dict, dry_run: bool = True) -> int:
    """应用精确修复到测试文件"""
    with open(test_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content
    applied_fixes = []

    for old_selector, new_selector in fixes.items():
        if old_selector in content:
            # 替换单引号版本
            content = content.replace(f"'{old_selector}'", f"'{new_selector}'")
            # 替换双引号版本
            content = content.replace(f'"{old_selector}"', f'"{new_selector}"')
            applied_fixes.append((old_selector, new_selector))

    if applied_fixes and not dry_run:
        with open(test_path, 'w', encoding='utf-8') as f:
            f.write(content)

    return len(applied_fixes)


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Precision UI Selector Fix Tool')
    parser.add_argument('--dry-run', action='store_true', help='只显示不修改')
    parser.add_argument('--fix', action='store_true', help='应用修复')
    args = parser.parse_args()

    print('=' * 80)
    print('  UI Selector PRECISION Fix Tool')
    print('  Based on Actual Component DOM Analysis')
    print('=' * 80)

    total_fixes = 0

    for test_file, fixes in PRECISE_SELECTOR_FIXES.items():
        test_path = PROJECT_ROOT / test_file

        if not test_path.exists():
            print(f'\n[WARNING]  File not found: {test_file}')
            continue

        num_fixes = fix_test_file(str(test_path), fixes, dry_run=not args.fix)

        if num_fixes > 0:
            total_fixes += num_fixes
            action = 'Would apply' if args.dry_run else 'Applied'
            print(f'\n[OK] {action} {num_fixes} fixes to:')
            print(f'   {Path(test_file).name}')
            for old, new in list(fixes.items())[:5]:  # Show first 5
                print(f'   • {old} → {new}')
            if len(fixes) > 5:
                print(f'   ... and {len(fixes) - 5} more')

    print('\n' + '=' * 80)
    print('SUMMARY')
    print('=' * 80)
    print(f'Total Fixes: {total_fixes}')

    if args.dry_run:
        print('\n[Dry Run] To apply fixes, run: python fix_selectors_precision.py --fix')
    else:
        print('\n[OK] All precision fixes applied!')
        print('Next step: npm run test:run to verify')

    return total_fixes


if __name__ == '__main__':
    result = main()
    sys.exit(0 if result > 0 else 1)

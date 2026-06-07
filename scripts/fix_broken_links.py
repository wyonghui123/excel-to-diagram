#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量修复文档中的失效链接
策略：
1. progress/ → archive/progress/（已归档文件）
2. fixes/ → archive/fixes/（已归档文件）
3. 中文字符名 → 英文名（已重命名）
"""
import os
import re
from pathlib import Path

ROOT = Path(r'd:\filework\excel-to-diagram\docs')

# 修复映射：(old_pattern, new_pattern)
REPLACEMENTS = [
    # 归档目录
    (r'\(progress/bo-action-', r'(archive/progress/bo-action-'),
    (r'\(progress/full-test-run', r'(archive/progress/full-test-run'),
    (r'\(progress/v3-bo-action', r'(archive/progress/v3-bo-action'),
    (r'\(progress/db-corruption', r'(archive/progress/db-corruption'),
    (r'\(progress/p0-action', r'(archive/progress/p0-action'),
    (r'\(progress/bo-action-expansion', r'(archive/progress/bo-action-expansion'),
    (r'\(progress/bo-action-vs', r'(archive/progress/bo-action-vs'),
    (r'\(progress/bo-action-v3-round1', r'(archive/progress/bo-action-v3-round1'),
    (r'\(progress/bo-action-v3.6-', r'(archive/progress/bo-action-v3.6-'),
    (r'\(progress/bo-action-v3.7-', r'(archive/progress/bo-action-v3.7-'),
    (r'\(progress/bo-action-v3.8-', r'(archive/progress/bo-action-v3.8-'),
    (r'\(progress/bo-action-v3.9-', r'(archive/progress/bo-action-v3.9-'),
    (r'\(progress/bo-action-v3.10-', r'(archive/progress/bo-action-v3.10-'),
    (r'\(progress/bo-action-v3.11-', r'(archive/progress/bo-action-v3.11-'),
    (r'\(progress/bo-action-v3.12-', r'(archive/progress/bo-action-v3.12-'),
    (r'\(progress/bo-action-v3.13-', r'(archive/progress/bo-action-v3.13-'),
    (r'\(progress/bo-action-v3.14-', r'(archive/progress/bo-action-v3.14-'),
    (r'\(progress/bo-action-v3.15-', r'(archive/progress/bo-action-v3.15-'),
    (r'\(progress/bo-action-v3.16-', r'(archive/progress/bo-action-v3.16-'),
    (r'\(progress/bo-action-p0-5', r'(archive/progress/bo-action-p0-5'),
    (r'\(progress/bo-action-p1-enum', r'(archive/progress/bo-action-p1-enum'),
    # file:/// 路径的归档文件
    (r'file:///d:/filework/excel-to-diagram/docs/progress/bo-action-', r'file:///d:/filework/excel-to-diagram/docs/archive/progress/bo-action-'),
    (r'file:///d:/filework/excel-to-diagram/docs/progress/full-test-run', r'file:///d:/filework/excel-to-diagram/docs/archive/progress/full-test-run'),
    (r'file:///d:/filework/excel-to-diagram/docs/progress/v3-bo-action', r'file:///d:/filework/excel-to-diagram/docs/archive/progress/v3-bo-action'),
    (r'file:///d:/filework/excel-to-diagram/docs/progress/db-corruption', r'file:///d:/filework/excel-to-diagram/docs/archive/progress/db-corruption'),
    (r'file:///d:/filework/excel-to-diagram/docs/progress/p0-action', r'file:///d:/filework/excel-to-diagram/docs/archive/progress/p0-action'),
    (r'file:///d:/filework/excel-to-diagram/docs/MIGRATION_COMPLETED_REPORT\.md', r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/MIGRATION_COMPLETED_REPORT.md'),
    (r'file:///d:/filework/excel-to-diagram/docs/MIGRATION_CHECKLIST\.md', r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/MIGRATION_CHECKLIST.md'),
    (r'file:///d:/filework/excel-to-diagram/docs/FAILED_TESTS\.md', r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/FAILED_TESTS.md'),
    (r'file:///d:/filework/excel-to-diagram/docs/TEST_FIX_REPORT\.md', r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/TEST_FIX_REPORT.md'),
    (r'file:///d:/filework/excel-to-diagram/docs/TEST_FIXES_2026-05-27\.md', r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/TEST_FIXES_2026-05-27.md'),
    (r'file:///d:/filework/excel-to-diagram/docs/AUDIT_LOG_DUPLICATE_FIX_COMPLETED\.md', r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/AUDIT_LOG_DUPLICATE_FIX_COMPLETED.md'),
    (r'file:///d:/filework/excel-to-diagram/docs/AUDIT_LOG_DUPLICATE_ISSUE\.md', r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/AUDIT_LOG_DUPLICATE_ISSUE.md'),
    (r'file:///d:/filework/excel-to-diagram/docs/AUDIT_LOG_FIELD_NAME_FIX\.md', r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/AUDIT_LOG_FIELD_NAME_FIX.md'),
    (r'file:///d:/filework/excel-to-diagram/docs/AUDIT_LOG_FIELD_NAME_FIX_COMPLETED\.md', r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/AUDIT_LOG_FIELD_NAME_FIX_COMPLETED.md'),
    (r'file:///d:/filework/excel-to-diagram/docs/ASSOCIATE_AUDIT_LOG_IMPLEMENTATION\.md', r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/ASSOCIATE_AUDIT_LOG_IMPLEMENTATION.md'),
    (r'file:///d:/filework/excel-to-diagram/docs/POPPER_FIX_IMPLEMENTATION_REPORT\.md', r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/POPPER_FIX_IMPLEMENTATION_REPORT.md'),
    (r'file:///d:/filework/excel-to-diagram/docs/SERVER_RESTART_COMPLETED\.md', r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/SERVER_RESTART_COMPLETED.md'),
    (r'file:///d:/filework/excel-to-diagram/docs/SQLITE_PRODUCTION_P0\.md', r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/SQLITE_PRODUCTION_P0.md'),
    (r'file:///d:/filework/excel-to-diagram/docs/401_ERROR_SOLUTION\.md', r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/401_ERROR_SOLUTION.md'),
    (r'file:///d:/filework/excel-to-diagram/docs/FIX_UPDATED_AT_SSOT', r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/FIX_UPDATED_AT_SSOT'),
    (r'file:///d:/filework/excel-to-diagram/docs/API接口文档\.md', r'file:///d:/filework/excel-to-diagram/docs/api-reference.md'),
    (r'\(\.\./API接口文档\.md', r'(../api-reference.md'),
    (r'\(API接口文档\.md', r'(api-reference.md'),
]

total_fixed = 0
files_modified = 0

for md_file in ROOT.rglob('*.md'):
    try:
        with open(md_file, encoding='utf-8') as f:
            content = f.read()
    except Exception:
        continue
    original = content
    file_fixes = 0
    for old_pat, new_pat in REPLACEMENTS:
        new_content, n = re.subn(old_pat, new_pat, content)
        if n > 0:
            content = new_content
            file_fixes += n
    if content != original:
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write(content)
        total_fixed += file_fixes
        files_modified += 1
        rel = md_file.relative_to(ROOT)
        if file_fixes > 0:
            print(f'  {file_fixes:3d} fixes | {rel}')

print(f'\n[OK] Total: {total_fixed} fixes in {files_modified} files')

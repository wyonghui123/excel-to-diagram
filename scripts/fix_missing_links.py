#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量修复文档中的失效 file:/// 链接
策略：
1. D:/filework/...docs/{file}.md (大小写) → 引用已归档文件，转 archive/fixes/
2. v3-bo-action-main-summary.md → archive/progress/
3. spec-m11-rls.md → spec-m11-rls-implementation.md (重命名)
"""
import os
import re
from pathlib import Path

ROOT = Path(r'd:\filework\excel-to-diagram\docs')

# 修复映射：(pattern, replacement)
FIXES = [
    # 已归档的修复/迁移报告（混合大小写）
    (re.compile(r'file:///D:/filework/excel-to-diagram/docs/MIGRATION_COMPLETED_REPORT\.md', re.IGNORECASE),
     r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/MIGRATION_COMPLETED_REPORT.md'),
    (re.compile(r'file:///D:/filework/excel-to-diagram/docs/MIGRATION_CHECKLIST\.md', re.IGNORECASE),
     r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/MIGRATION_CHECKLIST.md'),
    (re.compile(r'file:///D:/filework/excel-to-diagram/docs/FAILED_TESTS\.md', re.IGNORECASE),
     r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/FAILED_TESTS.md'),
    (re.compile(r'file:///D:/filework/excel-to-diagram/docs/TEST_FIX_REPORT\.md', re.IGNORECASE),
     r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/TEST_FIX_REPORT.md'),
    (re.compile(r'file:///D:/filework/excel-to-diagram/docs/AUDIT_LOG_DUPLICATE_FIX_COMPLETED\.md', re.IGNORECASE),
     r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/AUDIT_LOG_DUPLICATE_FIX_COMPLETED.md'),
    (re.compile(r'file:///D:/filework/excel-to-diagram/docs/AUDIT_LOG_DUPLICATE_ISSUE\.md', re.IGNORECASE),
     r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/AUDIT_LOG_DUPLICATE_ISSUE.md'),
    (re.compile(r'file:///D:/filework/excel-to-diagram/docs/AUDIT_LOG_FIELD_NAME_FIX\.md', re.IGNORECASE),
     r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/AUDIT_LOG_FIELD_NAME_FIX.md'),
    (re.compile(r'file:///D:/filework/excel-to-diagram/docs/AUDIT_LOG_FIELD_NAME_FIX_COMPLETED\.md', re.IGNORECASE),
     r'file:///d:/filework/excel-to-diagram/docs/archive/fixes/AUDIT_LOG_FIELD_NAME_FIX_COMPLETED.md'),
    # v3-bo-action-main-summary.md → archive/progress/
    (re.compile(r'(file:///d:/filework/excel-to-diagram/docs/)(?!archive/)v3-bo-action-main-summary\.md'),
     r'\1archive/progress/v3-bo-action-main-summary.md'),
    # spec-m11-rls.md → spec-m11-rls-implementation.md
    (re.compile(r'spec-m11-rls\.md(?![a-z\-])'),
     r'spec-m11-rls-implementation.md'),
    (re.compile(r'spec-m10-mcp-server\.md(?![a-z\-])'),
     r'spec-m10-mcp-server.md'),
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
    for pattern, repl in FIXES:
        new_content, n = pattern.subn(repl, content)
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

print(f'\n[OK] Total: {total_fixed} missing-link fixes in {files_modified} files')

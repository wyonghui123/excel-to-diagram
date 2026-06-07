#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""运行 link-check 并分析问题分布"""
import sys
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS_DIR = ROOT / 'docs'

# 直接调用 check_doc_links.py 的核心函数
sys.path.insert(0, str(ROOT / 'scripts'))
from check_doc_links import scan_file

md_files = sorted(DOCS_DIR.rglob('*.md'))
print(f'[INFO] Scanning {len(md_files)} markdown files...\n')

missing = []
anchor = []
error = []
file_issue_count = Counter()

for md_file in md_files:
    issues = scan_file(md_file, check_external=False)
    if not issues:
        continue
    file_issue_count[str(md_file.relative_to(ROOT))] = len(issues)
    for status, link, line_num in issues:
        if status == 'missing':
            missing.append((str(md_file.relative_to(ROOT)), line_num, link))
        elif status == 'anchor_missing':
            anchor.append((str(md_file.relative_to(ROOT)), line_num, link))
        elif status == 'error':
            error.append((str(md_file.relative_to(ROOT)), line_num, link))

print(f'=== Issue Type Distribution ===')
print(f'  [MISSING]: {len(missing)}')
print(f'  [ANCHOR]:  {len(anchor)}')
print(f'  [ERROR]:   {len(error)}')
print()

# 按归一化路径统计
def normalize(link):
    if '#' in link:
        return link.split('#')[0]
    return link

print(f'=== Top 20 MISSING links (by normalized path) ===')
mc = Counter(normalize(m[2]) for m in missing)
for link, count in mc.most_common(20):
    print(f'  {count:3d}x  {link[:90]}')
print()

print(f'=== Top 20 ANCHOR issues (by normalized path) ===')
ac = Counter(normalize(a[2]) for a in anchor)
for link, count in ac.most_common(20):
    print(f'  {count:3d}x  {link[:90]}')
print()

print(f'=== Files with most issues (Top 10) ===')
for path, count in file_issue_count.most_common(10):
    print(f'  {count:3d} issues | {path}')
print()

# 写入完整结果
with open(ROOT / 'scripts' / 'link-issues-detailed.txt', 'w', encoding='utf-8') as f:
    f.write(f'=== MISSING: {len(missing)} ===\n')
    for path, line_num, link in missing:
        f.write(f'{path}:L{line_num} {link}\n')
    f.write(f'\n=== ANCHOR: {len(anchor)} ===\n')
    for path, line_num, link in anchor:
        f.write(f'{path}:L{line_num} {link}\n')
    f.write(f'\n=== ERROR: {len(error)} ===\n')
    for path, line_num, link in error:
        f.write(f'{path}:L{line_num} {link}\n')

print(f'[OK] Detailed issues written to scripts/link-issues-detailed.txt')

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量修复文档中的失效 anchor 链接
模式：
- 链接中写 "#一xxx" 应为 "#一-xxx"（中文数字后缺横线）
- 链接中写 "#七附录xxx" 应为 "#七-附录xxx"（顿号丢失）
- 链接中写 "#71-xxx" 应为 "#7-1-xxx" 或原意

策略：保守修复，只修复明显的中文编号 anchor
"""
import os
import re
from pathlib import Path

ROOT = Path(r'd:\filework\excel-to-diagram\docs')

# 中文数字
CN_NUMS = '一二三四五六七八九十百千零〇壹贰叁肆伍陆柒捌玖拾'
# 阿拉伯数字
ARAB_NUMS = '0123456789'

# 修复模式：(pattern, replacement)
FIXES = [
    # #一xxx → #一-xxx (中文数字 + 紧接中文字符无横线)
    (re.compile(r'#([' + CN_NUMS + r'])([\u4e00-\u9fff])'), r'#\1-\2'),
    # #一 xxx → #一-xxx (中文数字 + 空格 + 字符)
    (re.compile(r'#([' + CN_NUMS + r'])\s+([\u4e00-\u9fff])'), r'#\1-\2'),
    # #十 xxx → #十-xxx (10 以上的复合数字)
    (re.compile(r'#(十[' + CN_NUMS + r']?)\s+([\u4e00-\u9fff])'), r'#\1-\2'),
    (re.compile(r'#([' + CN_NUMS + r']十[' + CN_NUMS + r']?)\s+([\u4e00-\u9fff])'), r'#\1-\2'),
    # 修复 "./xx.md#一xxx" 形式
    (re.compile(r'(\.md)#([' + CN_NUMS + r'])([\u4e00-\u9fff])'), r'\1#\2-\3'),
    (re.compile(r'(\.md)#([' + CN_NUMS + r'])\s+([\u4e00-\u9fff])'), r'\1#\2-\3'),
    # 修复 "#十六 -xxx" → "#十六-xxx" (数字间空格)
    (re.compile(r'#(十[' + CN_NUMS + r']?) '), r'#\1-'),
    (re.compile(r'#(' + CN_NUMS + r'{2,}) '), r'#\1-'),
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

print(f'\n[OK] Total: {total_fixed} anchor fixes in {files_modified} files')

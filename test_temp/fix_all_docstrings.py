#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量扫描 + 修复 docstring 损坏问题"""
import re
import sys
from pathlib import Path
import ast

filepath = Path(r'd:\filework\excel-to-diagram\meta\tests\test_association_multi_hop.py')
raw = filepath.read_bytes()
text = raw.decode('utf-8')
lines = text.splitlines(keepends=True)

# 找所有 line N: 末尾是 `""` 而不是 `"""` 的 docstring
fixed_count = 0
for i, line in enumerate(lines, 1):
    stripped = line.rstrip('\n').rstrip('\r')
    # 模式: 缩进 + """ 开头（带内容），但末尾只有 2 个 "
    if '"""' not in stripped:
        continue
    # 数末尾连续的 " 数量
    trailing_quotes = len(stripped) - len(stripped.rstrip('"'))
    if trailing_quotes == 2:
        # 修复：加 1 个 "
        print(f"Line {i}: 末尾只有 2 个 '\"' - {stripped[-40:]!r}")
        # 看是否是 docstring (开 """ 后内容有 U+FFFD)
        if '\ufffd' in stripped or '�' in stripped:
            # 这是损坏的 docstring，移除 U+FFFD 并补 1 个 "
            cleaned = stripped.replace('\ufffd', '').replace('\ufffd', '').rstrip('"') + '"""'
            print(f"  → 修复: {cleaned!r}")
            lines[i-1] = cleaned + '\n'
            fixed_count += 1

# 写回
new_text = ''.join(lines)
filepath.write_bytes(new_text.encode('utf-8'))

print(f"\n修复了 {fixed_count} 行")

# 验证
try:
    ast.parse(new_text)
    print("[OK] ast.parse() passed!")
except SyntaxError as e:
    print(f"[FAIL] line {e.lineno}: {e.msg}")
    print(f"  text: {e.text!r}")

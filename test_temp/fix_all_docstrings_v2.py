#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量修复 test_association_multi_hop.py 所有 docstring 损坏"""
import re
import sys
from pathlib import Path
import ast

filepath = Path(r'd:\filework\excel-to-diagram\meta\tests\test_association_multi_hop.py')
raw = filepath.read_bytes()
text = raw.decode('utf-8')
lines = text.splitlines(keepends=True)

# 规则: 如果行以 `    """` 开头（缩进 4 空格）且包含 `"""` 但末尾没有 3 个 `"`
# 而且该行不是 executescript(""" 这种开 SQL 字符串的行

fixed = []
for i, line in enumerate(lines, 1):
    stripped = line.rstrip('\n').rstrip('\r')
    # 跳过非 docstring 行
    if '"""' not in stripped:
        continue
    # 跳过 SQL 字符串开 (`executescript("""`)
    if 'executescript' in stripped and stripped.endswith('"""'):
        continue
    # 跳过 """Test method""" (平衡)
    if stripped.endswith('"""') and stripped.count('"""') == 2:
        continue
    # 跳过 """ 开始 SQL 块
    if stripped.count('"""') == 1 and not stripped.endswith('"""'):
        # 这种是 docstring 开头
        # 检查是否应该是闭合
        if '"""' in stripped and not stripped.endswith('"""'):
            # docstring 开头（多行）— 跳到闭合行
            continue

# 更简单：找所有以 `    """` 开头但不以 `"""` 结尾的行，且内容里有 U+FFFD
for i, line in enumerate(lines, 1):
    stripped = line.rstrip('\n').rstrip('\r')
    if not stripped.startswith('    """'):
        continue
    if '"""' not in stripped:
        continue
    if stripped.endswith('"""'):
        continue
    # 末尾 2 个 " 才补 1 个
    if stripped.endswith('""'):
        # 移除 U+FFFD
        cleaned = stripped.replace('\ufffd', '').replace('\ufffd', '').rstrip('"') + '"""'
        if cleaned != stripped:
            print(f"Line {i}: 修复 {stripped[-50:]!r} -> {cleaned[-50:]!r}")
            lines[i-1] = cleaned + '\n'
            fixed.append(i)

# 写回
new_text = ''.join(lines)
filepath.write_bytes(new_text.encode('utf-8'))
print(f"\n修复了 {len(fixed)} 行")

# 验证
try:
    ast.parse(new_text)
    print("[OK] ast.parse() passed")
except SyntaxError as e:
    print(f"[FAIL] line {e.lineno}:{e.offset} - {e.msg}")
    print(f"  Text: {e.text!r}")
    sys.exit(1)

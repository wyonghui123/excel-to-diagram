#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 test_association_multi_hop.py line 35 docstring 损坏"""
import sys
from pathlib import Path

filepath = Path(r'd:\filework\excel-to-diagram\meta\tests\test_association_multi_hop.py')

# 读 bytes
raw = filepath.read_bytes()
text = raw.decode('utf-8')
lines = text.splitlines(keepends=True)

print(f"Total lines: {len(lines)}")
print(f"Line 35 raw: {repr(lines[34])}")

# 找损坏的 docstring
# 期望:     """完整 schema（多跳需要完整体 hierarchy 层次）"""
# 实际:     """完整 schema（多跳需要完�?hierarchy�?"""  (U+FFFD 替换字符 + 末尾少 1 个 ")
bad_line = lines[34]
print(f"Bad line ends with: {repr(bad_line[-10:])}")
print(f"Quote count: {bad_line.count(chr(34))}")

# 修复：替换 line 35 为正确的 docstring
# 保留缩进
indent = bad_line[:len(bad_line) - len(bad_line.lstrip())]
new_line = indent + '"""完整 schema（多跳需要完整体 hierarchy 层次）"""\n'
lines[34] = new_line

# 写回
new_text = ''.join(lines)
filepath.write_bytes(new_text.encode('utf-8'))

print(f"\n[OK] Fixed. New line 35: {repr(new_line)}")

# 验证
import ast
try:
    ast.parse(new_text)
    print("[OK] ast.parse() passed")
except SyntaxError as e:
    print(f"[FAIL] {e}")
    sys.exit(1)

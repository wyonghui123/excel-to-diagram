#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""详细诊断 test_association_multi_hop.py"""
import ast
import sys
from pathlib import Path

filepath = Path(r'd:\filework\excel-to-diagram\meta\tests\test_association_multi_hop.py')
text = filepath.read_text(encoding='utf-8')

# 1. 找所有 U+FFFD 位置
lines = text.splitlines()
print(f"=== U+FFFD locations ===")
for i, line in enumerate(lines, 1):
    if '\ufffd' in line:
        # 找位置
        idx = 0
        positions = []
        while True:
            idx = line.find('\ufffd', idx)
            if idx == -1:
                break
            positions.append(idx)
            idx += 1
        print(f"Line {i}: {len(positions)} U+FFFD at {positions[:5]}")
        print(f"  Text: {line[:100]}")

# 2. 验证 ast.parse
print(f"\n=== ast.parse() ===")
try:
    ast.parse(text)
    print("[OK] ast.parse() passed")
except SyntaxError as e:
    print(f"[FAIL] {e.lineno}:{e.offset} - {e.msg}")
    print(f"  Text: {e.text!r}")

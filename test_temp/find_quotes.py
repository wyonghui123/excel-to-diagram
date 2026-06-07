#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""找所有包含 docstring 分隔符的行"""
from pathlib import Path

text = Path(r'd:\filework\excel-to-diagram\meta\tests\test_association_multi_hop.py').read_text(encoding='utf-8')
lines = text.splitlines()

print(f'Total lines: {len(lines)}')
print()
separator = chr(34) * 3  # triple quote
print(f'=== Lines with quote (separator={separator!r}) ===')
for i, line in enumerate(lines, 1):
    if '"' in line:
        cnt_q = line.count('"')
        # 末尾连续的 "
        trailing = len(line) - len(line.rstrip('"'))
        has_triple = separator in line
        marker = " <-- TRIPLE" if has_triple else ""
        print(f'{i:4}: q={cnt_q:2} trailing={trailing:2}{marker} | {line[:80]!r}')

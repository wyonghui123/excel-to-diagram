#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查文件里所有 docstring 是否配对"""
import tokenize
import io
from pathlib import Path

filepath = Path(r'd:\filework\excel-to-diagram\meta\tests\test_association_multi_hop.py')
text = filepath.read_text(encoding='utf-8')

# 用 tokenize 找所有 STRING tokens
readline = io.StringIO(text).readline
tokens = []
try:
    for tok in tokenize.generate_tokens(readline):
        if tok.type == tokenize.STRING and '"""' in tok.string:
            tokens.append((tok.start, tok.string[:50]))
except tokenize.TokenizeError as e:
    print(f"Tokenize error: {e}")

print(f"=== Triple-quoted strings: {len(tokens)} ===")
for (line, col), s in tokens:
    print(f"Line {line} col {col}: {s!r}")

# 期望：偶数个 tokens（开/闭配对）
if len(tokens) % 2 != 0:
    print(f"\n[!!!] ODD count = docstring not paired!")
    # 找未配对的
    if tokens:
        last_line = tokens[-1][0][0]
        print(f"Last triple-quoted string starts at line {last_line}")
        # 找从 last_line+1 到下个 """ 的范围

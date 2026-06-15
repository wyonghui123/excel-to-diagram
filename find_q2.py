#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Direct test: find unmasked ? in the actual file"""
import sys
sys.path.insert(0, 'scripts')
from check_file_encoding import mask_code_regions

with open('.trae/rules/file-encoding-rules.md', 'r', encoding='utf-8') as f:
    text = f.read()

# Direct test
masked = mask_code_regions(text)
print(f'orig lines: {text.count(chr(10))}, masked lines: {masked.count(chr(10))}')

# Find ? in masked
for i, c in enumerate(masked):
    if c == '?':
        # Check bytes around
        prev_char = masked[i-1] if i > 0 else ''
        next_char = masked[i+1] if i+1 < len(masked) else ''
        line_no = masked[:i].count('\n') + 1
        # Get whole line in masked
        line_start = masked.rfind('\n', 0, i) + 1
        line_end = masked.find('\n', i)
        if line_end == -1: line_end = len(masked)
        line_content = masked[line_start:line_end]
        print(f'? at L{line_no} pos {i}: prev={prev_char!r} next={next_char!r}')
        print(f'  masked line: {line_content!r}')
        # Also original
        orig_line_start = text.rfind('\n', 0, i) + 1
        orig_line_end = text.find('\n', i)
        if orig_line_end == -1: orig_line_end = len(text)
        orig_line = text[orig_line_start:orig_line_end]
        print(f'  orig line:   {orig_line!r}')
        break

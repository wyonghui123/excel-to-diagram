#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Diagnose mojibake in new file using script's own sig set"""
import sys
sys.path.insert(0, 'scripts')
from check_file_encoding import mask_code_regions, MOJIBAKE_SIGNATURE_CHARS

with open('.trae/rules/encoding-prevention-v20260612.md', 'r', encoding='utf-8') as f:
    text = f.read()
masked = mask_code_regions(text)
print(f'File: {len(text)} chars, masked: {len(masked)} chars')
print(f'MOJIBAKE_SIGNATURE_CHARS count: {len(MOJIBAKE_SIGNATURE_CHARS)}')
print(f'Characters: {sorted(MOJIBAKE_SIGNATURE_CHARS)!r}')

# Count hits
hits = [(i, c) for i, c in enumerate(masked) if c in MOJIBAKE_SIGNATURE_CHARS]
print(f'\nHits in masked: {len(hits)}')
for i, c in hits[:10]:
    line = masked[:i].count('\n') + 1
    lines = masked.split('\n')
    line_text = lines[line-1] if line-1 < len(lines) else ''
    print(f'  L{line} {c!r}({hex(ord(c))}): {line_text[:80]!r}')

# Find which sig chars are present
present = set(c for c in masked if c in MOJIBAKE_SIGNATURE_CHARS)
print(f'\nPresent sig chars:')
for c in sorted(present):
    cnt = masked.count(c)
    print(f'  {c!r}({hex(ord(c))}): {cnt} occurrences')

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Temp diagnostic - find remaining mojibake in file-encoding-rules.md"""
import sys
sys.path.insert(0, 'scripts')
from check_file_encoding import mask_code_regions

with open('.trae/rules/file-encoding-rules.md', 'r', encoding='utf-8') as f:
    text = f.read()

masked = mask_code_regions(text)
print(f'Total: {len(text)} chars, masked: {len(masked)} chars')

# Find 0x3F after high byte
masked_bytes = masked.encode('utf-8')
hits_3f = []
for i in range(1, len(masked_bytes)):
    if masked_bytes[i] == 0x3F and masked_bytes[i-1] >= 0x80:
        line = masked[:i].count('\n') + 1
        # find line in original text
        orig_lines = text.split('\n')
        if line-1 < len(orig_lines):
            hits_3f.append((line, orig_lines[line-1]))

print(f'\n0x3F after high byte ({len(hits_3f)}):')
for line, content in hits_3f[:5]:
    print(f'  L{line}: {content[:100]!r}')

# Find mojibake signature
sig = set('缁熶竴鐎广垺鍩涚粩瀹㈡埛绔璇锋眰瓒呮椂缃戠粶閿欒')
hits_moji = []
for i, c in enumerate(masked):
    if c in sig:
        line = masked[:i].count('\n') + 1
        orig_lines = text.split('\n')
        if line-1 < len(orig_lines):
            hits_moji.append((line, orig_lines[line-1]))

print(f'\nMojibake sig ({len(hits_moji)}):')
for line, content in hits_moji[:5]:
    print(f'  L{line}: {content[:100]!r}')

#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""提取 ARCHITECTURE_V2.md §六 到独立子文档"""
import os

os.chdir(r'd:\filework\excel-to-diagram')

with open('docs/ARCHITECTURE_V2.md', encoding='utf-8') as f:
    lines = f.read().split('\n')

# 拆分 §六、前端架构详解: 0-based 1113-1590
chapter6 = lines[1113:1591]

header = '''---
title: 六、前端架构详解
version: 3.0.2
date: 2026-06-07
status: 活跃
parent: ARCHITECTURE_V2.md
---

# 六、前端架构详解

> 本章节从 [ARCHITECTURE_V2.md §六](../ARCHITECTURE_V2.md#六-前端架构详解) 提取（2026-06-07 v3.0.2 拆分）
>
> **拆分原因**：原章节 478 行/15.6KB，独立成文便于维护
>
> **同步说明**：本文件为单一事实源，主文档 §六 仅保留链接

---

'''

content = header + '\n'.join(chapter6)

with open('docs/architecture/06-frontend-architecture.md', 'w', encoding='utf-8') as f:
    f.write(content)

size_kb = len(content.encode('utf-8')) / 1024
print('[OK] Extracted', len(chapter6), 'lines to architecture/06-frontend-architecture.md')
print('     File size:', round(size_kb, 1), 'KB')

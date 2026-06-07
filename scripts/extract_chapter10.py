#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""提取 ARCHITECTURE_V2.md §十 部署与运维 到独立子文档"""
import os

os.chdir(r'd:\filework\excel-to-diagram')

with open('docs/ARCHITECTURE_V2.md', encoding='utf-8') as f:
    lines = f.read().split('\n')

# 拆分 §十、部署与运维: 0-based 2505-2822
chapter10 = lines[2505:2823]

header = '''---
title: 十、部署与运维
version: 3.0.2
date: 2026-06-07
status: 活跃
parent: ARCHITECTURE_V2.md
---

# 十、部署与运维

> 本章节从 [ARCHITECTURE_V2.md §十](../ARCHITECTURE_V2.md#十-部署与运维) 提取（2026-06-07 v3.0.2 拆分）
>
> **拆分原因**：原章节 318 行/9.3KB，独立成文便于维护
>
> **同步说明**：本文件为单一事实源，主文档 §十 仅保留链接

---

'''

content = header + '\n'.join(chapter10)

with open('docs/architecture/10-deployment-and-ops.md', 'w', encoding='utf-8') as f:
    f.write(content)

size_kb = len(content.encode('utf-8')) / 1024
print('[OK] Extracted', len(chapter10), 'lines to architecture/10-deployment-and-ops.md')
print('     File size:', round(size_kb, 1), 'KB')

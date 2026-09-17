#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Update PERMISSION_TODOS.md with P1.6 wildcard support"""

filepath = r'd:\filework\excel-to-diagram\docs\PERMISSION_TODOS.md'

with open(filepath, 'r', encoding='utf-8') as f:
    content = f.read()

# Check if P1.6 already exists
if 'P1.6' in content:
    print('SKIP: P1.6 already exists')
    exit(0)

# Find insertion point: after P1.5, before P2 section
marker = '## 🟡 P2 - 评估'
if marker not in content:
    print('ERROR: marker not found')
    exit(1)

new_section = '''### P1.6 Dimension Scope 和 Condition 支持 `*` 通配符
- **现状**: 功能权限支持 `*`（超级管理员），但 dimension scope 和 condition 不支持
- **风险**: 无法表达"全量维度"的合法场景，admin 需逐个配置所有维度值
- **方向**: 扩展 role_dimension_scopes 支持 scope_mode='all'，condition 支持 '*'
- **关联**: [WILDCARD_SUPPORT_RESEARCH.md](WILDCARD_SUPPORT_RESEARCH.md), INDUSTRY_PERMISSION_RESEARCH_OVERVIEW.md 6.3.10
- **状态**: 研究完成，待实施
- **优先级**: P1 (中)

---

'''

content = content.replace(marker, new_section + marker)

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(content)

print('SUCCESS: P1.6 section inserted')

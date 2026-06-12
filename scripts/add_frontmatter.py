#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
为关键文档添加 frontmatter（保守策略）
仅对 docs/ 顶层的核心文档添加，避免破坏已有结构
"""
import os
import re
from pathlib import Path
from datetime import datetime

ROOT = Path(r'd:\filework\excel-to-diagram\docs')

# 已识别的核心文档及其元数据
CORE_DOCS = {
    'ARCHITECTURE_V2.md': {
        'title': '元数据驱动统一架构文档 (Metadata-Driven Unified Architecture)',
        'version': '3.0.2',
        'status': '活跃',
        'audience': '架构师、AI Agent、开发者',
    },
    'README.md': {
        'title': 'Excel-to-Diagram 文档门户',
        'version': '1.0.0',
        'status': '活跃',
        'audience': '全员',
    },
    'PERMISSION_SYSTEM_INDEX.md': {
        'title': '权限体系文档统一索引',
        'version': '1.0.0',
        'status': '活跃',
        'audience': '架构师、开发者、AI Agent',
    },
    'DOCUMENTATION_STANDARDS.md': {
        'title': '文档编写规范 (Documentation Standards)',
        'version': '1.0.0',
        'status': '活跃',
        'audience': '全员',
    },
    'TECH-DEBT.md': {
        'title': '技术债务清单',
        'version': '1.0.0',
        'status': '活跃',
        'audience': '开发者',
    },
    'requirements.md': {
        'title': '需求规格说明',
        'version': '1.0.0',
        'status': '活跃',
        'audience': '产品经理、开发者',
    },
    'requirements-backlog.md': {
        'title': '需求待办列表',
        'version': '1.0.0',
        'status': '活跃',
        'audience': '产品经理、开发者',
    },
    'data-model.md': {
        'title': '数据模型说明',
        'version': '1.0.0',
        'status': '活跃',
        'audience': '架构师、开发者',
    },
    'api-reference.md': {
        'title': 'API 接口参考',
        'version': '1.0.0',
        'status': '活跃',
        'audience': '开发者',
    },
    'architecture-design.md': {
        'title': '架构设计总览',
        'version': '1.0.0',
        'status': '活跃',
        'audience': '架构师、开发者',
    },
    'DEPLOYMENT_STANDARDS.md': {
        'title': '部署标准',
        'version': '1.0.0',
        'status': '活跃',
        'audience': '运维、开发者',
    },
    'DIRECTORY_STRUCTURE.md': {
        'title': '项目目录结构',
        'version': '1.0.0',
        'status': '活跃',
        'audience': '开发者',
    },
    'UI_COMPONENT_GUIDELINES.md': {
        'title': 'UI 组件使用指南',
        'version': '1.0.0',
        'status': '活跃',
        'audience': '前端开发者',
    },
    'audit-log-best-practices.md': {
        'title': '审计日志最佳实践',
        'version': '1.0.0',
        'status': '活跃',
        'audience': '架构师、开发者、运维',
    },
}

FRONTMATTER_PATTERN = re.compile(r'^---\s*\n.+?\n---\s*\n', re.DOTALL)

added = 0
skipped = 0

for filename, meta in CORE_DOCS.items():
    path = ROOT / filename
    if not path.exists():
        continue
    try:
        with open(path, encoding='utf-8') as f:
            content = f.read()
    except Exception:
        continue

    # 已有 frontmatter 跳过
    if FRONTMATTER_PATTERN.match(content):
        skipped += 1
        print(f'  SKIP (has frontmatter) | {filename}')
        continue

    # 构建 frontmatter
    fm_lines = ['---']
    fm_lines.append(f'title: {meta["title"]}')
    fm_lines.append(f'version: {meta["version"]}')
    fm_lines.append(f'date: 2026-06-07')
    fm_lines.append(f'status: {meta["status"]}')
    fm_lines.append(f'audience: {meta["audience"]}')
    fm_lines.append('---')
    fm_lines.append('')
    frontmatter = '\n'.join(fm_lines) + '\n'

    new_content = frontmatter + content

    with open(path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    added += 1
    print(f'  +{filename}')

print(f'\n[OK] Added frontmatter to {added} docs, skipped {skipped} (already has)')

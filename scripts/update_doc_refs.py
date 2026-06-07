#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""批量更新文档引用"""
import os
import re

# 文件重命名映射
RENAMES = {
    '需求文档.md': 'requirements.md',
    '需求Backlog.md': 'requirements-backlog.md',
    '数据模型文档.md': 'data-model.md',
    'API接口文档.md': 'api-reference.md',
    '架构设计文档.md': 'architecture-design.md',
    '审计日志最佳实践.md': 'audit-log-best-practices.md',
    '用友BIP权限模型研究补充.md': 'yonyou-bip-permission-research.md',
    '竞品架构分析_元数据驱动与权限模型.md': 'competitive-analysis-metadata-permission.md',
    '权限配置流程优化_维度驱动vs菜单驱动.md': 'permission-config-optimization.md',
    '权限体系_单一事实源补充分析.md': 'permission-ssot-analysis.md',
    '权限体系元数据驱动化_细化方案设计.md': 'permission-metadata-driven-design.md',
    '方案设计_元数据驱动权限体系.md': 'permission-metadata-driven-solution.md',
    '方案设计_权限体系元数据驱动优化.md': 'permission-metadata-driven-optimization.md',
    '方案细化_权限体系元数据驱动化.md': 'permission-metadata-driven-refinement.md',
    'Spec_权限体系元数据驱动化.md': 'spec-permission-metadata-driven.md',
    'Spec_消除meta_actions表统一动作声明.md': 'spec-eliminate-meta-actions.md',
    'MetaAction权限体系深度分析与设计方案.md': 'meta-action-permission-analysis.md',
    '用户指引设计方案.md': 'user-guide-design.md',
    '用户指引集成指南.md': 'user-guide-integration.md',
}

ROOT = r'd:\filework\excel-to-diagram\docs'

updated_files = {}
for root, dirs, files in os.walk(ROOT):
    for f in files:
        if not f.endswith('.md'):
            continue
        path = os.path.join(root, f)
        with open(path, encoding='utf-8') as fp:
            content = fp.read()
        original = content
        for old, new in RENAMES.items():
            # 替换 markdown 链接中的文件名
            content = content.replace(f'](./{old})', f'](./{new})')
            content = content.replace(f'](../{old})', f'](../{new})')
            content = content.replace(f']({old})', f']({new})')
            content = content.replace(f'file:///{old}', f'file:///{new}')
        if content != original:
            with open(path, 'w', encoding='utf-8') as fp:
                fp.write(content)
            updated_files[path] = sum(1 for old in RENAMES if old in original)

print(f'[OK] Updated {len(updated_files)} files')
for path, count in sorted(updated_files.items(), key=lambda x: -x[1])[:20]:
    print(f'  {count:3d} refs | {os.path.relpath(path, ROOT)}')

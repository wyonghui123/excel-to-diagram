"""
schema/audit/diff.py - M13 v1.2.0 Diff 报告生成器

生成 Markdown / HTML 格式的 schema 变更报告。

用法：
    from schema.audit.diff import (
        diff_schemas,
        format_markdown_report,
        format_html_report,
    )

    diff = diff_schemas(before, after)
    md = format_markdown_report(diff, before_entity='User', after_entity='User')
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional

from .score import calc_compatibility_score, calc_entity_score

logger = logging.getLogger(__name__)


def diff_schemas(before: dict, after: dict) -> dict:
    """生成完整 diff 报告

    Args:
        before: 旧 ENTITY_SCHEMAS 字典
        after: 新 ENTITY_SCHEMAS 字典

    Returns:
        dict: diff 报告
            {
                'score': int,
                'added_entities': [...],
                'removed_entities': [...],
                'modified_entities': {
                    'User': {'score': 95, 'changes': [...]},
                    ...
                },
                'breaking_changes': [...],
                'summary': '...',
            }
    """
    score = calc_compatibility_score(before, after)

    before_entities = set(before.keys())
    after_entities = set(after.keys())

    added = sorted(after_entities - before_entities)
    removed = sorted(before_entities - after_entities)
    common = before_entities & after_entities

    modified = {}
    for entity in sorted(common):
        entity_score, changes = calc_entity_score(before[entity], after[entity])
        if changes:  # 仅当有变更时记录
            modified[entity] = {
                'score': entity_score,
                'changes': changes,
            }

    # 提取破坏性变更
    breaking = []
    for entity, info in modified.items():
        for change in info['changes']:
            if any(op in change for op in ['remove', 'rename', 'type-narrow', 'required-add']):
                breaking.append(f'{entity}: {change}')
    for entity in removed:
        breaking.append(f'entity removed: {entity}')

    return {
        'score': score,
        'added_entities': added,
        'removed_entities': removed,
        'modified_entities': modified,
        'breaking_changes': breaking,
        'summary': _build_summary(score, added, removed, modified, breaking),
        'generated_at': datetime.now().isoformat(),
    }


def _build_summary(score: int, added: list, removed: list, modified: dict, breaking: list) -> str:
    """构建人类可读摘要"""
    level = (
        '[OK] 完全兼容' if score == 100 else
        '[WARNING] 软警告' if score >= 80 else
        '[MEDIUM] 中等变更' if score >= 50 else
        '[X] 破坏性变更'
    )
    summary = f'{level}（{score}/100）\n\n'
    summary += f'- 新增 entity: {len(added)}\n'
    summary += f'- 删除 entity: {len(removed)}\n'
    summary += f'- 修改 entity: {len(modified)}\n'
    summary += f'- 破坏性变更: {len(breaking)}\n'
    return summary


def format_markdown_report(diff: dict, include_score: bool = True) -> str:
    """生成 Markdown 格式的 diff 报告

    Args:
        diff: diff_schemas() 返回的字典
        include_score: 是否包含评分

    Returns:
        str: Markdown 报告
    """
    lines = [
        f'# Schema 变更报告 - {diff.get("generated_at", "unknown")[:10]}',
        '',
    ]
    if include_score:
        lines.append(f'## 兼容性评分：{diff["score"]}/100')
        lines.append(diff['summary'])
        lines.append('')

    if diff['breaking_changes']:
        lines.append('## [WARNING] 破坏性变更')
        for change in diff['breaking_changes']:
            lines.append(f'- [X] {change}')
        lines.append('')

    if diff['added_entities']:
        lines.append('## [OK] 新增 Entity')
        for entity in diff['added_entities']:
            lines.append(f'- {entity}')
        lines.append('')

    if diff['removed_entities']:
        lines.append('## [X] 删除 Entity')
        for entity in diff['removed_entities']:
            lines.append(f'- {entity}')
        lines.append('')

    if diff['modified_entities']:
        lines.append('## [DECORATIVE] 修改 Entity 详情')
        for entity, info in diff['modified_entities'].items():
            lines.append(f'### {entity}（评分 {info["score"]}/100）')
            for change in info['changes']:
                icon = (
                    '[X]' if 'remove' in change or 'rename' in change else
                    '[WARNING]' if 'type-narrow' in change or 'required-add' in change else
                    '[OK]'
                )
                lines.append(f'- {icon} {change}')
            lines.append('')

    return '\n'.join(lines)


def format_html_report(diff: dict) -> str:
    """生成 HTML 格式的 diff 报告

    Args:
        diff: diff_schemas() 返回的字典

    Returns:
        str: HTML 报告
    """
    score = diff['score']
    score_color = (
        'green' if score == 100 else
        'orange' if score >= 80 else
        'darkorange' if score >= 50 else
        'red'
    )

    rows = []
    for entity, info in diff['modified_entities'].items():
        for change in info['changes']:
            rows.append(f'<tr><td>{entity}</td><td>{change}</td></tr>')

    breaking_rows = ''.join(
        f'<tr><td colspan="2" class="breaking">{change}</td></tr>'
        for change in diff['breaking_changes']
    )

    return f'''<!DOCTYPE html>
<html><head>
<title>Schema Diff Report</title>
<style>
body {{ font-family: sans-serif; padding: 20px; }}
.score {{ font-size: 48px; color: {score_color}; font-weight: bold; }}
table {{ border-collapse: collapse; width: 100%; margin-top: 20px; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background: #f5f5f5; }}
.breaking {{ color: red; font-weight: bold; }}
</style>
</head><body>
<h1>Schema Diff Report</h1>
<div class="score">{score}/100</div>
<pre>{diff['summary']}</pre>
<h2>破坏性变更</h2>
<table>{breaking_rows}</table>
<h2>详细变更</h2>
<table>
<tr><th>Entity</th><th>变更</th></tr>
{''.join(rows)}
</table>
</body></html>'''

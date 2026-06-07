"""
schema/audit - M13 v1.2.0 Schema 审计模块

提供：
- 字段变更 diff
- 兼容性评分（0-100）
- Markdown / HTML 报告
- CI 校验脚本
"""
from .score import (
    calc_compatibility_score,
    calc_entity_score,
    SCORE_RULES,
)
from .diff import (
    diff_schemas,
    format_markdown_report,
    format_html_report,
)

__all__ = [
    'calc_compatibility_score',
    'calc_entity_score',
    'SCORE_RULES',
    'diff_schemas',
    'format_markdown_report',
    'format_html_report',
]

__version__ = '1.2.0'

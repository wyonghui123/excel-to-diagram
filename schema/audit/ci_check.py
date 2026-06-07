"""
schema/audit/ci_check.py - M13 v1.3.0 CI 校验脚本

CLI 工具：从 git diff 提取 ENTITY_SCHEMAS 变更 → 计算兼容性评分 → 阻止 PR 合并

用法：
    python -m schema.audit.ci_check \\
        --before=origin/main:meta/graphql/__init__.py \\
        --after=HEAD:meta/graphql/__init__.py \\
        --threshold=80

退出码：
    0 = 通过（score >= threshold）
    1 = 失败（score < threshold）
    2 = 错误（git show 失败 / 文件不存在）
"""
import argparse
import logging
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def extract_entity_schemas_from_file(file_content: str) -> dict:
    """从 Python 源文件提取 ENTITY_SCHEMAS 字典

    Args:
        file_content: Python 源文件内容

    Returns:
        dict: ENTITY_SCHEMAS（执行 namespace 中的字典）
    """
    namespace = {'__name__': 'extracted_namespace'}
    try:
        exec(file_content, namespace)
        return namespace.get('ENTITY_SCHEMAS', {})
    except Exception as e:
        logger.error(f"提取 ENTITY_SCHEMAS 失败：{e}")
        return {}


def git_show(ref_file: str) -> Optional[str]:
    """从 git ref 中提取文件内容

    Args:
        ref_file: 'origin/main:path/to/file' 形式

    Returns:
        文件内容字符串，失败返回 None
    """
    try:
        result = subprocess.run(
            ['git', 'show', ref_file],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            logger.error(f"git show {ref_file} 失败：{result.stderr}")
            return None
        return result.stdout
    except Exception as e:
        logger.error(f"git show 异常：{e}")
        return None


def run_ci_check(
    before: dict,
    after: dict,
    threshold: int = 80,
    output_format: str = 'text',
) -> int:
    """运行 CI 校验

    Args:
        before: 旧 ENTITY_SCHEMAS
        after: 新 ENTITY_SCHEMAS
        threshold: 兼容性阈值（< threshold 阻止 PR）
        output_format: text / json / markdown

    Returns:
        int: 退出码（0 = pass, 1 = fail）
    """
    from .diff import diff_schemas, format_markdown_report

    diff = diff_schemas(before, after)
    score = diff['score']
    passed = score >= threshold

    if output_format == 'json':
        import json
        print(json.dumps(diff, indent=2, ensure_ascii=False))
    elif output_format == 'markdown':
        print(format_markdown_report(diff))
    else:
        # text 格式
        level = '[OK] PASS' if passed else '[X] FAIL'
        print(f'{level} | Score: {score}/100 | Threshold: {threshold}')
        print()
        print(f'Breaking changes: {len(diff["breaking_changes"])}')
        for change in diff['breaking_changes']:
            print(f'  - {change}')
        if not passed:
            print()
            print('To override, ask maintainer to add label "schema-override".')

    return 0 if passed else 1


def main():
    """CLI 入口"""
    parser = argparse.ArgumentParser(
        description='M13 Schema 治理 CI 校验',
    )
    parser.add_argument(
        '--before',
        required=True,
        help='旧版本 git ref（如 origin/main:meta/graphql/__init__.py）',
    )
    parser.add_argument(
        '--after',
        required=True,
        help='新版本 git ref（如 HEAD:meta/graphql/__init__.py）',
    )
    parser.add_argument(
        '--threshold',
        type=int,
        default=80,
        help='兼容性阈值（默认 80）',
    )
    parser.add_argument(
        '--format',
        choices=['text', 'json', 'markdown'],
        default='text',
        help='输出格式（默认 text）',
    )
    parser.add_argument(
        '--file',
        action='store_true',
        help='after 是本地文件路径而非 git ref',
    )

    args = parser.parse_args()

    # 提取 before
    before_content = git_show(args.before)
    if before_content is None:
        print(f'ERROR: 无法获取 {args.before}', file=sys.stderr)
        sys.exit(2)

    # 提取 after
    if args.file:
        after_path = Path(args.after)
        if not after_path.is_file():
            print(f'ERROR: 文件不存在 {args.after}', file=sys.stderr)
            sys.exit(2)
        after_content = after_path.read_text(encoding='utf-8')
    else:
        after_content = git_show(args.after)
        if after_content is None:
            print(f'ERROR: 无法获取 {args.after}', file=sys.stderr)
            sys.exit(2)

    # 解析 ENTITY_SCHEMAS
    before = extract_entity_schemas_from_file(before_content)
    after = extract_entity_schemas_from_file(after_content)

    if not after:
        print('WARNING: 新版本未找到 ENTITY_SCHEMAS', file=sys.stderr)

    # 运行校验
    exit_code = run_ci_check(
        before, after,
        threshold=args.threshold,
        output_format=args.format,
    )
    sys.exit(exit_code)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()

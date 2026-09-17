#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pre_deploy_validator.py - 部署前通用校验编排器

设计原则 (无开发假设):
  - 不假设具体部署目标 / 文件类型 / 项目结构
  - 插件式校验器: 每个 checker 是可独立调用的纯函数
  - 默认包含 SQL vs DB schema 检查 (via code_db_compat_check)
  - 失败时返回结构化报告, 由调用方决定是否阻断

用法:
  # 基础: 跑默认检查 (SQL vs DB)
  python pre_deploy_validator.py --files f1.py f2.py --db db.sqlite

  # 跳过某类检查
  python pre_deploy_validator.py --files f1.py --db db.sqlite --skip code_db_compat

  # JSON 输出 + 退出码
  python pre_deploy_validator.py --files f1.py --db db.sqlite --json --exit-code

  # 集成到 deploy_upload (内部调用)
  from pre_deploy_validator import validate_files
  report = validate_files(files, db_path, force=force)
  if not report['ok'] and not force:
      return 2

可扩展:
  - 添加新 checker: 实现 BaseChecker 接口, 注册到 DEFAULT_CHECKERS
  - 跳过 / 启用: --enable / --skip

[2026-09-16] P0-2 通用化基础设施
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable, List, Optional

# 让 tools/ 成为 import root
sys.path.insert(0, str(Path(__file__).parent))


# --------------------------------------------------------------------------
# Checker 接口
# --------------------------------------------------------------------------
class BaseChecker:
    """Checker 抽象基类: 输入文件 + 上下文, 返回 issues 列表."""

    name: str = "base"
    description: str = ""

    def run(self, files: List[Path], context: dict) -> dict:
        """返回 {'checker': str, 'issues': [issue_dict, ...], 'stats': {...}}.

        issue_dict: {file, line, table, column, reason, severity}
        severity ∈ {'error', 'warning', 'info'}
        """
        raise NotImplementedError


class CodeDBChecker(BaseChecker):
    """[P0-1] SQL 列引用 vs DB schema 检查."""

    name = "code_db_compat"
    description = "SQL 列引用 vs DB schema 兼容性检查 (AST + sqlparse)"

    def run(self, files: List[Path], context: dict) -> dict:
        # 动态 import 避免硬依赖 sqlparse
        try:
            from code_db_compat_check import check_compatibility
        except ImportError as e:
            return {
                'checker': self.name,
                'issues': [{
                    'severity': 'error',
                    'file': '<validator>',
                    'line': 0,
                    'reason': f'failed to import code_db_compat_check: {e}',
                }],
                'stats': {'imported': False},
            }

        db_path = context.get('db_path')
        if not db_path:
            return {
                'checker': self.name,
                'issues': [{
                    'severity': 'warning',
                    'file': '<validator>',
                    'line': 0,
                    'reason': 'no db_path in context, skip code_db_compat',
                }],
                'stats': {'skipped': True},
            }

        if not Path(db_path).exists():
            return {
                'checker': self.name,
                'issues': [{
                    'severity': 'warning',
                    'file': '<validator>',
                    'line': 0,
                    'reason': f'db_path not found: {db_path}, skip',
                }],
                'stats': {'skipped': True, 'db_path': str(db_path)},
            }

        result = check_compatibility(files, Path(db_path))
        # 转换为统一 issue 格式
        issues = []
        for it in result.get('compatibility_issues', []):
            issues.append({
                'severity': 'error',
                'file': it.get('file'),
                'line': it.get('line'),
                'table': it.get('table'),
                'column': it.get('column'),
                'op': it.get('op'),
                'reason': it.get('reason'),
                'sql_snippet': it.get('sql_snippet', '')[:200],
            })

        return {
            'checker': self.name,
            'issues': issues,
            'stats': {
                'db_path': result.get('db_path'),
                'db_tables_count': result.get('db_tables_count'),
                'sql_strings_extracted': result.get('stats', {}).get('sql_strings_extracted'),
                'refs_extracted': result.get('stats', {}).get('refs_extracted'),
            },
        }


# 默认 checker 注册表 (按顺序执行)
DEFAULT_CHECKERS: List[BaseChecker] = [
    CodeDBChecker(),
]


# --------------------------------------------------------------------------
# 主入口
# --------------------------------------------------------------------------
def validate_files(
    files: List[Path],
    db_path: Optional[Path] = None,
    enabled: Optional[List[str]] = None,
    skipped: Optional[List[str]] = None,
) -> dict:
    """跑启用的 checker, 返回聚合报告.

    Args:
        files: 要校验的本地文件列表
        db_path: DB schema 路径 (用于 CodeDBChecker)
        enabled: 仅跑这些 checker (None=全部)
        skipped: 跳过这些 checker

    Returns:
        {
            'ok': bool,                    # 全部 issues 都通过 (无 error)
            'files': [str, ...],
            'checkers_run': [name, ...],
            'results': [checker_result, ...],
            'total_issues': int,
            'error_issues': int,
            'warning_issues': int,
        }
    """
    skipped = set(skipped or [])
    enabled_set = set(enabled) if enabled else None

    context = {
        'db_path': str(db_path) if db_path else None,
    }

    all_results = []
    checkers_run = []
    total_issues = 0
    error_issues = 0
    warning_issues = 0

    for checker in DEFAULT_CHECKERS:
        if checker.name in skipped:
            continue
        if enabled_set is not None and checker.name not in enabled_set:
            continue

        result = checker.run(files, context)
        all_results.append(result)
        checkers_run.append(checker.name)

        for issue in result.get('issues', []):
            total_issues += 1
            if issue.get('severity') == 'error':
                error_issues += 1
            elif issue.get('severity') == 'warning':
                warning_issues += 1

    ok = error_issues == 0

    return {
        'ok': ok,
        'files': [str(f) for f in files],
        'checkers_run': checkers_run,
        'results': all_results,
        'total_issues': total_issues,
        'error_issues': error_issues,
        'warning_issues': warning_issues,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _print_human(report: dict) -> None:
    print(f"[validator] files={len(report['files'])}, "
          f"checkers={report['checkers_run']}")
    print(f"[validator] issues: total={report['total_issues']}, "
          f"error={report['error_issues']}, warning={report['warning_issues']}")
    print()
    for result in report['results']:
        print(f"=== checker: {result['checker']} ===")
        print(f"    stats: {json.dumps(result.get('stats', {}), ensure_ascii=False)}")
        issues = result.get('issues', [])
        if not issues:
            print(f"    [OK] no issues")
        else:
            for i, iss in enumerate(issues[:50], 1):
                sev = iss.get('severity', '?').upper()
                print(f"    [{sev}] {i}. {iss.get('file', '?')}:{iss.get('line', 0)}")
                print(f"        reason: {iss.get('reason')}")
                if 'table' in iss and iss['table']:
                    print(f"        table={iss.get('table')}, column={iss.get('column')}")
                if 'sql_snippet' in iss and iss['sql_snippet']:
                    print(f"        sql: {iss['sql_snippet'][:120]}")
        if len(issues) > 50:
            print(f"    ... and {len(issues) - 50} more issues")
        print()


def main():
    parser = argparse.ArgumentParser(
        description='[P0-2] 部署前通用校验编排器 (无开发假设, 可扩展)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python pre_deploy_validator.py --files meta/scripts/init_auth.py --db db.sqlite
  python pre_deploy_validator.py --files f1.py f2.py --db db.sqlite --json --exit-code
  python pre_deploy_validator.py --files f1.py --db db.sqlite --skip code_db_compat
        """
    )
    parser.add_argument('--files', nargs='+', required=True,
                        help='要校验的本地文件列表')
    parser.add_argument('--db', default=None,
                        help='SQLite DB 路径 (供 code_db_compat checker 使用)')
    parser.add_argument('--enable', nargs='+', default=None,
                        help='仅启用这些 checker (默认全部)')
    parser.add_argument('--skip', nargs='+', default=None,
                        help='跳过这些 checker')
    parser.add_argument('--json', action='store_true', help='JSON 输出')
    parser.add_argument('--exit-code', action='store_true', help='不通过时 exit 1')

    args = parser.parse_args()

    files = [Path(f).resolve() for f in args.files]
    db_path = Path(args.db).resolve() if args.db else None

    report = validate_files(
        files=files,
        db_path=db_path,
        enabled=args.enable,
        skipped=args.skip,
    )

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_human(report)

    if args.exit_code and not report['ok']:
        sys.exit(1)
    sys.exit(0 if report['ok'] else (1 if args.exit_code else 0))


if __name__ == '__main__':
    main()
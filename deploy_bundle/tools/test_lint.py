# -*- coding: utf-8 -*-
"""
[TOOL] test_lint.py - AI Agent 测试反模式静态检查器
[DATE] 2026-06-15
[OWNER] AI Infra
[SCOPE] meta/tests/, tests/, test_helpers/

[USAGE]
    # 扫描默认目录
    python tools/test_lint.py

    # 扫描指定目录
    python tools/test_lint.py --target meta/tests/

    # 严格模式 (HIGH 级别返回 exit code 1)
    python tools/test_lint.py --strict

    # 输出 JSON (供 CI 解析)
    python tools/test_lint.py --json
"""
import ast
import os
import re
import sys
import json
import argparse
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field, asdict
from enum import Enum


# ========================================================================
# 配置
# ========================================================================

DEFAULT_TARGETS = [
    'meta/tests/',
    'tests/unit/',
    'tests/integration/',
    'tests/e2e/',
    'tests/diagnostics/',
]

PROJECT_ROOT = Path('d:/filework/excel-to-diagram')


class Severity(str, Enum):
    HIGH = 'HIGH'      # 严格模式会拦截
    MEDIUM = 'MEDIUM'  # WARN
    LOW = 'LOW'        # INFO


@dataclass
class Issue:
    severity: str
    code: str
    file: str
    line: int
    message: str
    suggestion: str


# ========================================================================
# 检查器
# ========================================================================

def check_time_sleep(tree: ast.AST, file_path: str) -> List[Issue]:
    """[HIGH] time.sleep / asyncio.sleep 在测试中"""
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            # time.sleep(3)
            if isinstance(func, ast.Attribute) and func.attr in ('sleep', 'wait_for_timeout'):
                # 排除合法用法: time.sleep(0) / 'wait_for_stable' (项目自定义)
                target = ast.unparse(func) if hasattr(ast, 'unparse') else ''
                if 'wait_for_stable' in target:
                    continue
                if isinstance(node, ast.Call) and node.args:
                    arg = node.args[0]
                    # sleep(0) 是合法的
                    if isinstance(arg, ast.Constant) and arg.value == 0:
                        continue
                line = node.lineno
                issues.append(Issue(
                    severity=Severity.HIGH,
                    code='TEST001',
                    file=file_path,
                    line=line,
                    message=f'{target}() is hardcoded wait',
                    suggestion='Use wait_for_selector() or wait_for_stable()'
                ))
    return issues


def check_sqlite_direct(tree: ast.AST, file_path: str) -> List[Issue]:
    """[HIGH] sqlite3.connect() 直连 DB (绕过 ORM)"""
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == 'connect':
                # sqlite3.connect(...)
                target = ast.unparse(func) if hasattr(ast, 'unparse') else ''
                if 'sqlite' in target.lower():
                    line = node.lineno
                    issues.append(Issue(
                        severity=Severity.HIGH,
                        code='TEST002',
                        file=file_path,
                        line=line,
                        message=f'{target}() direct DB access in test',
                        suggestion='Use record_view() fixture (Phase 2) or ORM'
                    ))
    return issues


def check_hardcoded_product_name(tree: ast.AST, file_path: str) -> List[Issue]:
    """[MEDIUM] 硬编码产品名 (如 '测试产品_TEST_PROD_DBBCAB')"""
    issues = []
    pattern = re.compile(r'[\u4e00-\u9fa5]+_[A-Z0-9]{6,}')
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if pattern.search(node.value):
                line = node.lineno
                issues.append(Issue(
                    severity=Severity.MEDIUM,
                    code='TEST003',
                    file=file_path,
                    line=line,
                    message=f'Hardcoded test data: {node.value[:50]}',
                    suggestion='Use test_data_inventory.json or factory'
                ))
    return issues


def check_print_in_test(tree: ast.AST, file_path: str) -> List[Issue]:
    """[MEDIUM] 测试中用 print() (应该用 logger 或 -s)"""
    issues = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == 'print':
                line = node.lineno
                issues.append(Issue(
                    severity=Severity.MEDIUM,
                    code='TEST004',
                    file=file_path,
                    line=line,
                    message='print() in test (bypasses pytest -s)',
                    suggestion='Use logger.debug() or pytest -s'
                ))
    return issues


def check_bare_requests(tree: ast.AST, file_path: str) -> List[Issue]:
    """[LOW] requests.get() 没 try/except"""
    issues = []
    # 简化: 只标记 requests.get/post, 完整检查 try/except 嵌套需更深分析
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr in ('get', 'post', 'put', 'delete'):
                target = ast.unparse(func) if hasattr(ast, 'unparse') else ''
                if 'requests' in target:
                    line = node.lineno
                    # 简化: 仅提示, 不强阻断
                    issues.append(Issue(
                        severity=Severity.LOW,
                        code='TEST005',
                        file=file_path,
                        line=line,
                        message=f'{target}() without explicit try/except',
                        suggestion='Wrap in try/except requests.RequestException'
                    ))
    return issues


def check_duplicate_prefix(file_paths: List[str]) -> List[Issue]:
    """[LOW] 同前缀文件 ≥ 3 个 (1-shot 脚本散落)"""
    issues = []
    prefix_count: Dict[str, List[str]] = {}
    for fp in file_paths:
        name = Path(fp).name
        # 提取 test_xxx_ 前缀 (去掉末尾数字/版本)
        match = re.match(r'^(test_[a-z_]+?)(_\d+|_v\d+|_final|_debug)?\.py$', name)
        if match:
            prefix = match.group(1)
            prefix_count.setdefault(prefix, []).append(fp)
    
    for prefix, files in prefix_count.items():
        if len(files) >= 3:
            issues.append(Issue(
                severity=Severity.LOW,
                code='TEST006',
                file=','.join(files[:3]),
                line=0,
                message=f'{len(files)} files with prefix "{prefix}" (likely 1-shot scripts)',
                suggestion='Consolidate to tests/diagnostics/ or delete obsolete'
            ))
    return issues


# ========================================================================
# 入口
# ========================================================================

CHECKS = [
    check_time_sleep,
    check_sqlite_direct,
    check_hardcoded_product_name,
    check_print_in_test,
    check_bare_requests,
]


def scan_file(file_path: str) -> List[Issue]:
    """扫描单个 .py 文件"""
    try:
        content = Path(file_path).read_text(encoding='utf-8')
        tree = ast.parse(content, filename=file_path)
    except (SyntaxError, UnicodeDecodeError) as e:
        return [Issue(
            severity=Severity.LOW,
            code='TEST000',
            file=file_path,
            line=0,
            message=f'Parse error: {e}',
            suggestion='Fix syntax'
        )]
    
    issues = []
    for check in CHECKS:
        issues.extend(check(tree, file_path))
    return issues


def scan_directory(target_dir: str) -> Tuple[List[Issue], List[str]]:
    """扫描目录下的所有 .py 文件 (或单文件)"""
    target = PROJECT_ROOT / target_dir if not Path(target_dir).is_absolute() else Path(target_dir)
    
    py_files = []
    if target.is_file() and target.suffix == '.py':
        # 单文件模式
        py_files.append(str(target))
    elif target.exists() and target.is_dir():
        # 目录递归
        for root, _, files in os.walk(target):
            for f in files:
                if f.endswith('.py'):
                    py_files.append(str(Path(root) / f))
    else:
        return [], []
    
    all_issues = []
    for fp in py_files:
        all_issues.extend(scan_file(fp))
    
    # 全局检查 (跨文件)
    all_issues.extend(check_duplicate_prefix(py_files))
    
    return all_issues, py_files


def main():
    parser = argparse.ArgumentParser(
        description='AI Agent test anti-pattern static checker',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--target', action='append', help='Target directory (can repeat)')
    parser.add_argument('--strict', action='store_true', help='Exit 1 on HIGH severity')
    parser.add_argument('--json', action='store_true', help='JSON output')
    args = parser.parse_args()
    
    targets = args.target if args.target else DEFAULT_TARGETS
    
    all_issues = []
    total_files = 0
    for t in targets:
        issues, files = scan_directory(t)
        all_issues.extend(issues)
        total_files += len(files)
    
    # 按严重度排序
    severity_order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    all_issues.sort(key=lambda i: (severity_order.get(i.severity, 3), i.file, i.line))
    
    if args.json:
        print(json.dumps({
            'total_files': total_files,
            'total_issues': len(all_issues),
            'issues': [asdict(i) for i in all_issues],
        }, indent=2, ensure_ascii=False))
    else:
        print(f'[test_lint] Scanned {total_files} files in {len(targets)} directories')
        print(f'[test_lint] Found {len(all_issues)} issues')
        print()
        
        by_severity: Dict[str, List[Issue]] = {s: [] for s in Severity}
        for issue in all_issues:
            by_severity[issue.severity].append(issue)
        
        for sev in [Severity.HIGH, Severity.MEDIUM, Severity.LOW]:
            issues = by_severity[sev]
            if not issues:
                continue
            print(f'=== {sev} ({len(issues)}) ===')
            for i in issues:
                rel_path = i.file.replace(str(PROJECT_ROOT) + '/', '')
                print(f'  [{i.code}] {rel_path}:{i.line}')
                print(f'    {i.message}')
                print(f'    -> {i.suggestion}')
            print()
        
        if not all_issues:
            print('[OK] No anti-patterns detected')
    
    # 退出码
    if args.strict and any(i.severity == Severity.HIGH for i in all_issues):
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())

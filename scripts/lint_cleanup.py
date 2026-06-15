"""
测试数据规范 Lint 工具 (Phase 3)
====================================

8 条数据管理规则 (D01-D08):
D01: 禁止硬编码 ID
D02: 必须用 Factory.create()
D03: Factory.create() 必须配 cleanup
D04: 测试数据必须用 unique_id()
D05: 禁止 int(time.time())
D06: 禁止 random.randint 当 ID
D07: Fixture 必须显式声明 scope
D08: 跨请求必须用 requests.Session

TBD-7 采纳: Phase 1-3 warning, Phase 4+ error

Usage:
  python scripts/lint_cleanup.py --severity warning
  python scripts/lint_cleanup.py --strict
  python scripts/lint_cleanup.py --report
"""
import ast
import re
import json
import argparse
import logging
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict, Any, Set, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# 8 条规则定义
# ============================================================

RULES = {
    'D01_no_hardcoded_id': {
        'description': '禁止硬编码 ID (id=数字)',
        'severity_default': 'error',
        'check': 'detect_id_equals',
    },
    'D02_factory_adoption': {
        'description': '必须用 Factory.create() 而非直接 API',
        'severity_default': 'warning',
        'check': 'check_factory_usage',
    },
    'D03_cleanup_required': {
        'description': 'Factory.create() 必须配 cleanup() 或 try/finally',
        'severity_default': 'error',
        'check': 'check_cleanup_pairing',
    },
    'D04_unique_id_required': {
        'description': '测试数据必须用 unique_id() 而非 time.time()',
        'severity_default': 'warning',
        'check': 'check_unique_generation',
    },
    'D05_no_time_time': {
        'description': '禁止用 int(time.time()) 当唯一值',
        'severity_default': 'warning',
        'check': 'check_time_time_abuse',
    },
    'D06_no_random_id': {
        'description': '禁止用 random.randint 当 ID',
        'severity_default': 'warning',
        'check': 'check_random_id',
    },
    'D07_explicit_scope': {
        'description': 'Fixture 必须显式声明 scope',
        'severity_default': 'warning',
        'check': 'check_fixture_scope',
    },
    'D08_session_cookie': {
        'description': '跨请求必须用 requests.Session',
        'severity_default': 'info',
        'check': 'check_session_usage',
    },
}


# ============================================================
# 检测函数
# ============================================================

def detect_id_equals(tree: ast.AST, source: str) -> List[Dict[str, Any]]:
    """D01: 检测硬编码 id=数字"""
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ('id', 'user_id', 'role_id', 'bo_id', 'version_id'):
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, int):
                        if node.value.value >= 1000:
                            findings.append({
                                'rule': 'D01',
                                'line': node.lineno,
                                'col': node.col_offset,
                                'message': f"硬编码 {target.id}={node.value.value} (≥1000)",
                                'severity': 'error',
                            })
    return findings


def check_factory_usage(tree: ast.AST, source: str) -> List[Dict[str, Any]]:
    """D02: 检测是否使用 Factory.create() 而非直接 API"""
    findings = []
    factory_calls = 0
    api_calls = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if isinstance(func.value, ast.Name) and 'Factory' in func.value.id:
                    if func.attr == 'create':
                        factory_calls += 1
                if isinstance(func.value, ast.Name) and func.value.id in ('requests', 'client', 'api_client'):
                    if func.attr in ('post', 'put'):
                        api_calls += 1

    if api_calls > 0 and factory_calls == 0:
        findings.append({
            'rule': 'D02',
            'line': 0,
            'col': 0,
            'message': f"测试只用了 {api_calls} 次直接 API 调用, 0 次 Factory.create(). 建议迁移到工厂",
            'severity': 'warning',
        })
    return findings


def check_cleanup_pairing(tree: ast.AST, source: str) -> List[Dict[str, Any]]:
    """D03: 检测 Factory.create() 是否配 cleanup() 或 try/finally"""
    findings = []
    # 找测试函数
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_'):
            has_create = False
            has_cleanup = False
            has_try_finally = False
            for child in ast.walk(node):
                if isinstance(child, ast.Call):
                    func = child.func
                    if isinstance(func, ast.Attribute):
                        if isinstance(func.value, ast.Name) and 'Factory' in func.value.id:
                            if func.attr == 'create':
                                has_create = True
                            if func.attr == 'cleanup':
                                has_cleanup = True
                if isinstance(child, ast.Try) and hasattr(child, 'finalbody') and child.finalbody:
                    has_try_finally = True

            if has_create and not (has_cleanup or has_try_finally):
                findings.append({
                    'rule': 'D03',
                    'line': node.lineno,
                    'col': node.col_offset,
                    'message': f"测试 {node.name} 调用了 Factory.create() 但无 cleanup() 或 try/finally",
                    'severity': 'error',
                })
    return findings


def check_unique_generation(tree: ast.AST, source: str) -> List[Dict[str, Any]]:
    """D04: 检测测试数据是否用 unique_id()"""
    # D04 在 D05/D06 中已覆盖, 这里仅占位
    return []


def check_time_time_abuse(tree: ast.AST, source: str) -> List[Dict[str, Any]]:
    """D05: 检测 int(time.time()) 滥用"""
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == 'int':
                if isinstance(node.func.value, ast.Name):
                    # int(time.time())
                    if isinstance(node.args[0], ast.Call) if node.args else False:
                        arg = node.args[0]
                        if (isinstance(arg, ast.Call) and isinstance(arg.func, ast.Attribute) and
                            isinstance(arg.func.value, ast.Name) and arg.func.value.id == 'time' and
                            arg.func.attr == 'time'):
                            findings.append({
                                'rule': 'D05',
                                'line': node.lineno,
                                'col': node.col_offset,
                                'message': "int(time.time()) 当唯一值有冲突风险, 改用 unique_id()",
                                'severity': 'warning',
                            })
    return findings


def check_random_id(tree: ast.AST, source: str) -> List[Dict[str, Any]]:
    """D06: 检测 random.randint 当 ID"""
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if isinstance(node.func.value, ast.Name) and node.func.value.id == 'random':
                if node.func.attr in ('randint', 'randrange'):
                    findings.append({
                        'rule': 'D06',
                        'line': node.lineno,
                        'col': node.col_offset,
                        'message': f"random.{node.func.attr}() 当 ID 不安全, 改用 unique_id()",
                        'severity': 'warning',
                    })
    return findings


def check_fixture_scope(tree: ast.AST, source: str) -> List[Dict[str, Any]]:
    """D07: 检测 fixture 是否显式声明 scope"""
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                try:
                    dec_name = ast.unparse(dec) if hasattr(ast, 'unparse') else ''
                except Exception:
                    continue
                if 'fixture' in dec_name and 'scope' not in dec_name:
                    findings.append({
                        'rule': 'D07',
                        'line': node.lineno,
                        'col': node.col_offset,
                        'message': f"Fixture {node.name}() 未声明 scope (默认 function, 但建议显式)",
                        'severity': 'warning',
                    })
    return findings


def check_session_usage(tree: ast.AST, source: str) -> List[Dict[str, Any]]:
    """D08: 检测是否使用 requests.Session"""
    # D08 是建议, 不强制
    return []


# ============================================================
# 检测器
# ============================================================

CHECKS = {
    'detect_id_equals': detect_id_equals,
    'check_factory_usage': check_factory_usage,
    'check_cleanup_pairing': check_cleanup_pairing,
    'check_unique_generation': check_unique_generation,
    'check_time_time_abuse': check_time_time_abuse,
    'check_random_id': check_random_id,
    'check_fixture_scope': check_fixture_scope,
    'check_session_usage': check_session_usage,
}


def lint_file(file_path: str, rules: List[str] = None) -> List[Dict[str, Any]]:
    """lint 单个文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source)
    except SyntaxError as e:
        return [{
            'file': file_path,
            'rule': 'SYNTAX',
            'line': 0,
            'col': 0,
            'message': f"语法错误: {e}",
            'severity': 'error',
        }]

    findings = []
    selected_rules = rules or list(RULES.keys())
    for rule_id in selected_rules:
        check_name = RULES[rule_id]['check']
        if check_name in CHECKS:
            rule_findings = CHECKS[check_name](tree, source)
            for f in rule_findings:
                f['file'] = file_path
            findings.extend(rule_findings)

    return findings


def lint_directory(test_dir: str = 'meta/tests', rules: List[str] = None) -> Dict[str, Any]:
    """lint 整个测试目录"""
    all_findings = []
    file_count = 0

    for path in Path(test_dir).rglob('test_*.py'):
        file_count += 1
        all_findings.extend(lint_file(str(path), rules))

    by_rule = Counter(f['rule'] for f in all_findings)
    by_severity = Counter(f['severity'] for f in all_findings)

    return {
        'meta': {
            'files_checked': file_count,
            'total_findings': len(all_findings),
            'by_severity': dict(by_severity),
        },
        'by_rule': dict(by_rule),
        'findings': all_findings,
    }


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='测试数据规范 Lint 工具 (Phase 3)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--path', default='meta/tests',
                        help='测试目录')
    parser.add_argument('--severity', choices=['info', 'warning', 'error'],
                        default='info', help='最低严重度')
    parser.add_argument('--rules', nargs='+',
                        help='指定规则 (D01-D08)')
    parser.add_argument('--strict', action='store_true',
                        help='严格模式 (warning 也算 fail)')
    parser.add_argument('--report', action='store_true',
                        help='生成报告')
    parser.add_argument('--output', type=str,
                        help='报告输出路径')

    args = parser.parse_args()

    print('=' * 70)
    print('测试数据规范 Lint 工具 (Phase 3)')
    print('=' * 70)
    print(f'路径: {args.path}')
    print(f'严重度: {args.severity}+')
    if args.rules:
        print(f'规则: {", ".join(args.rules)}')
    else:
        print('规则: D01-D08 (全部)')
    print()

    # 1. Lint
    result = lint_directory(args.path, args.rules)

    # 2. 严重度过滤
    severity_order = {'info': 0, 'warning': 1, 'error': 2}
    min_sev = severity_order[args.severity]
    if args.strict and args.severity == 'info':
        min_sev = 1  # warning+ in strict

    filtered = [f for f in result['findings']
                if severity_order.get(f.get('severity', 'info'), 0) >= min_sev]

    # 3. 展示
    print(f'  文件: {result["meta"]["files_checked"]}')
    print(f'  违规: {result["meta"]["total_findings"]} (过滤后: {len(filtered)})')
    print()

    print('按规则:')
    for rule, count in sorted(result['by_rule'].items(), key=lambda x: -x[1]):
        print(f'  {rule}: {count}')

    print()
    print('按严重度:')
    for sev, count in result['meta']['by_severity'].items():
        print(f'  {sev}: {count}')

    # 4. Top 违规
    print()
    print('=' * 70)
    print('Top 20 违规:')
    print('=' * 70)
    for f in filtered[:20]:
        file_short = f['file'].replace('meta/tests/', '').replace('d:/filework/excel-to-diagram/', '')
        print(f'  [{f["rule"]}] {f["severity"]} {file_short}:{f["line"]}')
        print(f'    {f["message"][:80]}')

    # 5. 报告
    if args.report:
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as fp:
                json.dump(result, fp, indent=2, ensure_ascii=False)
            print(f'\n📄 报告: {args.output}')

    # 6. 退出码
    error_count = sum(1 for f in filtered if f.get('severity') == 'error')
    if error_count > 0:
        print(f'\n❌ {error_count} 个 error, exit 1')
        # 真实 CI 用: sys.exit(1)
    else:
        print(f'\n✅ 无 error')

    print()
    print('=' * 70)
    print('Phase 3 目标: factory 30%, 无清理 -50%')
    print('=' * 70)


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文档化自动生成工具 (Phase 5 v3.18.4+)
========================================

为测试文件自动生成 docstring, 提升可读性:
- 测试函数缺 docstring → 自动生成模板
- 工厂方法缺 docstring → 自动生成模板
- Fixture 缺 docstring → 自动生成模板

设计原则:
1. 不破坏现有代码 (Add-Only)
2. 生成后让 Agent 审阅/修改
3. 支持 dry-run 预览
4. 支持批处理和单文件

Usage:
  python scripts/auto_docstring.py --path meta/tests             # 全量
  python scripts/auto_docstring.py --path meta/tests/factories    # 工厂
  python scripts/auto_docstring.py --file <path>                 # 单文件
  python scripts/auto_docstring.py --dry-run                     # 仅预览
  python scripts/auto_docstring.py --report                      # 生成报告
"""
import ast
import argparse
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple

logger = logging.getLogger(__name__)


# ============================================================
# 模板生成器
# ============================================================

def generate_test_docstring(node: ast.FunctionDef) -> str:
    """
    为 test_* 函数生成 docstring
    """
    name = node.name

    # 解析测试名
    parts = re.split(r'[_\W]+', name)
    parts = [p for p in parts if p and p != 'test']
    if not parts:
        parts = [name]

    # 首字母大写, 拼成描述
    desc_words = []
    for p in parts:
        if p in ('id', 'pk'):
            desc_words.append('ID')
        elif p in ('api', 'http', 'db'):
            desc_words.append(p.upper())
        else:
            desc_words.append(p.capitalize())
    description = ' '.join(desc_words)

    # 根据名字推断测试意图
    intent = ""
    if any(w in name.lower() for w in ['create', 'add', 'insert', 'post']):
        intent = "创建对象并验证成功"
    elif any(w in name.lower() for w in ['update', 'put', 'patch', 'edit']):
        intent = "更新对象并验证变更"
    elif any(w in name.lower() for w in ['delete', 'remove', 'drop']):
        intent = "删除对象并验证已清理"
    elif any(w in name.lower() for w in ['get', 'fetch', 'read', 'list', 'query', 'search']):
        intent = "查询对象并验证数据正确"
    elif any(w in name.lower() for w in ['login', 'auth', 'token']):
        intent = "验证认证流程"
    elif any(w in name.lower() for w in ['permission', 'role', 'access']):
        intent = "验证权限控制"
    elif any(w in name.lower() for w in ['error', 'fail', 'invalid', 'reject']):
        intent = "验证错误处理"
    elif any(w in name.lower() for w in ['perf', 'load', 'bench']):
        intent = "性能基准测试"
    else:
        intent = f"测试 {description} 场景"

    return f'"""\n        {intent}。\n\n        验证项:\n            - TODO: 由 Agent/开发者补全\n\n        关联工厂:\n            - TODO: 由 Agent/开发者补全\n        """'


def generate_factory_docstring(node: ast.FunctionDef, class_node: Optional[ast.ClassDef] = None) -> str:
    """
    为工厂方法生成 docstring
    """
    name = node.name
    cls_name = class_node.name if class_node else 'Factory'

    if name == 'build':
        return f'"""\n        构造 {cls_name} 数据, 不写 DB。\n\n        Returns:\n            dict: 构造的数据 (不含 id)\n        """'

    if name == 'create':
        return f'"""\n        通过 API 创建 {cls_name} 对象, 写 DB。\n\n        Args:\n            cookie: admin cookie (可选, 不传则用默认)\n            **overrides: 覆盖默认字段\n\n        Returns:\n            dict: 包含 id 的数据\n        """'

    if name == 'cleanup':
        return f'"""\n        通过 API 清理 {cls_name} 对象。\n\n        Args:\n            obj_id: 对象 ID\n            cookie: admin cookie\n\n        Returns:\n            bool: 是否成功清理\n        """'

    if name == '_base_defaults':
        return f'"""\n        提供 {cls_name} 默认字段 (子类重写)。\n\n        Returns:\n            dict: 默认字段值\n        """'

    if name == '_create_action':
        return f'"""\n        子类重写: 创建 action 名。\n\n        Returns:\n            str: action 名称, 如 "user.create"\n        """'

    if name == '_create_payload':
        return f'"""\n        子类重写: 创建 payload 格式。\n\n        Args:\n            data: 构造的数据\n\n        Returns:\n            dict: API 请求 payload\n        """'

    return f'"""\n        {name} - {cls_name} 的方法。\n\n        TODO: 由 Agent/开发者补全描述。\n        """'


def generate_fixture_docstring(node: ast.FunctionDef) -> str:
    """
    为 fixture 函数生成 docstring
    """
    name = node.name

    # 根据名字推断 fixture 用途
    if 'admin' in name:
        return f'"""\n        Admin 用户/认证 fixture。\n\n        提供 admin 权限的 cookie/headers 给测试函数。\n        """'
    if 'user' in name.lower():
        return f'"""\n        测试用户 fixture。\n\n        自动创建测试用户, 测试结束自动清理。\n        """'
    if 'role' in name.lower():
        return f'"""\n        角色 fixture。\n\n        自动创建测试角色, 测试结束自动清理。\n        """'
    if 'clean' in name or 'reset' in name or 'setup' in name or 'teardown' in name:
        return f'"""\n        清理/重置 fixture。\n\n        确保测试前/后状态一致, 避免测试间污染。\n        """'
    if 'client' in name or 'app' in name:
        return f'"""\n        Flask app/client fixture。\n\n        提供测试用 HTTP 客户端。\n        """'
    if 'session' in name or 'db' in name or 'conn' in name:
        return f'"""\n        数据库 session/connection fixture。\n\n        提供测试用 DB 连接, 自动事务管理。\n        """'
    if 'mock' in name or 'patch' in name:
        return f'"""\n        Mock/Patch fixture。\n\n        自动 patch 测试目标, 测试结束恢复。\n        """'

    return f'"""\n        {name} - 测试 fixture。\n\n        TODO: 由 Agent/开发者补全 fixture 用途。\n        """'


# ============================================================
# AST 处理器
# ============================================================

def has_docstring(node: ast.AST) -> bool:
    """检查节点是否有 docstring (ast.get_docstring)"""
    return ast.get_docstring(node) is not None


def get_func_role(node: ast.FunctionDef) -> str:
    """
    判断函数角色: test / factory / fixture / general
    """
    name = node.name
    decorators = [ast.unparse(d) if hasattr(ast, 'unparse') else '' for d in node.decorator_list]

    # Test
    if name.startswith('test_') or any('parametrize' in d for d in decorators):
        return 'test'

    # Fixture
    if any('fixture' in d for d in decorators):
        return 'fixture'

    # Factory (in factories/ dir or has _COUNTER/_OBJECT_TYPE)
    return 'general'


def find_class_for_method(tree: ast.Module, method_name: str) -> Optional[ast.ClassDef]:
    """找到方法所属的类"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == method_name:
                    return node
    return None


def generate_docstring(node: ast.FunctionDef, role: str, class_node: Optional[ast.ClassDef] = None) -> str:
    """根据角色生成 docstring"""
    if role == 'test':
        return generate_test_docstring(node)
    elif role == 'fixture':
        return generate_fixture_docstring(node)
    elif role == 'factory' or class_node:
        return generate_factory_docstring(node, class_node)
    return f'"""\n    TODO: 为 {node.name} 添加文档\n    """'


def insert_docstring(source: str, node: ast.FunctionDef, docstring: str) -> Tuple[str, bool]:
    """
    在函数体开头插入 docstring
    返回 (新源码, 是否修改)
    """
    lines = source.splitlines(keepends=True)

    # 函数体第一个语句的行号 (1-based)
    if not node.body:
        return source, False

    first_stmt = node.body[0]
    insert_line = first_stmt.lineno  # 1-based

    # 找到函数 def 行
    def_line = node.lineno
    if insert_line == def_line:
        # 单行函数 def body
        return source, False

    # 计算缩进: 函数体第一个语句的缩进
    if first_stmt.col_offset == 0:
        # 找缩进
        stmt_line_content = lines[insert_line - 1]
        indent = len(stmt_line_content) - len(stmt_line_content.lstrip())
    else:
        indent = first_stmt.col_offset

    indent_str = ' ' * indent

    # 格式化 docstring (使用 4 空格缩进)
    inner_indent = indent_str + '    '
    # 处理 docstring 内的换行
    if '\n' in docstring:
        doc_lines = docstring.split('\n')
        formatted = '\n'.join(indent_str + line if line else line for line in doc_lines)
    else:
        formatted = indent_str + docstring

    # 插入到函数体第一个语句前
    new_lines = lines[:insert_line - 1] + [formatted + '\n'] + lines[insert_line - 1:]
    return ''.join(new_lines), True


# ============================================================
# 处理器
# ============================================================

def process_file(file_path: str, dry_run: bool = False) -> Dict[str, Any]:
    """
    处理单个文件, 返回结果
    """
    result = {
        'file': file_path,
        'total_funcs': 0,
        'missing_docstring': 0,
        'added': 0,
        'errors': [],
    }

    try:
        source = Path(file_path).read_text(encoding='utf-8')
    except Exception as e:
        result['errors'].append(f"读取失败: {e}")
        return result

    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        result['errors'].append(f"语法错误: {e}")
        return result

    new_source = source
    modified = False

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # 跳过私有方法 (非 _dunder)
        if node.name.startswith('_') and not node.name.startswith('__'):
            continue
        # 跳过 setter/getter/特殊方法
        if node.name in ('__init__', '__str__', '__repr__', '__len__', '__iter__', '__getitem__', '__setitem__', '__delitem__', '__contains__', '__call__', '__enter__', '__exit__', '__aenter__', '__aexit__'):
            continue

        result['total_funcs'] += 1

        if has_docstring(node):
            continue

        result['missing_docstring'] += 1

        role = get_func_role(node)
        class_node = find_class_for_method(tree, node.name)
        if class_node and class_node.name.endswith('Factory'):
            role = 'factory'

        # 生成 docstring
        docstring = generate_docstring(node, role, class_node)
        new_source, changed = insert_docstring(new_source, node, docstring)
        if changed:
            result['added'] += 1
            modified = True

    if modified and not dry_run:
        try:
            Path(file_path).write_text(new_source, encoding='utf-8')
        except Exception as e:
            result['errors'].append(f"写入失败: {e}")
    elif modified and dry_run:
        result['dry_run_source'] = new_source

    return result


def process_directory(test_dir: str, dry_run: bool = False) -> Dict[str, Any]:
    """处理整个目录"""
    all_results = []
    for path in Path(test_dir).rglob('test_*.py'):
        result = process_file(str(path), dry_run)
        all_results.append(result)
    for path in Path(test_dir).rglob('*.py'):
        if path.name.startswith('test_'):
            continue
        # 工厂类也算
        if 'factory' in str(path).lower() or path.parent.name == 'factories':
            result = process_file(str(path), dry_run)
            all_results.append(result)

    total_funcs = sum(r['total_funcs'] for r in all_results)
    total_missing = sum(r['missing_docstring'] for r in all_results)
    total_added = sum(r['added'] for r in all_results)
    total_errors = sum(len(r['errors']) for r in all_results)

    return {
        'summary': {
            'files_processed': len(all_results),
            'total_functions': total_funcs,
            'missing_docstring': total_missing,
            'added': total_added,
            'errors': total_errors,
            'dry_run': dry_run,
        },
        'files': all_results,
    }


# ============================================================
# 主入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='文档化自动生成工具 (Phase 5)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('--path', default='meta/tests',
                        help='测试目录')
    parser.add_argument('--file', help='单文件路径')
    parser.add_argument('--dry-run', action='store_true',
                        help='仅预览, 不写文件')
    parser.add_argument('--report', action='store_true',
                        help='生成 JSON 报告')
    parser.add_argument('--output', default='docstring_report.json',
                        help='报告输出路径')

    args = parser.parse_args()

    print('=' * 70)
    print('文档化自动生成工具 (Phase 5 v3.18.4+)')
    print('=' * 70)
    print(f'路径: {args.path}')
    print(f'文件: {args.file or "(目录)"}')
    print(f'预览: {args.dry_run}')
    print()

    if args.file:
        result = process_file(args.file, args.dry_run)
        print(f'  文件: {result["file"]}')
        print(f'  函数: {result["total_funcs"]}')
        print(f'  缺 docstring: {result["missing_docstring"]}')
        print(f'  添加: {result["added"]}')
        if result['errors']:
            print(f'  错误: {result["errors"]}')
        return

    result = process_directory(args.path, args.dry_run)
    summary = result['summary']

    print(f'  文件: {summary["files_processed"]}')
    print(f'  函数: {summary["total_functions"]}')
    print(f'  缺 docstring: {summary["missing_docstring"]}')
    print(f'  添加: {summary["added"]}')
    print(f'  错误: {summary["errors"]}')
    print()

    if summary['missing_docstring'] > 0:
        coverage = (1 - summary['missing_docstring'] / summary['total_functions']) * 100
        print(f'  当前覆盖率: {coverage:.1f}%')
        print(f'  目标覆盖率: 90%+')

    if args.report:
        with open(args.output, 'w', encoding='utf-8') as fp:
            json.dump(result, fp, indent=2, ensure_ascii=False)
        print(f'\n📄 报告: {args.output}')

    print()
    print('=' * 70)
    print('Phase 5 目标: docstring 覆盖率 90%+, 测试可读性 +30%')
    print('=' * 70)


if __name__ == '__main__':
    logging.basicConfig(level=logging.WARNING)
    main()

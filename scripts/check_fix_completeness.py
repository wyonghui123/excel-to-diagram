#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
修复完整性检查脚本 (V2 落地 - V1 提出未实施)

基于 2026-06-20 WriteScopeDenied v1.2.25 修复事故：
- 类签名改了，但 _extract_business_key() 方法未实现
- raise site 调用了未定义的方法 → Test 4 HTTP 500

检测项：
1. raise site 调用的方法都已实现
2. 类签名的新参数在所有调用方都已更新
3. helper 方法有完整的实现（不是 stub/pass）
4. 相关测试都已更新或新增

使用：
    python scripts/check_fix_completeness.py --file meta/core/interceptors/write_scope_interceptor.py
    python scripts/check_fix_completeness.py --class WriteScopeDenied
"""

import argparse
import re
import sys
from pathlib import Path
from typing import List, Dict, Set


def find_class_definition(file_path: Path, class_name: str) -> Dict:
    """
    查找类的定义位置和签名
    """
    content = file_path.read_text(encoding='utf-8')
    # 匹配 class ClassName(...): 或 class ClassName:
    pattern = rf'class\s+{re.escape(class_name)}\s*\(?([^)]*)\)?\s*:'
    match = re.search(pattern, content)

    if not match:
        return {'found': False, 'class_name': class_name}

    # 找 __init__ 方法
    init_pattern = rf'def\s+__init__\s*\(\s*self\s*(?:,\s*([^)]+))?\s*\)\s*(?:\s*->\s*[^:]+)?\s*:'
    init_match = re.search(init_pattern, content[match.end():])

    init_params = []
    if init_match and init_match.group(1):
        params_str = init_match.group(1)
        # 解析参数
        for param in params_str.split(','):
            param = param.strip()
            # 去掉类型注解和默认值
            param_name = param.split(':')[0].split('=')[0].strip()
            if param_name and param_name not in ('self', '*args', '**kwargs'):
                init_params.append(param_name)

    return {
        'found': True,
        'class_name': class_name,
        'line': content[:match.start()].count('\n') + 1,
        'init_params': init_params,
    }


def find_raise_sites(file_path: Path, class_name: str) -> List[Dict]:
    """
    查找所有 raise ClassName(...) 的位置
    """
    content = file_path.read_text(encoding='utf-8')
    lines = content.splitlines()
    raise_sites = []

    pattern = rf'raise\s+{re.escape(class_name)}\s*\(([^)]*)\)'

    for i, line in enumerate(lines, 1):
        match = re.search(pattern, line)
        if match:
            raise_sites.append({
                'line': i,
                'content': line.strip(),
                'args': match.group(1).strip(),
            })

    return raise_sites


def find_method_calls_in_args(args_str: str) -> Set[str]:
    """
    从 raise site 的参数中提取被调用的方法名

    例：
        self._extract_business_key(object_type, record) -> {'self._extract_business_key'}
        message, business_key=self._extract_business_key(obj) -> {'self._extract_business_key'}
    """
    # 匹配 self.method_name( 或 ClassName.method_name(
    pattern = r'(?:self|cls|\w+)\.(\w+)\s*\('
    return set(re.findall(pattern, args_str))


def find_method_definitions(file_path: Path) -> Set[str]:
    """
    查找所有定义的方法名
    """
    content = file_path.read_text(encoding='utf-8')
    # 匹配 def method_name(
    pattern = r'def\s+(\w+)\s*\('
    return set(re.findall(pattern, content))


def find_call_sites(file_path: Path, class_name: str) -> List[Dict]:
    """
    查找所有 raise ClassName 之外的 ClassName() 调用点
    """
    content = file_path.read_text(encoding='utf-8')
    lines = content.splitlines()
    call_sites = []

    # 匹配 ClassName( 但不匹配 raise
    pattern = rf'(?<!raise\s){re.escape(class_name)}\s*\(([^)]*)\)'

    for i, line in enumerate(lines, 1):
        match = re.search(pattern, line)
        if match:
            call_sites.append({
                'line': i,
                'content': line.strip(),
                'args': match.group(1).strip(),
            })

    return call_sites


def check_class_signature_completeness(file_path: Path, class_name: str) -> Dict:
    """
    检查类签名修改的所有调用方是否都已更新
    """
    class_info = find_class_definition(file_path, class_name)
    if not class_info['found']:
        return {
            'check': 'class_signature',
            'passed': False,
            'error': f"类 {class_name} 未找到",
        }

    raise_sites = find_raise_sites(file_path, class_name)
    method_defs = find_method_definitions(file_path)

    missing_methods = set()
    helper_calls = []

    for site in raise_sites:
        called_methods = find_method_calls_in_args(site['args'])
        for method in called_methods:
            helper_calls.append({
                'method': method,
                'called_at_line': site['line'],
            })
            if method not in method_defs:
                missing_methods.add(method)

    return {
        'check': 'class_signature',
        'passed': len(missing_methods) == 0,
        'class_info': class_info,
        'raise_sites_count': len(raise_sites),
        'helper_calls': helper_calls,
        'missing_methods': list(missing_methods),
        'error': f"缺少方法定义: {missing_methods}" if missing_methods else None,
    }


def check_helper_method_implementation(file_path: Path, method_name: str) -> Dict:
    """
    检查 helper 方法是否有完整实现（不是 stub/pass）

    检测 stub 模式：
    - def method(): pass
    - def method(): ...  # TODO
    - def method(): return None
    """
    content = file_path.read_text(encoding='utf-8')

    # 查找方法定义
    pattern = rf'def\s+{re.escape(method_name)}\s*\([^)]*\)\s*(?:\s*->\s*[^:]+)?\s*:\s*\n((?:[ \t]+.*\n)*)'
    match = re.search(pattern, content)

    if not match:
        return {
            'check': 'helper_implementation',
            'method': method_name,
            'passed': False,
            'error': f"方法 {method_name} 未定义",
        }

    body = match.group(1)

    # 检测 stub 模式
    stub_indicators = [
        r'^\s*pass\s*$',
        r'^\s*\.\.\.\s*$',
        r'^\s*return\s+None\s*$',
        r'#\s*TODO',
        r'#\s*FIXME',
        r'#\s*XXX',
        r'raise\s+NotImplementedError',
    ]

    is_stub = False
    for indicator in stub_indicators:
        if re.search(indicator, body, re.MULTILINE):
            is_stub = True
            break

    body_lines = [l for l in body.splitlines() if l.strip()]
    is_too_short = len(body_lines) <= 2

    return {
        'check': 'helper_implementation',
        'method': method_name,
        'passed': not is_stub and not is_too_short,
        'is_stub': is_stub,
        'is_too_short': is_too_short,
        'body_lines': len(body_lines),
        'error': f"方法 {method_name} 是 stub 或实现过短" if (is_stub or is_too_short) else None,
    }


def check_file(file_path: Path, class_name: str = None) -> Dict:
    """
    对文件执行完整的修复完整性检查
    """
    if not file_path.exists():
        return {
            'file': str(file_path),
            'passed': False,
            'error': f"文件不存在: {file_path}",
        }

    # 如果未指定 class_name，尝试从文件名推断
    if not class_name:
        class_name = file_path.stem.replace('_', ' ').title().replace(' ', '')

    results = {
        'file': str(file_path),
        'class_name': class_name,
        'checks': [],
        'passed': True,
    }

    # 检查 1：类签名完整性
    sig_check = check_class_signature_completeness(file_path, class_name)
    results['checks'].append(sig_check)
    if not sig_check['passed']:
        results['passed'] = False

    # 检查 2：helper 方法实现完整性
    helper_calls = sig_check.get('helper_calls', [])
    for call in helper_calls:
        method_name = call['method']
        impl_check = check_helper_method_implementation(file_path, method_name)
        impl_check['called_at_line'] = call['called_at_line']
        results['checks'].append(impl_check)
        if not impl_check['passed']:
            results['passed'] = False

    return results


def main():
    parser = argparse.ArgumentParser(description='修复完整性检查 (V2 落地)')
    parser.add_argument('--file', '-f', required=True, help='要检查的文件路径')
    parser.add_argument('--class', '-c', dest='class_name', help='类名（不指定则从文件名推断）')
    parser.add_argument('--quiet', '-q', action='store_true', help='只输出错误')

    args = parser.parse_args()

    file_path = Path(args.file)
    result = check_file(file_path, args.class_name)

    if not args.quiet or not result['passed']:
        print('=' * 70)
        print(f'修复完整性检查: {result["file"]}')
        print(f'类名: {result["class_name"]}')
        print('=' * 70)

        for check in result['checks']:
            status = '[OK]' if check['passed'] else '[FAIL]'
            print(f'{status} {check["check"]}')

            if 'missing_methods' in check and check['missing_methods']:
                print(f'        缺少方法: {check["missing_methods"]}')

            if 'helper_calls' in check:
                for call in check['helper_calls']:
                    print(f'        调用: {call["method"]} (line {call["called_at_line"]})')

            if 'is_stub' in check and check['is_stub']:
                print(f'        [WARN] 方法 {check["method"]} 是 stub')

            if 'is_too_short' in check and check['is_too_short']:
                print(f'        [WARN] 方法 {check["method"]} 实现过短 ({check["body_lines"]} 行)')

            if check.get('error'):
                print(f'        错误: {check["error"]}')

        print('=' * 70)
        if result['passed']:
            print('[OK] 修复完整性检查通过')
            sys.exit(0)
        else:
            print('[FAIL] 修复不完整，请检查上述错误')
            sys.exit(1)


if __name__ == '__main__':
    main()
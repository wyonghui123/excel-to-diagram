# -*- coding: utf-8 -*-
"""
绕过 conftest 的简化测试运行器
"""
import sys
import os
import traceback

sys.path.insert(0, '.')

# 直接 import 测试模块
from meta.tests.test_graphql_poc import (
    TestParseQuery, TestCamelCaseMapping, TestFormatResponse,
    TestSchemaRegistry, TestBlueprint,
)
from meta.tests.test_graphql_sdl_consistency import TestGraphQLSDLConsistency

def run_test_class(cls):
    """运行一个测试类的所有方法"""
    instance = cls()
    methods = [m for m in dir(cls) if m.startswith('test_')]
    results = {'pass': 0, 'fail': 0, 'errors': []}
    for method_name in methods:
        try:
            getattr(instance, method_name)()
            results['pass'] += 1
            print(f"  PASS: {cls.__name__}.{method_name}")
        except Exception as e:
            results['fail'] += 1
            tb = traceback.format_exc()
            results['errors'].append((f"{cls.__name__}.{method_name}", tb))
            print(f"  FAIL: {cls.__name__}.{method_name}")
            print(f"    {e}")
    return results

if __name__ == '__main__':
    print("=" * 60)
    print("M9 GraphQL POC 单测 - 绕过 conftest")
    print("=" * 60)

    classes = [
        TestParseQuery,
        TestCamelCaseMapping,
        TestFormatResponse,
        TestSchemaRegistry,
        TestBlueprint,
        TestGraphQLSDLConsistency,
    ]

    total_pass = 0
    total_fail = 0

    for cls in classes:
        print(f"\n[{cls.__name__}]")
        r = run_test_class(cls)
        total_pass += r['pass']
        total_fail += r['fail']

    print()
    print("=" * 60)
    print(f"TOTAL: {total_pass} PASS / {total_fail} FAIL")
    print("=" * 60)

    if total_fail > 0:
        sys.exit(1)

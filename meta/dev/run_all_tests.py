#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
统一测试运行脚本

运行所有元模型测试
"""

import sys
import os
import time
import importlib

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
META_DIR = os.path.dirname(TESTS_DIR)
PROJECT_DIR = os.path.dirname(META_DIR)

sys.path.insert(0, PROJECT_DIR)


TEST_MODULES = [
    ("元模型核心测试", "test_core_models"),
    ("YAML 加载器测试", "test_yaml_loader"),
    ("Schema 生成器测试", "test_schema_generator"),
    ("规则链测试", "test_rule_chain"),
    ("派生规则测试", "test_derivation"),
    ("层级路径测试", "test_hierarchy_path"),
    ("RuleEngine 测试", "test_rule_engine"),
    ("ActionExecutor 集成测试", "test_action_executor"),
    ("统一元模型测试", "test_unified_meta_model"),
    ("外键解析测试", "test_foreign_key_resolution"),
    ("导入外键解析集成测试", "test_import_with_parent_resolution"),
]


def run_test(name, module_name):
    """运行单个测试"""
    print("\n" + "=" * 70)
    print("  运行: {0}".format(name))
    print("=" * 70)
    
    try:
        module = importlib.import_module(module_name)
        if hasattr(module, "run_all_tests"):
            module.run_all_tests()
        elif hasattr(module, "main"):
            module.main()
        else:
            print("  [SKIP] 未找到测试入口")
            return True
        
        return True
    except Exception as e:
        print("\n  [FAIL] {0}".format(str(e)))
        import traceback
        traceback.print_exc()
        return False


def run_all():
    """运行所有测试"""
    print("=" * 70)
    print("  元模型自动化测试")
    print("=" * 70)
    
    start_time = time.time()
    
    results = []
    for name, module_name in TEST_MODULES:
        success = run_test(name, module_name)
        results.append((name, success))
    
    elapsed = time.time() - start_time
    
    print("\n" + "=" * 70)
    print("  测试汇总")
    print("=" * 70)
    
    passed = sum(1 for _, s in results if s)
    failed = sum(1 for _, s in results if not s)
    
    for name, success in results:
        status = "[PASS]" if success else "[FAIL]"
        print("  {0} {1}".format(status, name))
    
    print("\n" + "-" * 70)
    print("  总计: {0} 个测试".format(len(results)))
    print("  通过: {0}".format(passed))
    print("  失败: {0}".format(failed))
    print("  耗时: {0:.2f} 秒".format(elapsed))
    print("=" * 70)
    
    return failed == 0


if __name__ == "__main__":
    success = run_all()
    sys.exit(0 if success else 1)

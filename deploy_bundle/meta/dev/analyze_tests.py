#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试体系分析脚本

分析测试文件分布、测试数量和潜在问题。
支持分层执行统计。
"""

import os
import re
import sys
import subprocess
from collections import defaultdict
from pathlib import Path

TESTS_DIR = Path(__file__).parent


def analyze_tests():
    """分析测试目录"""
    
    # 统计数据
    test_files = []
    debug_scripts = []
    data_scripts = []
    tool_scripts = []
    other_files = []
    
    # 按前缀分组
    prefix_groups = defaultdict(list)
    
    # 分层统计
    unit_tests = []
    integration_tests = []
    e2e_tests = []
    
    for f in TESTS_DIR.iterdir():
        if not f.is_file() or not f.suffix == '.py':
            continue
        
        name = f.stem
        
        # 分类
        if name.startswith('test_'):
            test_files.append(name)
            
            # 提取测试主题
            parts = name[5:].split('_')
            if len(parts) >= 2:
                prefix = '_'.join(parts[:2])
            else:
                prefix = parts[0] if parts else 'unknown'
            prefix_groups[prefix].append(name)
            
            # 分层分类
            if any(kw in name.lower() for kw in ['service', 'manager', 'config', 'utils']):
                if 'api' not in name.lower():
                    unit_tests.append(name)
            elif any(kw in name.lower() for kw in ['api', 'endpoint', 'integration']):
                integration_tests.append(name)
            elif any(kw in name.lower() for kw in ['e2e', 'scenario', 'import_export']):
                e2e_tests.append(name)
            else:
                unit_tests.append(name)
            
        elif name.startswith('debug_'):
            debug_scripts.append(name)
        elif name.startswith('quick_') or name.startswith('pinpoint_'):
            tool_scripts.append(name)
        elif name.startswith('add_') or name.startswith('init_') or name.startswith('check_') or name.startswith('batch_') or name.startswith('fix_') or name.startswith('show_'):
            data_scripts.append(name)
        else:
            other_files.append(name)
    
    # 分析测试文件内容
    test_class_counts = defaultdict(int)
    test_function_counts = defaultdict(int)
    
    for name in test_files:
        filepath = TESTS_DIR / f"{name}.py"
        try:
            content = filepath.read_text(encoding='utf-8')
            
            # 统计测试类
            classes = re.findall(r'class\s+(Test\w+)', content)
            test_class_counts[name] = len(classes)
            
            # 统计测试函数
            functions = re.findall(r'def\s+(test_\w+)', content)
            test_function_counts[name] = len(functions)
            
        except Exception as e:
            print(f"Error reading {name}: {e}")
    
    # 输出分析结果
    print("=" * 80)
    print("测试体系分析报告")
    print("=" * 80)
    
    print(f"\n[DECORATIVE] 文件统计:")
    print(f"  - 测试文件 (test_*.py): {len(test_files)}")
    print(f"  - 调试脚本 (debug_*.py): {len(debug_scripts)}")
    print(f"  - 数据脚本 (add_*/init_*/check_*/batch_*/fix_*/show_*): {len(data_scripts)}")
    print(f"  - 工具脚本 (quick_*/pinpoint_*): {len(tool_scripts)}")
    print(f"  - 其他文件: {len(other_files)}")
    print(f"  - 总计: {len(test_files) + len(debug_scripts) + len(data_scripts) + len(tool_scripts) + len(other_files)}")
    
    total_classes = sum(test_class_counts.values())
    total_functions = sum(test_function_counts.values())
    print(f"\n[DECORATIVE] 测试用例统计:")
    print(f"  - 测试类总数: {total_classes}")
    print(f"  - 测试函数总数: {total_functions}")
    
    # 分层统计
    unit_function_count = sum(test_function_counts.get(t, 0) for t in unit_tests)
    integration_function_count = sum(test_function_counts.get(t, 0) for t in integration_tests)
    e2e_function_count = sum(test_function_counts.get(t, 0) for t in e2e_tests)
    
    print(f"\n[SYMBOL] 分层统计:")
    print(f"  - 单元测试: {len(unit_tests)} 个文件, {unit_function_count} 个用例")
    print(f"  - 集成测试: {len(integration_tests)} 个文件, {integration_function_count} 个用例")
    print(f"  - E2E测试: {len(e2e_tests)} 个文件, {e2e_function_count} 个用例")
    
    # 按测试数量排序
    print(f"\n[CLIPBOARD] 测试文件按用例数量排序 (Top 20):")
    sorted_files = sorted(test_function_counts.items(), key=lambda x: x[1], reverse=True)
    for name, count in sorted_files[:20]:
        classes = test_class_counts[name]
        print(f"  {name}: {count} 函数, {classes} 类")
    
    # 按前缀分组
    print(f"\n[SYMBOL] 测试文件按主题分组:")
    sorted_groups = sorted(prefix_groups.items(), key=lambda x: len(x[1]), reverse=True)
    for prefix, files in sorted_groups:
        if len(files) >= 2:
            print(f"  {prefix}: {len(files)} 个文件")
            for f in files:
                print(f"    - {f}")
    
    # 调试脚本
    if debug_scripts:
        print(f"\n[TOOL] 调试脚本 (建议移至 scripts/debug/):")
        for name in sorted(debug_scripts):
            print(f"  - {name}")
    
    # 数据脚本
    if data_scripts:
        print(f"\n[DECORATIVE] 数据脚本 (建议移至 scripts/data/):")
        for name in sorted(data_scripts):
            print(f"  - {name}")
    
    # 工具脚本
    if tool_scripts:
        print(f"\n[TOOL] 工具脚本 (建议移至 scripts/tools/):")
        for name in sorted(tool_scripts):
            print(f"  - {name}")
    
    # 识别可能重复的测试
    print(f"\n[WARNING] 可能重复或相似的测试文件:")
    seen_prefixes = set()
    for prefix, files in sorted_groups:
        if len(files) > 1 and prefix not in seen_prefixes:
            print(f"  {prefix}:")
            for f in files:
                count = test_function_counts.get(f, 0)
                print(f"    - {f} ({count} 测试)")
            seen_prefixes.add(prefix)
    
    # 建议
    print(f"\n[DECORATIVE] 优化建议:")
    print(f"  1. 将 {len(debug_scripts)} 个调试脚本移至 meta/scripts/debug/")
    print(f"  2. 将 {len(data_scripts)} 个数据脚本移至 meta/scripts/data/")
    print(f"  3. 将 {len(tool_scripts)} 个工具脚本移至 meta/scripts/tools/")
    print(f"  4. 整合相似测试文件 (如 test_analytics_p0/p1_adaptation)")
    print(f"  5. 按模块创建子目录分层组织测试")
    print(f"")
    print(f"  [DECORATIVE] 执行建议:")
    print(f"  - 快速验证: python -m pytest meta/tests/unit -m unit")
    print(f"  - 完整测试: python -m pytest meta/tests/ -m 'unit or integration'")


def run分层测试():
    """运行分层测试统计"""
    print("\n" + "=" * 80)
    print("分层测试执行统计")
    print("=" * 80)
    
    try:
        # 单元测试统计
        print("\n[SYMBOL] 运行单元测试...")
        result = subprocess.run(
            ['python', '-m', 'pytest', 'meta/tests/', '-m', 'unit', '-v', '--tb=no', '-q'],
            capture_output=True,
            text=True,
            cwd=str(Path(__file__).parent.parent.parent),
            timeout=120
        )
        print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
        
    except Exception as e:
        print(f"单元测试执行失败: {e}")


if __name__ == '__main__':
    analyze_tests()

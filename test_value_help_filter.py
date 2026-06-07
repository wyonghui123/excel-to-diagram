#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""测试 value_help 过滤器是否正确显示"""

import sys
import os
import time

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    print("=" * 60)
    print("测试 value_help 过滤器")
    print("=" * 60)

    # 1. 检查 API 返回
    print("\n1. 检查 API 返回:")
    import requests
    try:
        resp = requests.get('http://localhost:3010/api/v1/meta/user_group/view-config', timeout=5)
        data = resp.json()

        filters = data.get('data', {}).get('list', {}).get('filters', [])
        print(f"   找到 {len(filters)} 个过滤器")

        for f in filters:
            if f.get('type') == 'value_help':
                print(f"\n   [DECORATIVE] value_help 过滤器:")
                print(f"     - field: {f.get('field')}")
                print(f"     - label: {f.get('label')}")
                print(f"     - type: {f.get('type')}")

                vh = f.get('value_help', {})
                if vh:
                    print(f"     - value_help.source.type: {vh.get('source', {}).get('type')}")
                    print(f"     - value_help.source.target_bo: {vh.get('source', {}).get('target_bo')}")
                    print(f"     - value_help.behavior.multiple: {vh.get('behavior', {}).get('multiple')}")
                    print(f"     - value_help.presentation.result_type: {vh.get('presentation', {}).get('result_type')}")
                else:
                    print(f"     - WARNING: value_help 为空!")

    except Exception as e:
        print(f"   API 请求失败: {e}")
        return

    # 2. 检查前端代码
    print("\n2. 检查前端 FilterBar.vue:")
    filter_bar_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   'src', 'components', 'common', 'FilterBar', 'FilterBar.vue')
    with open(filter_bar_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if "field.valueHelpConfig || field.value_help" in content:
        print("   [DECORATIVE] 已修复: FilterBar 使用 field.valueHelpConfig || field.value_help")
    elif "field.valueHelpConfig" in content:
        print("   [DECORATIVE] 未修复: FilterBar 仍只使用 field.valueHelpConfig")
    else:
        print("   ? 无法确定修复状态")

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == '__main__':
    main()

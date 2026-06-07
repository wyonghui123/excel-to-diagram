#!/usr/bin/env python3
"""
批量修复测试文件中的API路径
将 /api/v1/xxx 替换为 /api/v2/bo/xxx
"""

import os
import re

# API路径映射
API_MAPPINGS = [
    # product相关
    ('/api/v1/product', '/api/v2/bo/product'),
    ('/api/v1/products', '/api/v2/bo/products'),
    # version相关
    ('/api/v1/version', '/api/v2/bo/version'),
    ('/api/v1/versions', '/api/v2/bo/versions'),
    # domain相关
    ('/api/v1/domain', '/api/v2/bo/domain'),
    ('/api/v1/domains', '/api/v2/bo/domains'),
    # business_object相关
    ('/api/v1/business_object', '/api/v2/bo/business_object'),
    ('/api/v1/business_objects', '/api/v2/bo/business_objects'),
    # relationship相关
    ('/api/v1/relationship', '/api/v2/bo/relationship'),
    ('/api/v1/relationships', '/api/v2/bo/relationships'),
    # other v1 endpoints
    ('/api/v1/query', '/api/v2/bo/query'),
    ('/api/v1/menu', '/api/v2/bo/menu'),
    ('/api/v1/user', '/api/v2/bo/user'),
    ('/api/v1/role', '/api/v2/bo/role'),
    ('/api/v1/audit', '/api/v2/bo/audit'),
    ('/api/v1/enum', '/api/v2/bo/enum'),
]

def process_file(filepath):
    """处理单个文件"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()

        original = content
        replacements_made = []

        for old_path, new_path in API_MAPPINGS:
            if old_path in content:
                count = content.count(old_path)
                content = content.replace(old_path, new_path)
                replacements_made.append(f"{old_path} -> {new_path} ({count}处)")

        if content != original:
            # 备份原文件
            backup_path = filepath + '.bak'
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(original)

            # 写入新内容
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            print(f"[DECORATIVE] {filepath}")
            for r in replacements_made:
                print(f"  - {r}")
            return True

        return False

    except Exception as e:
        print(f"[DECORATIVE] {filepath}: {e}")
        return False

def main():
    tests_dir = r'D:\filework\excel-to-diagram\meta\tests'

    # 要处理的文件列表
    files_to_process = [
        'test_api_integration.py',
        'test_core_models.py',
        'test_meta_api.py',
        'test_manage_api.py',
        'test_relation_api.py',
        'test_scope_mode.py',
        'test_bo_api.py',
        'test_role_api.py',
        'test_user_api.py',
        'test_v2_api_permissions.py',
    ]

    total_fixed = 0
    for filename in files_to_process:
        filepath = os.path.join(tests_dir, filename)
        if os.path.exists(filepath):
            if process_file(filepath):
                total_fixed += 1
        else:
            print(f"跳过 {filename} - 不存在")

    print(f"\n总计修复 {total_fixed} 个文件")

if __name__ == '__main__':
    main()

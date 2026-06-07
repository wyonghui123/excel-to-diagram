#!/usr/bin/env python3
"""
自动扫描并修复所有测试文件中的v1 API路径
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
    ('/api/v1/service_module', '/api/v2/bo/service_module'),
    ('/api/v1/sub_domain', '/api/v2/bo/sub_domain'),
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

            print(f"[DECORATIVE] {os.path.basename(filepath)}")
            for r in replacements_made:
                print(f"  - {r}")
            return True

        return False

    except Exception as e:
        print(f"[DECORATIVE] {os.path.basename(filepath)}: {e}")
        return False

def scan_tests_directory():
    """扫描tests目录下的所有.py文件"""
    tests_dir = r'D:\filework\excel-to-diagram\meta\tests'
    backup_dir = r'D:\filework\excel-to-diagram\meta\tests_backups'

    # 创建备份目录
    if not os.path.exists(backup_dir):
        os.makedirs(backup_dir)

    total_fixed = 0
    total_replacements = 0

    for filename in os.listdir(tests_dir):
        if not filename.startswith('test_') or not filename.endswith('.py'):
            continue

        filepath = os.path.join(tests_dir, filename)

        # 跳过已处理的文件
        if os.path.exists(filepath + '.done'):
            continue

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
                    total_replacements += count

            if content != original:
                # 备份到专门目录
                backup_path = os.path.join(backup_dir, filename)
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(original)

                # 写入新内容
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)

                # 创建标记文件
                with open(filepath + '.done', 'w') as f:
                    f.write('')

                print(f"[DECORATIVE] {filename}")
                for r in replacements_made:
                    print(f"  - {r}")
                total_fixed += 1

        except Exception as e:
            print(f"[DECORATIVE] {filename}: {e}")

    print(f"\n总计修复 {total_fixed} 个文件，{total_replacements} 处替换")
    print(f"备份位置: {backup_dir}")

if __name__ == '__main__':
    scan_tests_directory()

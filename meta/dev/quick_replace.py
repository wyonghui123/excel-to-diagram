# -*- coding: utf-8 -*-
"""
快速替换测试文件中的硬编码数据库路径
"""

import os
import glob

def replace_in_file(file_path):
    """替换文件中的硬编码路径"""
    if not os.path.exists(file_path):
        print(f"[SKIP] Not found: {file_path}")
        return False

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    # 替换所有变体
    replacements = [
        ('get_data_source("sqlite", database="architecture.db")',
         'get_data_source("sqlite", database=get_test_db_path())'),
        ("get_data_source('sqlite', database='architecture.db')",
         "get_data_source('sqlite', database=get_test_db_path())"),
        ('get_data_source("sqlite", database="meta/architecture.db")',
         'get_data_source("sqlite", database=get_test_db_path())'),
        ("get_data_source('sqlite', database='meta/architecture.db')",
         "get_data_source('sqlite', database=get_test_db_path())"),
    ]

    for old, new in replacements:
        content = content.replace(old, new)

    if content != original:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[OK] Updated: {file_path}")
        return True
    return False

def main():
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    pattern = os.path.join(tests_dir, "test_*.py")

    count = 0
    for file_path in glob.glob(pattern):
        # 跳过工具文件
        if 'test_utils' in file_path or 'batch_update' in file_path or 'init_test_data' in file_path:
            continue
        if replace_in_file(file_path):
            count += 1

    print(f"\n完成！共更新 {count} 个文件。")

if __name__ == '__main__':
    main()

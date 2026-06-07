# -*- coding: utf-8 -*-
"""
批量更新测试文件使用统一的数据库路径

将所有硬编码的数据库路径替换为 get_test_db_path()
"""

import os
import re

# 需要更新的文件及其模式
UPDATES = [
    {
        'file': 'test_e2e_tree_to_list.py',
        'old': 'get_data_source("sqlite", database="architecture.db")',
        'new': 'get_data_source("sqlite", database=get_test_db_path())',
    },
    {
        'file': 'test_diagnose_domain_list.py',
        'old': 'get_data_source("sqlite", database="architecture.db")',
        'new': 'get_data_source("sqlite", database=get_test_db_path())',
    },
    {
        'file': 'test_enrichment_and_search.py',
        'old': 'get_data_source("sqlite", database="architecture.db")',
        'new': 'get_data_source("sqlite", database=get_test_db_path())',
    },
    {
        'file': 'test_hierarchy_filter_api.py',
        'old': 'get_data_source("sqlite", database="architecture.db")',
        'new': 'get_data_source("sqlite", database=get_test_db_path())',
    },
    {
        'file': 'test_scope_mode.py',
        'old': 'get_data_source("sqlite", database="architecture.db")',
        'new': 'get_data_source("sqlite", database=get_test_db_path())',
    },
    {
        'file': 'test_sub_domain_issue.py',
        'old': 'get_data_source("sqlite", database="architecture.db")',
        'new': 'get_data_source("sqlite", database=get_test_db_path())',
    },
    {
        'file': 'test_tree_empty.py',
        'old': 'get_data_source("sqlite", database="architecture.db")',
        'new': 'get_data_source("sqlite", database=get_test_db_path())',
    },
    {
        'file': 'test_leaf_domain_issue.py',
        'old': 'get_data_source("sqlite", database="architecture.db")',
        'new': 'get_data_source("sqlite", database=get_test_db_path())',
    },
    {
        'file': 'test_multi_level_and.py',
        'old': 'get_data_source("sqlite", database="architecture.db")',
        'new': 'get_data_source("sqlite", database=get_test_db_path())',
    },
    {
        'file': 'test_relation_api.py',
        'old': 'get_data_source("sqlite", database="architecture.db")',
        'new': 'get_data_source("sqlite", database=get_test_db_path())',
    },
    {
        'file': 'test_annotation_api.py',
        'old': 'get_data_source("sqlite", database="architecture.db")',
        'new': 'get_data_source("sqlite", database=get_test_db_path())',
    },
    {
        'file': 'test_dimension_aware_filtering.py',
        'old': 'get_data_source("sqlite", database="architecture.db")',
        'new': 'get_data_source("sqlite", database=get_test_db_path())',
    },
    {
        'file': 'test_exact_scenario.py',
        'old': 'get_data_source("sqlite", database="architecture.db")',
        'new': 'get_data_source("sqlite", database=get_test_db_path())',
    },
    {
        'file': 'test_field_controls.py',
        'old': 'get_data_source("sqlite", database="architecture.db")',
        'new': 'get_data_source("sqlite", database=get_test_db_path())',
    },
    {
        'file': 'test_hierarchy_filter_service.py',
        'old': 'get_data_source("sqlite", database="architecture.db")',
        'new': 'get_data_source("sqlite", database=get_test_db_path())',
    },
    {
        'file': 'test_meta_api.py',
        'old': 'get_data_source("sqlite", database="architecture.db")',
        'new': 'get_data_source("sqlite", database=get_test_db_path())',
    },
]

def add_import_if_missing(content, file_path):
    """如果文件中没有导入 test_utils，则添加"""
    if 'from meta.tests.test_utils import get_test_db_path' not in content:
        # 找到最后一个导入语句的位置
        lines = content.split('\n')
        last_import_idx = -1
        for i, line in enumerate(lines):
            if line.strip().startswith('from ') or line.strip().startswith('import '):
                last_import_idx = i

        if last_import_idx >= 0:
            lines.insert(last_import_idx + 1, 'from meta.tests.test_utils import get_test_db_path')
            return '\n'.join(lines)
    return content

def process_file(file_path, old_pattern, new_pattern):
    """处理单个文件"""
    if not os.path.exists(file_path):
        print(f"  [SKIP] {file_path} not found")
        return False

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if old_pattern not in content:
        print(f"  [SKIP] Pattern not found in {file_path}")
        return False

    # 添加导入（如果需要）
    content = add_import_if_missing(content, file_path)

    # 替换模式
    new_content = content.replace(old_pattern, new_pattern)

    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)

    print(f"  [OK] Updated {file_path}")
    return True

def main():
    tests_dir = os.path.dirname(os.path.abspath(__file__))

    print("批量更新测试文件使用统一的数据库路径...")
    print(f"工作目录: {tests_dir}\n")

    for update in UPDATES:
        file_path = os.path.join(tests_dir, update['file'])
        process_file(file_path, update['old'], update['new'])

    print("\n完成！")

if __name__ == '__main__':
    main()

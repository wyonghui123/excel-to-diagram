#!/usr/bin/env python3
"""
批量修复测试文件中的API路径
"""

import os

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

            print(f"[DECORATIVE] {os.path.basename(filepath)}")
            for r in replacements_made:
                print(f"  - {r}")
            return True

        return False

    except Exception as e:
        print(f"[DECORATIVE] {os.path.basename(filepath)}: {e}")
        return False

def main():
    tests_dir = r'D:\filework\excel-to-diagram\meta\tests'

    # 更多要处理的文件列表
    files_to_process = [
        'test_bo_api.py',
        'test_audit_api.py',
        'test_data_permission_api.py',
        'test_menu_auto_generator.py',
        'test_computation_aggregation.py',
        'test_object_adaptation_role.py',
        'test_object_adaptation_user_group.py',
        'test_owner_transfer_api.py',
        'test_permission_bundle_api.py',
        'test_permission_audit_api.py',
        'test_field_controls.py',
        'test_v2_api_permissions.py',
        'test_real_data_scenario.py',
        'test_queryservice_dataperm.py',
        'test_yaml_single_source_of_truth.py',
        'test_yaml_loader.py',
        'test_detail_and_batch.py',
        'test_e2e_tree_to_list.py',
        'test_view_config.py',
        'test_view_config_v2_api.py',
    ]

    total_fixed = 0
    for filename in files_to_process:
        filepath = os.path.join(tests_dir, filename)
        if os.path.exists(filepath):
            if process_file(filepath):
                total_fixed += 1
        # else:
        #     print(f"跳过 {filename} - 不存在")

    print(f"\n总计修复 {total_fixed} 个文件")

if __name__ == '__main__':
    main()

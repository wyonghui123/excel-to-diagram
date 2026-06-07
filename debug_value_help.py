#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""调试脚本：检查 user_group 的 value_help 配置是否正确解析"""

import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from meta.core.yaml_loader import load_yaml_file, parse_field, parse_value_help
from meta.core.models import registry

def main():
    # 加载 user_group.yaml
    schema_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'meta', 'schemas')
    yaml_path = os.path.join(schema_dir, 'user_group.yaml')

    print("=" * 60)
    print("调试：检查 value_help 配置")
    print("=" * 60)

    # 1. 直接解析 YAML 文件
    print("\n1. 直接解析 YAML 文件:")
    import yaml
    with open(yaml_path, 'r', encoding='utf-8') as f:
        raw_yaml = yaml.safe_load(f)

    # 找到 parent_id 字段
    parent_id_field = None
    for field in raw_yaml.get('fields', []):
        if field.get('id') == 'parent_id':
            parent_id_field = field
            break

    if parent_id_field:
        print(f"\n   parent_id 字段的原始 YAML:")
        print(f"   - 有 value_help: {'value_help' in parent_id_field}")
        if 'value_help' in parent_id_field:
            vh = parent_id_field['value_help']
            print(f"   - value_help 类型: {type(vh)}")
            print(f"   - value_help 内容: {vh}")

            # 测试 parse_value_help 函数
            result = parse_value_help(parent_id_field)
            print(f"\n   parse_value_help 结果: {result}")

    # 2. 通过 registry 获取解析后的 MetaField
    print("\n2. 通过 registry 获取解析后的 MetaField:")
    from meta.core.yaml_loader import register_from_directory
    register_from_directory(schema_dir)

    meta_obj = registry.get('user_group')
    if meta_obj:
        for field in meta_obj.fields:
            if field.id == 'parent_id':
                print(f"\n   parent_id 字段:")
                print(f"   - field.value_help: {field.value_help}")

                if field.value_help:
                    print(f"   - value_help.source: {field.value_help.source}")
                    print(f"   - value_help.behavior: {field.value_help.behavior}")
                    print(f"   - value_help.presentation: {field.value_help.presentation}")
                    if field.value_help.presentation:
                        print(f"   - presentation.result_type: {field.value_help.presentation.result_type}")

                # 检查 ui.relation
                ui = getattr(field, 'ui', None)
                if ui:
                    print(f"   - ui.relation: {getattr(ui, 'relation', None)}")
                    print(f"   - ui.widget: {getattr(ui, 'widget', None)}")
                    print(f"   - ui.multiple: {getattr(ui, 'multiple', None)}")
                break

    # 3. 测试 _infer_value_help_from_field
    print("\n3. 测试 _infer_value_help_from_field:")
    from meta.core.yaml_loader import _infer_value_help_from_field

    if parent_id_field:
        ui_annotation = parse_ui_annotation(parent_id_field.get('ui', {}))
        inferred = _infer_value_help_from_field(parent_id_field, ui_annotation)
        print(f"   推断的 value_help: {inferred}")

    print("\n" + "=" * 60)
    print("调试完成")
    print("=" * 60)

if __name__ == '__main__':
    main()

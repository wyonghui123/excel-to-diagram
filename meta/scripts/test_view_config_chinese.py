"""
test_view_config_chinese.py - 验证 view-config 返回的中文标题
直接读取 YAML 文件并通过 yaml_loader 解析
"""
import yaml
import os

def load_yaml(path):
    with open(path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def get_field_name(schema, field_id):
    """从 schema 的 fields 中获取字段的中文名称"""
    fields = schema.get('fields', [])
    for f in fields:
        if f.get('id') == field_id:
            return f.get('name', '')
    return ''

def test_entity(entity_name):
    print(f"\n{'='*60}")
    print(f"测试 {entity_name} 的 view-config")
    print('='*60)

    yaml_path = f'D:/filework/excel-to-diagram/meta/schemas/{entity_name}.yaml'

    if not os.path.exists(yaml_path):
        print(f"[X] 文件不存在: {yaml_path}")
        return False

    schema = load_yaml(yaml_path)
    if not schema:
        print(f"[X] 无法解析 YAML")
        return False

    print(f"[OK] Schema: {schema.get('name')}")

    # 构建 fields_dict
    fields = schema.get('fields', [])
    fields_dict = {}
    for f in fields:
        fid = f.get('id')
        if fid:
            fields_dict[fid] = f

    print(f"   fields 数量: {len(fields)}")
    print(f"   fields_dict 键: {list(fields_dict.keys())[:5]}...")

    # 读取 ui_view_config
    ui_view_config = schema.get('ui_view_config', {})
    list_config = ui_view_config.get('list', {})
    columns = list_config.get('columns', [])

    print(f"\n[CLIPBOARD] 原始列定义 (from YAML):")
    for i, col in enumerate(columns):
        field_id = col.get('field')
        yaml_label = col.get('label')
        print(f"   {i+1}. field={field_id}, yaml_label={yaml_label}")

        # 尝试从 fields 获取中文名称
        if field_id and field_id in fields_dict:
            field_name = fields_dict[field_id].get('name', '')
            print(f"       -> fields 中的 name: {field_name}")

    # 模拟 parse_ui_list_view_config 的逻辑
    print(f"\n[CLIPBOARD] 应用修复后的 title (当 yaml label 为空时从 fields 获取):")
    for i, col in enumerate(columns):
        field_id = col.get('field')
        yaml_label = col.get('label')

        # 应用修复逻辑
        final_title = yaml_label
        if not final_title:  # yaml 中没有 label
            if field_id and field_id in fields_dict:
                final_title = fields_dict[field_id].get('name', '')
        if not final_title:  # fields 中也没有
            final_title = field_id  # fallback 到 field

        print(f"   {i+1}. field={field_id}, final_title={final_title}")

    return True


if __name__ == '__main__':
    print("="*60)
    print("[SEARCH] 测试 view-config 中文标题")
    print("="*60)

    for entity in ['role', 'user', 'user_group']:
        test_entity(entity)

    print("\n" + "="*60)
    print("测试完成")
    print("="*60)

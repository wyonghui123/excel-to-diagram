"""
check_yaml_config.py - 直接读取 YAML 文件并打印配置
"""
import yaml
import os

def check_yaml_file(entity_type):
    print(f"\n{'='*60}")
    print(f"[SEARCH] 检查 {entity_type} 的 YAML 配置")
    print('='*60)

    yaml_path = f'D:/filework/excel-to-diagram/meta/schemas/{entity_type}.yaml'

    if not os.path.exists(yaml_path):
        print(f"[X] 文件不存在: {yaml_path}")
        return

    with open(yaml_path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)

    if not data:
        print(f"[X] 无法解析 YAML")
        return

    print(f"[OK] YAML 解析成功")
    print(f"   id: {data.get('id')}")
    print(f"   name: {data.get('name')}")

    # 获取 ui_view_config
    ui_view_config = data.get('ui_view_config', {})
    print(f"\n[CLIPBOARD] ui_view_config 存在: {bool(ui_view_config)}")

    if ui_view_config:
        list_config = ui_view_config.get('list', {})
        print(f"   list 配置存在: {bool(list_config)}")

        if list_config:
            columns = list_config.get('columns', [])
            print(f"   columns 数量: {len(columns)}")

            if columns:
                print(f"\n   [DECORATIVE] 原始列定义 (from YAML):")
                for i, col in enumerate(columns):
                    print(f"      {i+1}. field={col.get('field')}, label={col.get('label')}, width={col.get('width')}")
                    if 'association' in str(col):
                        print(f"          (包含 association 配置)")

            actions = list_config.get('actions', [])
            print(f"\n   [DECORATIVE] actions 数量: {len(actions)}")
            for i, act in enumerate(actions):
                print(f"      {i+1}. id={act.get('id')}, label={act.get('label')}")

            search_fields = list_config.get('searchFields', [])
            print(f"\n   [DECORATIVE] searchFields: {search_fields}")

            filters = list_config.get('filters', [])
            print(f"\n   [DECORATIVE] filters:")
            for f in filters:
                print(f"      - field={f.get('field')}, type={f.get('type')}")

            default_sort = list_config.get('defaultSort', {})
            print(f"\n   [DECORATIVE] defaultSort: {default_sort}")

    # 打印完整的 ui_view_config
    print(f"\n[SYMBOL] 完整的 ui_view_config.list (YAML 原始):")
    if ui_view_config:
        print(yaml.dump(ui_view_config.get('list', {}), indent=2, allow_unicode=True, default_flow_style=False))


if __name__ == '__main__':
    print("="*60)
    print("[SEARCH] YAML 配置诊断工具")
    print("="*60)

    for entity in ['role', 'user_group', 'user']:
        check_yaml_file(entity)

    print("\n" + "="*60)
    print("诊断完成")
    print("="*60)

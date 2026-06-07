"""
check_view_config.py - 检查 view-config 原始数据
直接导入 view_config_service，打印返回的原始数据
"""
import os
import sys

# 设置工作目录
os.chdir('D:/filework/excel-to-diagram/meta')
sys.path.insert(0, os.getcwd())

from meta.services.view_config_service import get_or_build_view_config

def check_view_config(entity_type):
    print(f"\n{'='*60}")
    print(f"[SEARCH] 检查 {entity_type} 的 view-config")
    print('='*60)

    config = get_or_build_view_config(entity_type)

    if config is None:
        print(f"[X] {entity_type} 没有 view-config")
        return

    print(f"[OK] view-config 加载成功")
    print(f"\n[CLIPBOARD] list 配置:")

    if hasattr(config, 'list') and config.list:
        list_config = config.list
        print(f"   title: {list_config.title}")
        print(f"   columns 数量: {len(list_config.columns) if list_config.columns else 0}")

        if list_config.columns:
            print(f"\n   [DECORATIVE] 列定义:")
            for i, col in enumerate(list_config.columns):
                print(f"      {i+1}. key={col.key}, title={col.title}, width={col.width}")

        if list_config.actions:
            print(f"\n   [DECORATIVE] actions 数量: {len(list_config.actions)}")
            for i, act in enumerate(list_config.actions):
                key = getattr(act, 'key', getattr(act, 'id', 'N/A'))
                print(f"      {i+1}. key={key}, label={act.label}")

        if list_config.searchFields:
            print(f"\n   [DECORATIVE] searchFields 数量: {len(list_config.searchFields)}")

        if list_config.filters:
            print(f"\n   [DECORATIVE] filters 数量: {len(list_config.filters)}")
    else:
        print("   [X] 缺少 list 配置")

    print(f"\n[CLIPBOARD] form 配置:")
    if hasattr(config, 'form') and config.form:
        print(f"   title: {config.form.title}")
        print(f"   groups 数量: {len(config.form.groups) if config.form.groups else 0}")
    else:
        print("   [WARNING]  缺少 form 配置")

    print(f"\n[CLIPBOARD] detail 配置:")
    if hasattr(config, 'detail') and config.detail:
        print(f"   title: {config.detail.title}")
        print(f"   tabs 数量: {len(config.detail.tabs) if config.detail.tabs else 0}")
    else:
        print("   [WARNING]  缺少 detail 配置")

    # 打印原始 dict 便于调试
    print(f"\n[SYMBOL] 原始 dict (list 部分):")
    if hasattr(config, 'to_dict'):
        config_dict = config.to_dict()
    else:
        config_dict = {}
        for attr in ['list', 'form', 'detail']:
            if hasattr(config, attr):
                val = getattr(config, attr)
                if hasattr(val, 'to_dict'):
                    config_dict[attr] = val.to_dict()
                else:
                    config_dict[attr] = str(val)

    if 'list' in config_dict:
        import json
        print(json.dumps(config_dict['list'], indent=2, ensure_ascii=False, default=str))

    return config


if __name__ == '__main__':
    print("="*60)
    print("[SEARCH] View-Config 诊断工具")
    print("="*60)

    for entity in ['role', 'user_group', 'user']:
        check_view_config(entity)

    print("\n" + "="*60)
    print("诊断完成")
    print("="*60)

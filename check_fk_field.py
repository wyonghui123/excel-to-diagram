# 检查 FK 字段定义
import sys
sys.path.insert(0, 'd:/filework/excel-to-diagram')

# 直接从 meta_object 获取字段信息
from meta.core.yaml_loader import get_meta_object

meta = get_meta_object('user_group')
if meta:
    print(f"meta_object: {meta}")
    print(f"fields count: {len(meta.fields) if meta.fields else 0}")
    for field in meta.fields:
        vh = getattr(field, 'value_help', None)
        if vh:
            source = getattr(vh, 'source', None)
            if source:
                print(f"\nField: {field.id}")
                print(f"  target_bo: {getattr(source, 'target_bo', None)}")
                print(f"  display_field: {getattr(source, 'display_field', None)}")
                print(f"  code_field: {getattr(source, 'code_field', None)}")
                print(f"  target_table: {getattr(source, 'target_table', None)}")  # 可能没有这个属性
else:
    print("meta_object is None")

with open('meta/api/manage_api.py', 'r', encoding='utf-8') as f:
    content = f.read()

old = "physical_fields = {f.id for f in meta_obj.fields if str(getattr(f, 'storage', '')) != 'virtual'}"
new = "physical_fields = {f.id for f in meta_obj.fields if getattr(f, 'storage', None) != FieldStorage.VIRTUAL}"

if old in content:
    content = content.replace(old, new)
    
    # 确保导入了 FieldStorage
    if 'from meta.core.models import FieldStorage' not in content:
        # 在已有的 registry import 旁边添加
        content = content.replace(
            'from meta.core.models import registry as meta_registry',
            'from meta.core.models import registry as meta_registry, FieldStorage'
        )
    
    with open('meta/api/manage_api.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('OK: fixed to use FieldStorage.VIRTUAL enum comparison')
else:
    print('ERROR: pattern not found')

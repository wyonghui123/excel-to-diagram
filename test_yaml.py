import yaml
with open('meta/schemas/user_group.yaml', 'r', encoding='utf-8') as f:
    data = yaml.safe_load(f)

for field in data.get('fields', []):
    if field.get('id') in ('parent_id', 'manager_id'):
        ui = field.get('ui', {})
        print(f"{field.get('id')}: multiple={ui.get('multiple')}, type={type(ui.get('multiple'))}")

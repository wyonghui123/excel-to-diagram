import requests
r = requests.get('http://localhost:3004/src/components/common/ObjectPage/ObjectPageField.vue')
text = r.text
for kw in ['onFieldDisplayUpdate', 'onUpdate:DisplayValue', 'onUpdate:display', 'onFieldDisplay', 'update:display']:
    idx = text.find(kw)
    print(f'{kw}: {idx if idx >= 0 else "NOT FOUND"}')

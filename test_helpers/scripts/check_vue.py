import requests
r = requests.get('http://localhost:3004/src/components/common/DetailPage/DetailPage.vue')
text = r.text
for kw in ['onFieldDisplayUpdate', 'fieldDisplay', 'field-display', 'fieldUpdate', 'handleFieldDisplayUpdate', 'field-update']:
    idx = text.find(kw)
    print(f'{kw}: {"found at " + str(idx) if idx >= 0 else "NOT FOUND"}')

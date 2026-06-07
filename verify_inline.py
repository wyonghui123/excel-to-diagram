import requests

print("=" * 60)
print("Inline编辑功能验证")
print("=" * 60)

# 登录获取token
r = requests.post('http://localhost:3005/api/v1/auth/login', 
                   json={'username':'admin','password':'admin123'}, 
                   timeout=10)
token = r.json()['data']['token']

# 获取view-config
r2 = requests.get('http://localhost:3005/api/v2/meta/enum_type/view-config/default',
                   headers={'Authorization': f'Bearer {token}'},
                   timeout=15)

if r2.status_code == 200:
    data = r2.json()
    list_config = data['data']['list']
    
    print(f"\n[OK] API返回成功")
    print(f"   list配置keys: {list(list_config.keys())}")
    print(f"   inlineEdit: {list_config.get('inlineEdit', 'NOT FOUND')}")
    
    if 'inlineEdit' in list_config:
        ie = list_config['inlineEdit']
        print(f"\n   [OK] inlineEdit配置详情:")
        print(f"      enabled: {ie.get('enabled', 'MISSING')}")
        print(f"      mode: {ie.get('mode', 'MISSING')}")
        print(f"      autoSave: {ie.get('autoSave', 'MISSING')}")
        print(f"      toolbarPosition: {ie.get('toolbarPosition', 'MISSING')}")
    else:
        print(f"\n   [X] inlineEdit配置缺失!")
else:
    print(f"\n[X] API请求失败: {r2.status_code}")
    print(r2.text[:300])

print("\n" + "=" * 60)
print("验证完成")
print("=" * 60)
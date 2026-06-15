#!/usr/bin/env python3
"""验证所有测试场景"""
import urllib.request, http.cookiejar, json

def check_product(name):
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    op.open('http://localhost:3010/api/v1/auth/dev-login?username=admin')
    
    r = op.open(f'http://localhost:3010/api/v2/bo/product?name={name}')
    products = json.loads(r.read().decode())['data']['items']
    
    if not products:
        print(f'❌ {name}: 不存在')
        return False
    
    p = products[0]
    pid = p['id']
    r2 = op.open(f'http://localhost:3010/api/v2/bo/version?product_id={pid}&page_size=20')
    versions = json.loads(r2.read().decode())['data']['items']
    
    print(f'✅ {name}: id={pid}, versions={len(versions)}')
    for v in versions:
        print(f'   - {v["name"]}')
    return True

print('=== 验证所有测试场景 ===\n')

# 场景 1: add 模式创建产品+版本
check_product('TEST888888')

# 场景 2: 已有产品添加版本
check_product('TEST99999')

# 场景 3: 之前失败的案例
check_product('TEST888121')
check_product('TEST888122')

print('\n=== 验证完成 ===')

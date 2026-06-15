#!/usr/bin/env python3
"""
扫描数据权限 + 维度 + 值列表端点
"""
import urllib.request
import http.cookiejar
import json
import time

BASE = 'http://localhost:3010'
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open(BASE + '/api/v1/auth/dev-login?username=admin')
time.sleep(0.5)

# 数据权限相关端点
endpoints = [
    # 数据权限
    '/api/v2/bo/data_scope?page_size=3',
    '/api/v2/bo/data_permission?page_size=3',
    '/api/v2/bo/role_data_permission?page_size=3',
    '/api/v2/bo/employee_data_scope?page_size=3',
    '/api/v2/bo/user_data_scope?page_size=3',
    '/api/v2/bo/group_data_permission?page_size=3',
    # 维度
    '/api/v2/bo/dimension?page_size=3',
    '/api/v2/bo/dimension_object_mapping?page_size=3',
    '/api/v2/bo/dimension_value?page_size=3',
    # 值列表
    '/api/v2/bo/value_list?page_size=3',
    '/api/v2/bo/filter_variant?page_size=3',
    # 业务对象
    '/api/v2/bo/business_object?page_size=3',
    '/api/v2/bo/service_module?page_size=3',
    '/api/v2/bo/sub_domain?page_size=3',
    '/api/v2/bo/composite_entity?page_size=3',
    '/api/v2/bo/composite?page_size=3',
    # 数据域
    '/api/v2/bo/data_domain?page_size=3',
    # 主数据
    '/api/v2/bo/master_data?page_size=3',
    # 表单 schema
    '/api/v2/bo/form_schema?page_size=3',
    '/api/v2/bo/list_schema?page_size=3',
]

print(f"{'endpoint':<60} {'status':<6} {'items':<8} {'first_key'}")
print('-' * 100)
for ep in endpoints:
    try:
        r = opener.open(BASE + ep, timeout=5)
        body = json.loads(r.read().decode())
        items = body.get('data', {}).get('items', [])
        first_key = list(items[0].keys())[:3] if items else '-'
        print(f"{ep:<60} {r.status:<6} {len(items):<8} {first_key}")
    except urllib.error.HTTPError as e:
        print(f"{ep:<60} {e.code:<6} -        -")
    except Exception as e:
        print(f"{ep:<60} ERR     -        -")

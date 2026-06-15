#!/usr/bin/env python3
"""
扫描主数据/表单 schema/UI schema/工作流端点
"""
import urllib.request
import http.cookiejar
import json

BASE = 'http://localhost:3010'
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
opener.open(BASE + '/api/v1/auth/dev-login?username=admin')

endpoints = [
    # 主数据
    '/api/v2/bo/master_data?page_size=3',
    '/api/v2/bo/master-data?page_size=3',
    '/api/v2/master_data?page_size=3',
    # 表单 schema
    '/api/v2/bo/form_schema?page_size=3',
    '/api/v2/bo/form-schema?page_size=3',
    '/api/v2/form_schemas?page_size=3',
    '/api/v2/bo/form_layout?page_size=3',
    # 列表 schema
    '/api/v2/bo/list_schema?page_size=3',
    '/api/v2/bo/list-schema?page_size=3',
    '/api/v2/list_schemas?page_size=3',
    # UI schema
    '/api/v2/bo/ui_schema?page_size=3',
    '/api/v2/ui_schemas?page_size=3',
    # 工作流
    '/api/v2/bo/workflow?page_size=3',
    '/api/v2/bo/workflow_instance?page_size=3',
    '/api/v2/bo/workflow_task?page_size=3',
    # 节点
    '/api/v2/bo/node?page_size=3',
    '/api/v2/bo/page?page_size=3',
    # 路由
    '/api/v2/bo/route?page_size=3',
    '/api/v2/bo/menu?page_size=3',
    # 国际化
    '/api/v2/bo/i18n?page_size=3',
    '/api/v2/bo/translation?page_size=3',
    '/api/v2/i18n?page_size=3',
    # 标签/分类
    '/api/v2/bo/tag?page_size=3',
    '/api/v2/bo/category?page_size=3',
    # 模板
    '/api/v2/bo/template?page_size=3',
    '/api/v2/bo/email_template?page_size=3',
    # API 资源
    '/api/v2/bo/api_resource?page_size=3',
    '/api/v2/bo/api_endpoint?page_size=3',
    # 缓存
    '/api/v2/bo/cache_config?page_size=3',
    # 元数据
    '/api/v2/bo/metadata?page_size=3',
    '/api/v2/bo/meta_entity?page_size=3',
    '/api/v2/bo/meta_field?page_size=3',
    # 视图
    '/api/v2/bo/view?page_size=3',
    '/api/v2/bo/view_config?page_size=3',
]

print(f"{'endpoint':<55} {'status':<6} {'items':<8} {'first_keys'}")
print('-' * 100)
for ep in endpoints:
    try:
        r = opener.open(BASE + ep, timeout=5)
        body = json.loads(r.read().decode())
        items = body.get('data', {}).get('items', [])
        first_keys = list(items[0].keys())[:4] if items else '-'
        print(f"{ep:<55} {r.status:<6} {len(items):<8} {first_keys}")
    except urllib.error.HTTPError as e:
        print(f"{ep:<55} {e.code:<6} -        -")
    except Exception as e:
        print(f"{ep:<55} ERR     -        {str(e)[:30]}")

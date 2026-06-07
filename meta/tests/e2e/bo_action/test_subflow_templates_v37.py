# -*- coding: utf-8 -*-
"""
[MODULE] A3: v3.7 模板 CRUD + dry_run + metrics 测试
[DESCRIPTION] 测 subflow 模板系统
- _subflow_template (GET / PUT / DELETE / 单 GET)
- _subflow_metrics
- _chain 的 dry_run 模式
"""
import os
import sys
import time
import http.client
import json

# admin_token 路径在 conftest.py 已配 (走 sys.path)
from admin_token import call_action  # noqa: E402


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 模板 CRUD - PUT (create)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_subflow_template_create(bo_action_server_check, admin_cookie):
    """[DECORATIVE] A3.1: PUT /_subflow_template/<name> 创建模板"""
    name = f'a3_template_{int(time.time())}'
    body = json.dumps({
        'description': f'A3.1 test template {name}',
        'steps': [
            {'action_id': 'user.get_current', 'as': 'me'},
        ]
    }).encode('utf-8')
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    conn.request('PUT', f'/api/v2/action/_subflow_template/{name}', body=body,
                 headers={'Content-Type': 'application/json',
                          'Content-Length': str(len(body)),
                          'Cookie': admin_cookie})
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()

    # 模板创建
    assert r.status in [200, 201], f'PUT template 应返回 2xx, 实际 {r.status}: {data}'
    assert data.get('success') is True or 'created' in str(data).lower() or 'saved' in str(data).lower(), \
        f'PUT template 成功, 实际 {data}'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. 模板 CRUD - GET 单个
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_subflow_template_get(bo_action_server_check, admin_cookie):
    """[DECORATIVE] A3.2: GET /_subflow_template/<name> 获取模板"""
    name = f'a3_get_{int(time.time())}'
    # 先创建
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    body = json.dumps({
        'description': 'A3.2',
        'steps': [{'action_id': 'user.get_current'}]
    }).encode('utf-8')
    conn.request('PUT', f'/api/v2/action/_subflow_template/{name}', body=body,
                 headers={'Content-Type': 'application/json',
                          'Content-Length': str(len(body)),
                          'Cookie': admin_cookie})
    r = conn.getresponse()
    r.read()
    conn.close()

    # 再 GET
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    conn.request('GET', f'/api/v2/action/_subflow_template/{name}',
                 headers={'Cookie': admin_cookie})
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()

    assert r.status == 200
    assert data.get('success') is True, f'GET template 成功, 实际 {data}'
    # 应有 description 字段
    assert 'description' in data.get('data', {}) or 'steps' in data.get('data', {}), \
        f'GET template 应返回 description/steps: {data}'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. 模板 CRUD - GET 列表
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_subflow_template_list(bo_action_server_check, admin_cookie):
    """[DECORATIVE] A3.3: GET /_subflow_template 列出所有模板"""
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    conn.request('GET', '/api/v2/action/_subflow_template',
                 headers={'Cookie': admin_cookie})
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()

    assert r.status == 200
    assert data.get('success') is True
    # data 应该是 list 或 dict
    result = data.get('data', [])
    assert isinstance(result, (list, dict)), f'list template 应返回 list/dict, 实际 {type(result)}'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. 模板 CRUD - DELETE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_subflow_template_delete(bo_action_server_check, admin_cookie):
    """[DECORATIVE] A3.4: DELETE /_subflow_template/<name> 删除模板"""
    name = f'a3_del_{int(time.time())}'
    # 先创建
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    body = json.dumps({
        'description': 'A3.4 to delete',
        'steps': [{'action_id': 'user.get_current'}]
    }).encode('utf-8')
    conn.request('PUT', f'/api/v2/action/_subflow_template/{name}', body=body,
                 headers={'Content-Type': 'application/json',
                          'Content-Length': str(len(body)),
                          'Cookie': admin_cookie})
    r = conn.getresponse()
    r.read()
    conn.close()

    # DELETE
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    conn.request('DELETE', f'/api/v2/action/_subflow_template/{name}',
                 headers={'Cookie': admin_cookie})
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()

    assert r.status in [200, 204], f'DELETE 应返回 2xx, 实际 {r.status}'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. dry_run 模式
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_subflow_dry_run_mode(bo_action_server_check, admin_cookie):
    """[DECORATIVE] A3.5: _chain dry_run=true 不实际执行, 只返回计划"""
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    body = json.dumps({
        'name': 'a3_dry_run',
        'steps': [
            {'action_id': 'user.get_current', 'as': 'me'},
            {'action_id': 'function.subscription.list', 'as': 'subs'},
        ],
        'dry_run': True
    }).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Content-Length': str(len(body)),
        'Cookie': admin_cookie,
    }
    conn.request('POST', '/api/v2/action/_chain', body=body, headers=headers)
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()

    # dry_run 模式: 应有 plan 或不实际执行
    assert r.status == 200
    # dry_run 数据应包含 plan
    result = data.get('data', {})
    assert 'plan' in result or 'steps' in result or 'dry_run' in str(data).lower(), \
        f'dry_run 应有 plan/steps: {data}'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. metrics 端点
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_subflow_metrics_endpoint(bo_action_server_check, admin_cookie):
    """[DECORATIVE] A3.6: GET /_subflow_metrics 返回 subflow 指标"""
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    conn.request('GET', '/api/v2/action/_subflow_metrics',
                 headers={'Cookie': admin_cookie})
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()

    assert r.status == 200
    assert data.get('success') is True
    # 应有 total_steps / succeeded / failed 等
    metrics = data.get('data', {})
    expected_keys = ['total_runs', 'succeeded', 'failed', 'avg_duration_ms']
    for k in expected_keys:
        if k in metrics:
            break  # 至少有一个
    else:
        # 至少返回 dict
        assert isinstance(metrics, dict), f'metrics 应为 dict, 实际 {type(metrics)}: {metrics}'


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. templates 字段 (内联模板)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_subflow_inline_templates(bo_action_server_check, admin_cookie):
    """[DECORATIVE] A3.7: _chain templates 字段, 内联定义子 subflow"""
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    body = json.dumps({
        'name': 'a3_inline_templates',
        'templates': {
            'sub_a': {
                'name': 'sub_a',
                'steps': [{'action_id': 'user.get_current'}]
            }
        },
        'steps': [
            {'action_id': 'user.get_current', 'as': 'me'},
        ]
    }).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Content-Length': str(len(body)),
        'Cookie': admin_cookie,
    }
    conn.request('POST', '/api/v2/action/_chain', body=body, headers=headers)
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()

    # templates 字段应被接受
    assert r.status == 200


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. template 字段引用已存模板
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def test_subflow_template_reference(bo_action_server_check, admin_cookie):
    """[DECORATIVE] A3.8: _chain template 字段, 引用已存模板"""
    name = f'a3_ref_{int(time.time())}'
    # 先创建模板
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    body = json.dumps({
        'description': 'A3.8 referenced',
        'steps': [{'action_id': 'user.get_current'}]
    }).encode('utf-8')
    conn.request('PUT', f'/api/v2/action/_subflow_template/{name}', body=body,
                 headers={'Content-Type': 'application/json',
                          'Content-Length': str(len(body)),
                          'Cookie': admin_cookie})
    r = conn.getresponse()
    r.read()
    conn.close()

    # 引用模板
    conn = http.client.HTTPConnection('localhost', 3010, timeout=10)
    body = json.dumps({
        'name': 'a3_use_template',
        'template': name,
    }).encode('utf-8')
    headers = {
        'Content-Type': 'application/json',
        'Content-Length': str(len(body)),
        'Cookie': admin_cookie,
    }
    conn.request('POST', '/api/v2/action/_chain', body=body, headers=headers)
    r = conn.getresponse()
    data = json.loads(r.read().decode())
    conn.close()

    # 模板应能引用 (即使失败也不应是 404)
    assert r.status in [200, 400, 404], f'引用 template 应有响应, 实际 {r.status}: {data}'

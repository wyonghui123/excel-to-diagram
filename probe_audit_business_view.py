"""
业务人员视角: 走查 6 类对象详情页的 audit_log API 返回,
重点关注: 业务可读性 + 是否含技术性内容
"""
import requests
import json

r = requests.post('http://localhost:3010/api/v1/auth/login', json={'username': 'admin', 'password': 'admin123'}, timeout=5)
cookies = {'auth_token': r.json()['data']['token']}

cases = [
    ('domain', 683, '领域'),
    ('sub_domain', 68, '子领域'),
    ('relationship', 35, '关系'),
    ('business_object', 468, '业务对象 (供应商)'),
    ('user', 1, '用户 (admin)'),
    ('role', 1, '角色 (admin)'),
    ('user_group', 8217, '用户组 (测试组_511983)'),
    ('annotation', 4, '备注 (annotation)'),
]

for ot, oid, label in cases:
    print('=' * 80)
    print(f'{label}: /api/v1/audit/logs?object_type={ot}&object_id={oid}&parent_object_id={oid}')
    print('=' * 80)
    r = requests.get(
        f'http://localhost:3010/api/v1/audit/logs?object_type={ot}&object_id={oid}&parent_object_id={oid}&page=1&page_size=3',
        cookies=cookies, timeout=5)
    data = r.json()
    print(f'total={data.get("total")}')
    for it in data.get('data', [])[:2]:
        print(f'\n  [{it["id"]}] {it.get("action")} {it.get("object_type")}/{it.get("object_id")} field={it.get("field_name")} by={it.get("user_name")}')
        # 检查技术性字段
        technical = []
        for k in ['ip_address', 'user_agent', 'trace_id', 'transaction_id',
                  'agent_id', 'agent_session_id', 'tool_call_id', 'agent_reasoning',
                  'log_category', 'log_level', 'status', 'retry_count',
                  'error_message', 'retention_until', 'cascade_root_id', 'cascade_root_action',
                  'outcome', 'parent_object_type', 'parent_object_id', 'parent_action_id']:
            v = it.get(k)
            if v is not None and v != '':
                if k in ('ip_address', 'user_agent', 'trace_id', 'transaction_id', 'agent_xx', 'error_message', 'retention_until', 'cascade_root_id', 'cascade_root_action'):
                    technical.append(f'{k}={v!r:.60s}')
        if technical:
            print(f'  [技术性字段]:')
            for t in technical:
                print(f'    - {t}')
        # 看 old/new value
        for k in ['old_value', 'new_value', 'extra_data']:
            v = it.get(k)
            if v:
                preview = str(v)[:100]
                print(f'  {k}: {preview!r}')
    print()

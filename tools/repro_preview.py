#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
[yonaa 现场诊断 4] 复现 /architecture/preview
"""
import os, sys, json
os.environ['JWT_SECRET_KEY'] = 'test'
os.environ['FLASK_SECRET_KEY'] = 'test'
sys.path.insert(0, '.')

from flask import Flask
app = Flask(__name__)

# disable login_required
import meta.api.bo_api as bo_api_mod
from functools import wraps
def fake_login_required(fn):
    @wraps(fn)
    def wrapped(*a, **k):
        return fn(*a, **k)
    return wrapped

# patch login_required
import inspect
src = inspect.getsource(bo_api_mod)
# patch global
bo_api_mod.login_required = fake_login_required

with app.test_request_context('/architecture/preview?version_id=1'):
    import meta.api.bo_api as bo_api_mod
    # 获取 wrapped 函数
    fn = bo_api_mod.get_architecture_preview
    # 跳过 login_required: 直接拿 wrapped function
    if hasattr(fn, '__wrapped__'):
        fn = fn.__wrapped__
    try:
        r = fn()
        if isinstance(r, tuple):
            body, status = r
            j = body.get_json() if hasattr(body, 'get_json') else json.loads(body.data)
        else:
            j = r.get_json()
            status = r.status_code
        print(f'status: {status}')
        print(f'success: {j.get("success")}')
        if not j.get('success'):
            print(f'message: {j.get("message")}')
        else:
            d = j.get('data', {})
            for k in ['domains','sub_domains','service_modules','business_objects','relationships']:
                print(f'  {k}: {len(d.get(k, []))}')
    except Exception as e:
        import traceback
        print(f'ERR: {type(e).__name__}: {e}')
        traceback.print_exc()

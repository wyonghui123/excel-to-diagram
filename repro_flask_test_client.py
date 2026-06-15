"""[REPRO 4] 用 Flask test client 真实跑一次 preview 端点"""
import sys, os
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.path.insert(0, '.')

# 启动 server 但不走端口
from meta.server import create_app
app = create_app()

with app.test_client() as c:
    # login
    r = c.get('/api/v1/auth/dev-login?username=admin')
    print('login:', r.status_code)

    # preview
    r = c.post('/api/v2/key-template/preview/relationship',
        json={'field_values': {},
              'parent_params': {'source_bo_id': 468, 'target_bo_id': 467},
              'generate': False})
    print('preview:', r.status_code)
    import json
    print(r.get_data(as_text=True)[:500])
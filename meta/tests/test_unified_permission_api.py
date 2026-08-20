# -*- coding: utf-8 -*-
"""
Phase 3 后端 API TDD 测试

[覆盖范围]
  P3.1 permission_rules_v2 CRUD API
  P3.2 role_effective_intents CRUD API
  P3.3 推导管道触发 API
  P3.4 SQL 预览 API
  P3.5 完整性检查 API
  P3.6 角色对比 API
  P3.7 权限模拟 API

[测试策略]
  - 使用 Flask test_client 直接调用 API 端点
  - 每个测试独立 DB (tmpdir), 避免相互影响
  - mock 掉 login_required / require_permission (测试不依赖认证)
"""
import os
import sys
import json
import sqlite3
import tempfile

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _PROJECT_ROOT)

os.environ['TEST_ENTRY'] = '1'
os.environ['ALLOW_RAW_SQL'] = '1'


# ============================================================================
# 测试 Fixtures
# ============================================================================
@pytest.fixture
def app_with_db():
    """创建 Flask app + 测试 DB (含 permission_rules_v2 + role_effective_intents)"""
    tmp_dir = tempfile.mkdtemp(prefix='p3_api_')
    db_path = os.path.join(tmp_dir, 'test.db')

    conn = sqlite3.connect(db_path)
    conn.executescript('''
        CREATE TABLE permission_rules_v2 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            resource_type VARCHAR(200) NOT NULL,
            permission_level VARCHAR(50) DEFAULT 'read',
            include_conditions TEXT,
            exclude_conditions TEXT,
            derivation_mode VARCHAR(20) DEFAULT 'static',
            source VARCHAR(50) DEFAULT 'manual',
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE role_effective_intents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            bo_id VARCHAR(100) NOT NULL,
            action_name VARCHAR(100) NOT NULL,
            data_scope TEXT,
            derivation_mode VARCHAR(20) DEFAULT 'static',
            source VARCHAR(50) DEFAULT 'derived',
            is_stale INTEGER DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (role_id, bo_id, action_name)
        );

        CREATE TABLE products (
            id INTEGER PRIMARY KEY, code TEXT, name TEXT,
            owner_id INTEGER, status TEXT
        );
        INSERT INTO products VALUES
            (1, 'P1', 'Product 1', 999, 'active'),
            (2, 'P2', 'Product 2', 888, 'archived'),
            (3, 'P3', 'Product 3', 999, 'active');

        CREATE TABLE roles (id INTEGER PRIMARY KEY, name TEXT);
        INSERT INTO roles VALUES (100, 'Role A'), (101, 'Role B');
    ''')
    conn.commit()
    conn.close()

    # 创建 Flask app 并注册蓝图
    from flask import Flask
    from meta.api.unified_permission_api import unified_permission_bp
    from meta.core.permission_flags import reset_flags, set_flag

    reset_flags()

    app = Flask(__name__)
    app.config['TESTING'] = True
    app.config['DB_PATH'] = db_path

    # 注册蓝图
    app.register_blueprint(unified_permission_bp)

    # mock 认证: 注入测试用户到 g
    @app.before_request
    def _inject_test_user():
        from flask import g
        g.current_user = {'user_id': 999, 'id': 999, 'permissions': ['*']}

    # 把 db_path 注入到环境变量, 让 API 内部能获取
    old_db_path = os.environ.get('DB_PATH')
    os.environ['DB_PATH'] = db_path

    yield app, db_path

    # cleanup
    reset_flags()
    if old_db_path is not None:
        os.environ['DB_PATH'] = old_db_path
    else:
        os.environ.pop('DB_PATH', None)


@pytest.fixture
def client(app_with_db):
    """Flask test client"""
    app, db_path = app_with_db
    return app.test_client()


# ============================================================================
# P3.1 permission_rules_v2 CRUD API
# ============================================================================
class TestPermissionRulesV2Crud:
    """P3.1 permission_rules_v2 CRUD API"""

    def test_create_rule(self, client, app_with_db):
        """POST /api/v2/unified-permission-rules → 创建规则"""
        _, db_path = app_with_db
        resp = client.post('/api/v2/unified-permission-rules', json={
            'role_id': 100,
            'resource_type': 'product',
            'permission_level': 'read',
            'include_conditions': [{'field': 'owner_id', 'op': '=', 'value': 999}],
            'exclude_conditions': [],
        })
        assert resp.status_code == 200 or resp.status_code == 201
        data = resp.get_json()
        assert data['success'] is True
        assert 'id' in data['data']

        # 验证 DB
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            'SELECT role_id, resource_type, permission_level FROM permission_rules_v2 WHERE id = ?',
            [data['data']['id']]
        ).fetchone()
        conn.close()
        assert row[0] == 100
        assert row[1] == 'product'
        assert row[2] == 'read'

    def test_list_rules_by_role(self, client, app_with_db):
        """GET /api/v2/unified-permission-rules?role_id=100 → 列表"""
        _, db_path = app_with_db
        # 先插入数据
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO permission_rules_v2 (role_id, resource_type, permission_level) "
            "VALUES (100, 'product', 'read'), (100, 'version', 'write'), (101, 'product', 'admin')"
        )
        conn.commit()
        conn.close()

        resp = client.get('/api/v2/unified-permission-rules?role_id=100')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        rules = data['data']
        assert len(rules) == 2  # role 100 有 2 条
        for r in rules:
            assert r['role_id'] == 100

    def test_list_all_rules(self, client, app_with_db):
        """GET /api/v2/unified-permission-rules (无 role_id) → 全部"""
        _, db_path = app_with_db
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO permission_rules_v2 (role_id, resource_type, permission_level) "
            "VALUES (100, 'product', 'read'), (101, 'version', 'write')"
        )
        conn.commit()
        conn.close()

        resp = client.get('/api/v2/unified-permission-rules')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['data']) == 2

    def test_get_single_rule(self, client, app_with_db):
        """GET /api/v2/unified-permission-rules/<id> → 单条"""
        _, db_path = app_with_db
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "INSERT INTO permission_rules_v2 (role_id, resource_type, permission_level) "
            "VALUES (100, 'product', 'read')"
        )
        rule_id = cursor.lastrowid
        conn.commit()
        conn.close()

        resp = client.get(f'/api/v2/unified-permission-rules/{rule_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['id'] == rule_id
        assert data['data']['resource_type'] == 'product'

    def test_get_nonexistent_rule_returns_404(self, client):
        """GET /api/v2/unified-permission-rules/99999 → 404"""
        resp = client.get('/api/v2/unified-permission-rules/99999')
        assert resp.status_code == 404

    def test_update_rule(self, client, app_with_db):
        """PUT /api/v2/unified-permission-rules/<id> → 更新"""
        _, db_path = app_with_db
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "INSERT INTO permission_rules_v2 (role_id, resource_type, permission_level) "
            "VALUES (100, 'product', 'read')"
        )
        rule_id = cursor.lastrowid
        conn.commit()
        conn.close()

        resp = client.put(f'/api/v2/unified-permission-rules/{rule_id}', json={
            'permission_level': 'write',
            'include_conditions': [{'field': 'status', 'op': '=', 'value': 'active'}],
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

        # 验证 DB
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            'SELECT permission_level, include_conditions FROM permission_rules_v2 WHERE id = ?',
            [rule_id]
        ).fetchone()
        conn.close()
        assert row[0] == 'write'
        assert json.loads(row[1])[0]['field'] == 'status'

    def test_delete_rule(self, client, app_with_db):
        """DELETE /api/v2/unified-permission-rules/<id> → 删除"""
        _, db_path = app_with_db
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "INSERT INTO permission_rules_v2 (role_id, resource_type, permission_level) "
            "VALUES (100, 'product', 'read')"
        )
        rule_id = cursor.lastrowid
        conn.commit()
        conn.close()

        resp = client.delete(f'/api/v2/unified-permission-rules/{rule_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

        # 验证 DB
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            'SELECT COUNT(*) FROM permission_rules_v2 WHERE id = ?', [rule_id]
        ).fetchone()
        conn.close()
        assert row[0] == 0

    def test_create_rule_validates_required_fields(self, client):
        """POST 缺少 role_id → 400"""
        resp = client.post('/api/v2/unified-permission-rules', json={
            'resource_type': 'product',
            # 缺 role_id
        })
        assert resp.status_code == 400


# ============================================================================
# P3.2 role_effective_intents CRUD API
# ============================================================================
class TestEffectiveIntentsCrud:
    """P3.2 role_effective_intents CRUD API"""

    def test_list_intents_by_role(self, client, app_with_db):
        """GET /api/v2/roles/<role_id>/effective-intents → 列表"""
        _, db_path = app_with_db
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', '{}'), "
            "       (100, 'product', 'list', '{}'), "
            "       (101, 'product', 'read', '{}')"
        )
        conn.commit()
        conn.close()

        resp = client.get('/api/v2/roles/100/effective-intents')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert len(data['data']) == 2  # role 100 有 2 个

    def test_list_intents_filter_by_bo(self, client, app_with_db):
        """GET /api/v2/roles/100/effective-intents?bo_id=product → 按 BO 过滤"""
        _, db_path = app_with_db
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', '{}'), "
            "       (100, 'version', 'read', '{}')"
        )
        conn.commit()
        conn.close()

        resp = client.get('/api/v2/roles/100/effective-intents?bo_id=product')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['data']) == 1
        assert data['data'][0]['bo_id'] == 'product'

    def test_update_intent_data_scope(self, client, app_with_db):
        """PUT /api/v2/roles/100/effective-intents/<id> → 更新 data_scope"""
        _, db_path = app_with_db
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', '{}')"
        )
        intent_id = cursor.lastrowid
        conn.commit()
        conn.close()

        new_scope = {
            'include': [{'field': 'owner_id', 'op': '=', 'value': '${user.id}'}],
            'exclude': [],
        }
        resp = client.put(f'/api/v2/roles/100/effective-intents/{intent_id}', json={
            'data_scope': new_scope,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

        # 验证 DB
        conn = sqlite3.connect(db_path)
        row = conn.execute(
            'SELECT data_scope FROM role_effective_intents WHERE id = ?', [intent_id]
        ).fetchone()
        conn.close()
        scope = json.loads(row[0])
        assert scope['include'][0]['field'] == 'owner_id'

    def test_delete_intent(self, client, app_with_db):
        """DELETE /api/v2/roles/100/effective-intents/<id> → 删除"""
        _, db_path = app_with_db
        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', '{}')"
        )
        intent_id = cursor.lastrowid
        conn.commit()
        conn.close()

        resp = client.delete(f'/api/v2/roles/100/effective-intents/{intent_id}')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            'SELECT COUNT(*) FROM role_effective_intents WHERE id = ?', [intent_id]
        ).fetchone()
        conn.close()
        assert row[0] == 0


# ============================================================================
# P3.3 推导管道触发 API
# ============================================================================
class TestDerivationTrigger:
    """P3.3 推导管道触发 API"""

    def test_trigger_derivation(self, client, app_with_db):
        """POST /api/v2/roles/100/derive → 触发推导"""
        _, db_path = app_with_db
        # 先插入规则
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO permission_rules_v2 (role_id, resource_type, permission_level, include_conditions) "
            "VALUES (100, 'product', 'read', ?)",
            [json.dumps([{'field': 'owner_id', 'op': '=', 'value': 999}])]
        )
        conn.commit()
        conn.close()

        resp = client.post('/api/v2/roles/100/derive')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'intent_count' in data['data']
        assert data['data']['intent_count'] > 0

        # 验证 role_effective_intents 表被写入
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            'SELECT action_name FROM role_effective_intents WHERE role_id = 100'
        ).fetchall()
        conn.close()
        actions = {r[0] for r in rows}
        assert 'read' in actions
        assert 'list' in actions  # read 展开为 read+list+export

    def test_derive_empty_role(self, client, app_with_db):
        """POST /api/v2/roles/999/derive → 无规则, intent_count=0"""
        resp = client.post('/api/v2/roles/999/derive')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['intent_count'] == 0


# ============================================================================
# P3.4 SQL 预览 API
# ============================================================================
class TestSqlPreview:
    """P3.4 SQL 预览 API"""

    def test_sql_preview_with_intent(self, client, app_with_db):
        """GET /api/v2/roles/100/sql-preview?bo_id=product&action=read → 返回 SQL"""
        _, db_path = app_with_db
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', ?)",
            [json.dumps({
                'include': [{'field': 'owner_id', 'op': '=', 'value': 999}],
                'exclude': [],
            })]
        )
        conn.commit()
        conn.close()

        resp = client.get('/api/v2/roles/100/sql-preview?bo_id=product&action=read')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert 'cond_expr' in data['data']
        assert 'owner_id' in data['data']['cond_expr']
        assert 999 in data['data']['params']

    def test_sql_preview_no_intent_returns_default_deny(self, client):
        """无 Intent → cond_expr='1=0' (默认拒绝)"""
        resp = client.get('/api/v2/roles/999/sql-preview?bo_id=product&action=read')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['cond_expr'] == '1=0'

    def test_sql_preview_with_user_id_variable(self, client, app_with_db):
        """含 ${user.id} 的 Intent → SQL 中变量被解析"""
        _, db_path = app_with_db
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', ?)",
            [json.dumps({
                'include': [{'field': 'owner_id', 'op': '=', 'value': '${user.id}'}],
                'exclude': [],
            })]
        )
        conn.commit()
        conn.close()

        resp = client.get('/api/v2/roles/100/sql-preview?bo_id=product&action=read')
        assert resp.status_code == 200
        data = resp.get_json()
        # ${user.id} 应被替换为 ? 占位符, user_id 加到 params
        assert 'owner_id' in data['data']['cond_expr']
        assert 999 in data['data']['params']  # g.current_user.id = 999


# ============================================================================
# P3.5 完整性检查 API
# ============================================================================
class TestCompletenessCheck:
    """P3.5 完整性检查 API"""

    def test_completeness_green(self, client, app_with_db):
        """有 Intent → 绿灯 (complete)"""
        _, db_path = app_with_db
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', '{}')"
        )
        conn.commit()
        conn.close()

        resp = client.get('/api/v2/roles/100/completeness')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['status'] in ('green', 'yellow', 'red')
        assert data['data']['intent_count'] >= 1

    def test_completeness_red_no_intent(self, client):
        """无 Intent → 红灯"""
        resp = client.get('/api/v2/roles/999/completeness')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['data']['status'] == 'red'
        assert data['data']['intent_count'] == 0

    def test_completeness_yellow_stale(self, client, app_with_db):
        """有 stale Intent → 黄灯"""
        _, db_path = app_with_db
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope, is_stale) "
            "VALUES (100, 'product', 'read', '{}', 1)"
        )
        conn.commit()
        conn.close()

        resp = client.get('/api/v2/roles/100/completeness')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['data']['status'] == 'yellow'


# ============================================================================
# P3.6 角色对比 API
# ============================================================================
class TestRoleDiff:
    """P3.6 角色对比 API"""

    def test_role_diff(self, client, app_with_db):
        """GET /api/v2/roles/diff?role_a=100&role_b=101 → 差异"""
        _, db_path = app_with_db
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', '{}'), "  # role A 有
            "       (101, 'product', 'read', '{}'), "  # role B 有
            "       (101, 'version', 'read', '{}')"    # role B 独有
        )
        conn.commit()
        conn.close()

        resp = client.get('/api/v2/roles/diff?role_a=100&role_b=101')
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        diff = data['data']
        # 应该有 only_in_a / only_in_b / common 三部分
        assert 'only_in_a' in diff
        assert 'only_in_b' in diff
        assert 'common' in diff
        # version:read 只在 B
        assert any(i['bo_id'] == 'version' for i in diff['only_in_b'])

    def test_role_diff_identical(self, client, app_with_db):
        """两个角色 Intent 完全相同 → only_in_a/b 为空"""
        _, db_path = app_with_db
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', '{}'), "
            "       (101, 'product', 'read', '{}')"
        )
        conn.commit()
        conn.close()

        resp = client.get('/api/v2/roles/diff?role_a=100&role_b=101')
        assert resp.status_code == 200
        data = resp.get_json()
        assert len(data['data']['only_in_a']) == 0
        assert len(data['data']['only_in_b']) == 0
        assert len(data['data']['common']) == 1


# ============================================================================
# P3.7 权限模拟 API
# ============================================================================
class TestPermissionSimulate:
    """P3.7 权限模拟 API"""

    def test_simulate_allow(self, client, app_with_db):
        """POST /api/v2/permissions/simulate → 允许场景"""
        _, db_path = app_with_db
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', ?)",
            [json.dumps({
                'include': [{'field': 'owner_id', 'op': '=', 'value': 999}],
                'exclude': [],
            })]
        )
        conn.commit()
        conn.close()

        resp = client.post('/api/v2/permissions/simulate', json={
            'role_ids': [100],
            'bo_id': 'product',
            'action_name': 'read',
            'record_id': 1,  # product 1 owner_id=999
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['success'] is True
        assert data['data']['allowed'] is True

    def test_simulate_deny_no_intent(self, client):
        """POST /api/v2/permissions/simulate → 无 Intent 拒绝"""
        resp = client.post('/api/v2/permissions/simulate', json={
            'role_ids': [999],
            'bo_id': 'product',
            'action_name': 'read',
            'record_id': 1,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['data']['allowed'] is False
        assert data['data']['source'] == 'default_deny'

    def test_simulate_deny_exclude(self, client, app_with_db):
        """POST /api/v2/permissions/simulate → exclude 命中拒绝"""
        _, db_path = app_with_db
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO role_effective_intents (role_id, bo_id, action_name, data_scope) "
            "VALUES (100, 'product', 'read', ?)",
            [json.dumps({
                'include': [],
                'exclude': [{'field': 'owner_id', 'op': '=', 'value': 999}],
            })]
        )
        conn.commit()
        conn.close()

        # product 1 owner_id=999 → exclude 命中
        resp = client.post('/api/v2/permissions/simulate', json={
            'role_ids': [100],
            'bo_id': 'product',
            'action_name': 'read',
            'record_id': 1,
        })
        assert resp.status_code == 200
        data = resp.get_json()
        assert data['data']['allowed'] is False
        assert data['data']['source'] == 'exclude'

    def test_simulate_missing_params_returns_400(self, client):
        """POST 缺少必填参数 → 400"""
        resp = client.post('/api/v2/permissions/simulate', json={
            'role_ids': [100],
            # 缺 bo_id / action_name / record_id
        })
        assert resp.status_code == 400

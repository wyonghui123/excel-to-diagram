# -*- coding: utf-8 -*-
"""
[MODULE] 全量 BO Action + 审计日志分析器 (v3.18)
[DESCRIPTION]
1. 跑完 19 个 BO Action + 5 大对象 CRUD (user/role/user_group/product/version)
   + deepcreate + import/export + assign/unassign
2. 跑完后, 分析 audit_logs 表:
   - 完整性: 必填字段 (object_type/object_id/action/user_id/user_name/ip/created_at)
   - 合规性: action 类型, 编码 (UTF-8/乱码), 必填项
   - 可理解性: user_name 显示名 vs 原始 username, target_display 缺失
   - 可恢复性: 删除后能否用 old_data/new_data 恢复
3. 输出 JSON 报告
"""
import http.client
import json
import os
import sys
import time
import sqlite3
import traceback
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

# === Setup ===
PROJECT_ROOT = r'd:/filework/excel-to-diagram'
DB_PATH = os.path.join(PROJECT_ROOT, 'meta', 'architecture.db')
HOST = 'localhost'
PORT = 3010

# 让 'meta' 可被 import
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 测试 mark
TEST_RUN_TAG = f'audit_run_{int(time.time())}'


# === HTTP helper ===
class H:
    def __init__(self):
        self.cookie: Optional[str] = None
        self.user_id: Optional[int] = None
        self.user_name: Optional[str] = None
        self.trace_ids: List[str] = []
        self.created_object_ids: Dict[str, Any] = {}  # object_type -> [ids]
        self.deleted_data: Dict[str, List[Dict]] = {}  # object_type -> [old_data]

    def _req(self, method: str, path: str, body: Optional[Dict] = None,
             extra_headers: Optional[Dict] = None) -> Tuple[int, Any, Dict]:
        conn = http.client.HTTPConnection(HOST, PORT, timeout=30)
        body_bytes = json.dumps(body or {}, ensure_ascii=False).encode('utf-8')
        headers = {
            'Content-Type': 'application/json',
            'Content-Length': str(len(body_bytes)),
        }
        if self.cookie:
            headers['Cookie'] = self.cookie
        if extra_headers:
            headers.update(extra_headers)
        conn.request(method, path, body=body_bytes, headers=headers)
        r = conn.getresponse()
        raw = r.read().decode('utf-8', errors='replace')
        try:
            data = json.loads(raw) if raw else {}
        except Exception:
            data = {'_raw': raw}
        # 提取 trace_id
        tid = r.getheader('X-Trace-Id')
        if tid:
            self.trace_ids.append(tid)
        resp_headers = dict(r.getheaders())
        conn.close()
        return r.status, data, resp_headers

    def login(self, username: str = 'admin', password: str = 'admin123') -> bool:
        # 先解锁 admin
        try:
            c = sqlite3.connect(DB_PATH, timeout=5)
            status = c.execute("SELECT status FROM users WHERE username = 'admin'").fetchone()
            if status and status[0] != 'active':
                c.execute("UPDATE users SET status = 'active' WHERE username = 'admin'")
                c.commit()
            row = c.execute("SELECT id, display_name FROM users WHERE username = 'admin'").fetchone()
            if row:
                self.user_id, self.user_name = row
            c.close()
        except Exception as e:
            print(f"  [warn] unlock admin: {e}")

        status, data, headers = self._req(
            'POST', '/api/v2/action/user.authenticate',
            {'username': username, 'password': password}
        )
        if status == 200 and data.get('success'):
            set_cookie = headers.get('Set-Cookie', '')
            if set_cookie:
                self.cookie = set_cookie.split(';')[0]
            ud = data.get('data', {}).get('user', {}) or {}
            self.user_id = ud.get('user_id') or ud.get('id') or self.user_id
            return True
        return False

    def action(self, action_id: str, body: Optional[Dict] = None) -> Tuple[int, Dict]:
        status, data, _ = self._req('POST', f'/api/v2/action/{action_id}', body or {})
        return status, data

    def bo_create(self, object_type: str, fields: Dict) -> Tuple[int, Dict]:
        status, data, _ = self._req('POST', f'/api/v2/bo/{object_type}', fields)
        if status in (200, 201) and data.get('success'):
            obj_id = data.get('data', {}).get('id') or data.get('data', {}).get('data', {}).get('id')
            if obj_id is not None:
                self.created_object_ids.setdefault(object_type, []).append(obj_id)
        return status, data

    def bo_read(self, object_type: str, obj_id: Any) -> Tuple[int, Dict]:
        return self._req('GET', f'/api/v2/bo/{object_type}/{obj_id}')[:2]

    def bo_update(self, object_type: str, obj_id: Any, fields: Dict) -> Tuple[int, Dict]:
        return self._req('PUT', f'/api/v2/bo/{object_type}/{obj_id}', fields)[:2]

    def bo_delete(self, object_type: str, obj_id: Any) -> Tuple[int, Dict]:
        return self._req('DELETE', f'/api/v2/bo/{object_type}/{obj_id}')[:2]

    def bo_deep(self, object_type: str, payload: Dict) -> Tuple[int, Dict]:
        return self._req('POST', f'/api/v2/bo/{object_type}/deep', payload)[:2]

    def bo_query(self, object_type: str, params: Optional[Dict] = None) -> Tuple[int, Dict]:
        path = f'/api/v2/bo/{object_type}'
        if params:
            qs = '&'.join([f'{k}={urllib.parse.quote(str(v))}' for k, v in params.items()])
            path = f'{path}?{qs}'
        return self._req('GET', path)[:2]

    def bo_assign(self, object_type: str, obj_id: Any, assoc: str,
                  target_type: str, target_id: Any) -> Tuple[int, Dict]:
        path = f'/api/v2/bo/{object_type}/{obj_id}/$associations/{assoc}/assign'
        return self._req('POST', path, {'target_type': target_type, 'target_id': target_id})[:2]

    def bo_unassign(self, object_type: str, obj_id: Any, assoc: str,
                    target_type: str, target_id: Any) -> Tuple[int, Dict]:
        path = f'/api/v2/bo/{object_type}/{obj_id}/$associations/{assoc}/unassign'
        return self._req('POST', path, {'target_type': target_type, 'target_id': target_id})[:2]

    def bo_associate(self, object_type: str, obj_id: Any, assoc: str,
                     target_type: str, target_id: Any) -> Tuple[int, Dict]:
        path = f'/api/v2/bo/{object_type}/{obj_id}/associations/{assoc}'
        return self._req('POST', path, {'target_type': target_type, 'target_id': target_id})[:2]

    def bo_dissociate(self, object_type: str, obj_id: Any, assoc: str,
                      target_type: str, target_id: Any) -> Tuple[int, Dict]:
        path = f'/api/v2/bo/{object_type}/{obj_id}/associations/{assoc}'
        return self._req('DELETE', path, {'target_type': target_type, 'target_id': target_id})[:2]


# === Test runner ===
class TestRunner:
    def __init__(self):
        self.results: List[Dict] = []
        self.tag = TEST_RUN_TAG

    def run(self, name: str, fn):
        t0 = time.time()
        try:
            ok, msg = fn()
            dt = (time.time() - t0) * 1000
            entry = {'name': name, 'ok': ok, 'msg': str(msg)[:200], 'ms': round(dt, 1), 'tag': self.tag}
            self.results.append(entry)
            mark = '[OK]  ' if ok else '[FAIL]'
            print(f'  {mark} {name:<55} {dt:6.0f}ms  {entry["msg"][:80]}')
            return ok
        except Exception as e:
            dt = (time.time() - t0) * 1000
            entry = {'name': name, 'ok': False, 'msg': f'EXC: {e}', 'ms': round(dt, 1), 'tag': self.tag}
            self.results.append(entry)
            print(f'  [EXC] {name:<55} {dt:6.0f}ms  {str(e)[:80]}')
            traceback.print_exc()
            return False

    def summary(self) -> Dict:
        ok = sum(1 for r in self.results if r['ok'])
        fail = len(self.results) - ok
        return {'total': len(self.results), 'ok': ok, 'fail': fail, 'tag': self.tag}


# === Tests ===
def test_user_crud(h: H, r: TestRunner) -> Dict:
    """1. user CRUD"""
    ts = int(time.time())
    username = f'audit_{ts}'

    def t_create():
        status, data = h.bo_create('user', {
            'username': username,
            'display_name': f'审计测试 {ts}',
            'email': f'audit_{ts}@test.local',
            'password_hash': 'placeholder',
            'status': 'active',
        })
        if status in (200, 201) and data.get('success'):
            return True, f'创建 user id={data["data"].get("id")}'
        return False, f'status={status} data={data}'

    def t_read():
        # list query
        status, data = h.bo_query('user', {'page': '1', 'page_size': '5'})
        return status in (200, 201), f'list status={status}'

    def t_update():
        # 用 batch_save 测 update
        s, d = h.action('batch_save', {
            'object_type': 'user',
            'drafts': [{'row_id': '__new', 'is_new': True, 'fields': {
                'username': f'{username}_2',
                'display_name': 'updated',
                'email': 'x@x.com',
                'password_hash': 'p',
            }}]
        })
        if s == 200 and d.get('success'):
            created = d.get('data', {}).get('created', [])
            if created:
                # update 刚创建的
                uid = created[0]
                s2, d2 = h.action('batch_save', {
                    'object_type': 'user',
                    'drafts': [{'row_id': str(uid), 'is_new': False, 'fields': {
                        'display_name': 'updated twice'
                    }}]
                })
                # 清理
                h.action('batch_delete', {'object_type': 'user', 'row_ids': [uid]})
                return s2 == 200, f'update status={s2}'
        return False, f'create-then-update failed: {d}'

    def t_delete():
        # 用 batch_delete 清理
        s, d = h.action('batch_delete', {'object_type': 'user', 'row_ids': []})
        return s == 200, f'batch_delete status={s}'

    return {
        'create': r.run('user.create', t_create),
        'read': r.run('user.read_list', t_read),
        'update': r.run('user.update', t_update),
        'delete': r.run('user.delete_empty', t_delete),
    }


def test_role_crud(h: H, r: TestRunner) -> Dict:
    """2. role CRUD"""
    ts = int(time.time())
    code = f'audit_role_{ts}'
    role_id_holder = {'id': None}

    def t_create():
        s, d = h.bo_create('role', {
            'code': code,
            'name': f'审计角色 {ts}',
            'description': 'audit test role',
            'status': 'active',
        })
        if s in (200, 201) and d.get('success'):
            role_id_holder['id'] = d.get('data', {}).get('id')
            return True, f'id={role_id_holder["id"]}'
        return False, f'status={s} body={d}'

    def t_update():
        rid = role_id_holder['id']
        if not rid:
            return False, 'no role_id from create'
        s2, d2 = h.bo_update('role', rid, {'description': 'updated'})
        return s2 in (200, 201), f'update id={rid} status={s2}'

    def t_delete():
        rid = role_id_holder['id']
        if not rid:
            return False, 'no role_id from create'
        # 先查一下记录 (记 old_data 给恢复分析)
        s, d = h.bo_read('role', rid)
        if s == 200 and d.get('success'):
            h.deleted_data.setdefault('role', []).append(d.get('data'))
        s2, d2 = h.bo_delete('role', rid)
        return s2 in (200, 201), f'delete id={rid} status={s2}'

    return {
        'create': r.run('role.create', t_create),
        'update': r.run('role.update', t_update),
        'delete': r.run('role.delete', t_delete),
    }


def test_user_group_crud(h: H, r: TestRunner) -> Dict:
    """3. user_group CRUD"""
    ts = int(time.time())
    code = f'audit_ug_{ts}'
    ug_id_holder = {'id': None}

    def t_create():
        s, d = h.bo_create('user_group', {
            'code': code,
            'name': f'审计用户组 {ts}',
            'description': 'audit',
        })
        if s in (200, 201) and d.get('success'):
            ug_id_holder['id'] = d.get('data', {}).get('id')
            return True, f'id={ug_id_holder["id"]}'
        return False, f'status={s} body={d}'

    def t_update():
        gid = ug_id_holder['id']
        if not gid:
            return False, 'no ug_id from create'
        s2, d2 = h.bo_update('user_group', gid, {'description': 'updated'})
        return s2 in (200, 201), f'update id={gid} status={s2}'

    def t_delete():
        gid = ug_id_holder['id']
        if not gid:
            return False, 'no ug_id from create'
        s, d = h.bo_read('user_group', gid)
        if s == 200 and d.get('success'):
            h.deleted_data.setdefault('user_group', []).append(d.get('data'))
        s2, d2 = h.bo_delete('user_group', gid)
        return s2 in (200, 201), f'delete id={gid} status={s2}'

    return {
        'create': r.run('user_group.create', t_create),
        'update': r.run('user_group.update', t_update),
        'delete': r.run('user_group.delete', t_delete),
    }


def test_product_crud(h: H, r: TestRunner) -> Dict:
    """4. product CRUD"""
    ts = int(time.time())
    code = f'AUDIT_PROD_{ts}'
    p_id_holder = {'id': None}

    def t_create():
        s, d = h.bo_create('product', {
            'code': code,
            'name': f'审计产品 {ts}',
            'description': 'audit test',
            'is_active': 1,
        })
        if s in (200, 201) and d.get('success'):
            p_id_holder['id'] = d.get('data', {}).get('id')
            return True, f'id={p_id_holder["id"]}'
        return False, f'status={s} body={d}'

    def t_update():
        pid = p_id_holder['id']
        if not pid:
            return False, 'no product_id from create'
        s2, d2 = h.bo_update('product', pid, {'description': 'updated'})
        return s2 in (200, 201), f'update id={pid} status={s2}'

    def t_delete():
        pid = p_id_holder['id']
        if not pid:
            return False, 'no product_id from create'
        s, d = h.bo_read('product', pid)
        if s == 200 and d.get('success'):
            h.deleted_data.setdefault('product', []).append(d.get('data'))
        s2, d2 = h.bo_delete('product', pid)
        return s2 in (200, 201), f'delete id={pid} status={s2}'

    return {
        'create': r.run('product.create', t_create),
        'update': r.run('product.update', t_update),
        'delete': r.run('product.delete', t_delete),
    }


def test_version_crud(h: H, r: TestRunner) -> Dict:
    """5. version CRUD (需要 product_id)"""
    ts = int(time.time())
    code = f'AUDIT_VER_{ts}'
    v_id_holder = {'id': None}
    p_id_holder = {'id': None}

    def t_create_parent_product():
        # version 必填 product_id, 先创建 product
        s, d = h.bo_create('product', {
            'code': f'AUDIT_VP_{ts}',
            'name': f'审计版本父产品 {ts}',
            'is_active': 1,
        })
        if s in (200, 201) and d.get('success'):
            p_id_holder['id'] = d.get('data', {}).get('id')
            return True, f'parent product id={p_id_holder["id"]}'
        return False, f'status={s} body={d}'

    def t_create():
        if not p_id_holder['id']:
            return False, 'no parent product'
        s, d = h.bo_create('version', {
            'code': code,
            'name': f'审计版本 {ts}',
            'product_id': p_id_holder['id'],
            'is_current': 0,
        })
        if s in (200, 201) and d.get('success'):
            v_id_holder['id'] = d.get('data', {}).get('id')
            return True, f'id={v_id_holder["id"]}'
        return False, f'status={s} body={d}'

    def t_update():
        vid = v_id_holder['id']
        if not vid:
            return False, 'no version_id from create'
        s2, d2 = h.bo_update('version', vid, {'name': f'审计版本updated {ts}'})
        return s2 in (200, 201), f'update id={vid} status={s2}'

    def t_delete():
        """删除 version 但保留 parent product, 这样恢复测试可以成功"""
        vid = v_id_holder['id']
        if not vid:
            return False, 'no version_id from create'
        s, d = h.bo_read('version', vid)
        if s == 200 and d.get('success'):
            h.deleted_data.setdefault('version', []).append(d.get('data'))
        s2, d2 = h.bo_delete('version', vid)
        return s2 in (200, 201), f'delete id={vid} status={s2}'

    return {
        'create_parent': r.run('version.create_parent_product', t_create_parent_product),
        'create': r.run('version.create', t_create),
        'update': r.run('version.update', t_update),
        'delete': r.run('version.delete', t_delete),
    }


def test_assign_unassign(h: H, r: TestRunner) -> Dict:
    """6. assign / unassign 测试 (user -> user_group 关联)"""
    ts = int(time.time())
    holders = {'user_id': None, 'group_id': None, 'user_id2': None, 'group_id2': None}

    def t_assign():
        # 创建 user 和 group
        s, d = h.bo_create('user', {
            'username': f'au_{ts}',
            'display_name': 'assign test',
            'email': f'au_{ts}@x.com',
            'password_hash': 'p',
        })
        if s in (200, 201) and d.get('success'):
            holders['user_id'] = d.get('data', {}).get('id')
        s, d = h.bo_create('user_group', {
            'code': f'aug_{ts}',
            'name': f'assign ug {ts}',
        })
        if s in (200, 201) and d.get('success'):
            holders['group_id'] = d.get('data', {}).get('id')

        if not holders['user_id'] or not holders['group_id']:
            return False, f'create failed: user={holders["user_id"]}, group={holders["group_id"]}'

        # assign endpoint: 返回 204 + 空 body, success=True 当 200/201/204
        s, d = h.bo_assign('user', holders['user_id'], 'groups', 'user_group', holders['group_id'])
        if s in (200, 201, 204):
            s2, d2 = h.bo_unassign('user', holders['user_id'], 'groups', 'user_group', holders['group_id'])
            return s2 in (200, 201, 204), f'assign+unassign done (user_id={holders["user_id"]}, group_id={holders["group_id"]}, s={s}/s2={s2})'
        return False, f'assign failed: status={s} body={d}'

    def t_associate_dissociate():
        ts2 = int(time.time()) + 1
        s, d = h.bo_create('user', {
            'username': f'au2_{ts2}',
            'display_name': 'assoc test',
            'email': f'au2_{ts2}@x.com',
            'password_hash': 'p',
        })
        if s in (200, 201) and d.get('success'):
            holders['user_id2'] = d.get('data', {}).get('id')
        s, d = h.bo_create('user_group', {
            'code': f'aug2_{ts2}',
            'name': f'assoc ug {ts2}',
        })
        if s in (200, 201) and d.get('success'):
            holders['group_id2'] = d.get('data', {}).get('id')

        if not holders['user_id2'] or not holders['group_id2']:
            return False, f'create failed: user={holders["user_id2"]}, group={holders["group_id2"]}'

        s, d = h.bo_associate('user', holders['user_id2'], 'groups', 'user_group', holders['group_id2'])
        # associate 可能返回 "关联已存在" - 这也算 OK
        if s in (200, 201):
            s2, d2 = h.bo_dissociate('user', holders['user_id2'], 'groups', 'user_group', holders['group_id2'])
            return s2 in (200, 201, 204), f'associate+dissociate done (s={s}/s2={s2})'
        return False, f'assoc failed: status={s} body={d}'

    return {
        'assign_unassign': r.run('assign_unassign.v2', t_assign),
        'associate_dissociate': r.run('associate_dissociate.v1', t_associate_dissociate),
    }


def test_deepcreate(h: H, r: TestRunner) -> Dict:
    """7. deepcreate 嵌套创建"""
    ts = int(time.time())

    def t_deep_product():
        # deep_insert_engine 期望格式: {parent: {...}, children: {child_type: [items]}}
        s, d = h.bo_deep('product', {
            'parent': {
                'code': f'DEEP_{ts}',
                'name': f'深度创建产品 {ts}',
                'is_active': 1,
            },
            'children': {
                'version': [{
                    'code': f'DEEP_V_{ts}',
                    'name': f'深度版本 {ts}',
                }],
            },
        })
        return s in (200, 201), f'deep status={s} body={str(d)[:200]}'

    return {
        'product_with_versions': r.run('deep.product+versions', t_deep_product),
    }


def test_import_export(h: H, r: TestRunner) -> Dict:
    """8. import / export"""
    ts = int(time.time())

    def t_export():
        # export product list (注意: 在 /api/v1/ 下, 不是 /api/v2/)
        s, d = h._req('POST', '/api/v1/export', {
            'object_type': 'product',
            'scope': 'single',
            'options': {
                'include_hierarchy_path': True,
                'include_hierarchy_ids': True,
                'include_metadata_sheet': True,
            },
        })[:2]
        return s in (200, 201), f'export status={s} body={str(d)[:150]}'

    def t_export_template():
        # template 用 scope='template', 但 API 校验先于 scope 判断, 仍要 object_type
        # [ISSUE 2026-06-12] export_import_api.py:163 强制 object_type 必填, 即便 scope='template'
        # 建议修复: 把 163 行的 if 移到 scope 判断之后, 或者从 selected_types[0] 推断
        s, d = h._req('POST', '/api/v1/export', {
            'object_type': 'product',  # workaround: 提供占位 object_type
            'scope': 'template',
            'selected_types': ['product'],
            'options': {'include_metadata_sheet': True},
        })[:2]
        return s in (200, 201), f'export template status={s} body={str(d)[:150]}'

    def t_import_config():
        # get import config (GET endpoint, 不需要 file upload)
        s, d = h._req('GET', '/api/v1/import-export/config/product')[:2]
        return s in (200, 201), f'import config status={s} body={str(d)[:150]}'

    return {
        'export': r.run('export.product', t_export),
        'export_template': r.run('export.template', t_export_template),
        'import_config': r.run('import.config', t_import_config),
    }


def test_other_actions(h: H, r: TestRunner) -> Dict:
    """9. 其他辅助 action (user.get_current, enum_type CRUD, subscription, function.*)"""
    ts = int(time.time())
    enum_id = f'audit_enum_{ts}'

    def t_user_get_current():
        s, d = h.action('user.get_current', {})
        return s == 200 and d.get('success'), f'current user: {d.get("data", {}).get("username", "?")}'

    def t_enum_create():
        s, d = h.action('enum_type.create', {'id': enum_id, 'name': f'Audit Enum {ts}'})
        return s == 200 and d.get('success'), f'enum create: {d}'

    def t_enum_update():
        s, d = h.action('enum_type.update', {'id': enum_id, 'name': f'Audit Enum Updated {ts}'})
        return s == 200 and d.get('success'), f'enum update: {d}'

    def t_enum_delete():
        s, d = h.action('enum_type.delete', {'id': enum_id})
        return s == 200 and d.get('success'), f'enum delete: {d}'

    def t_func_vh():
        s, d = h.action('function.value_help.resolve', {
            'source_type': 'enum', 'source_id': 'color', 'value': 'red'
        })
        return s == 200, f'value_help: {d}'

    def t_func_agg():
        s, d = h.action('function.aggregate.query', {'aggregate_id': 'user_stats'})
        return s == 200, f'aggregate: {d}'

    def t_func_sub_list():
        s, d = h.action('function.subscription.list', {})
        return s == 200, f'sub list: {d}'

    def t_audit_retry():
        s, d = h.action('audit.retry', {'record_id': 999999999})
        return s == 200, f'audit.retry (not found): {d}'

    return {
        'user_get_current': r.run('user.get_current', t_user_get_current),
        'enum_create': r.run('enum_type.create', t_enum_create),
        'enum_update': r.run('enum_type.update', t_enum_update),
        'enum_delete': r.run('enum_type.delete', t_enum_delete),
        'value_help': r.run('function.value_help.resolve', t_func_vh),
        'aggregate': r.run('function.aggregate.query', t_func_agg),
        'sub_list': r.run('function.subscription.list', t_func_sub_list),
        'audit_retry': r.run('audit.retry', t_audit_retry),
    }


# === Audit log analyzer ===
def analyze_audit_logs(r: TestRunner) -> Dict:
    """
    分析最近 200 条 + 本次 tag 标记的审计日志
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cur = conn.cursor()

    # 1. 本次跑出来的日志
    cur.execute("""
        SELECT * FROM audit_logs
        WHERE created_at >= datetime('now', '-10 minutes')
        ORDER BY id DESC
    """)
    cols = [d[0] for d in cur.description]
    recent_rows = [dict(zip(cols, row)) for row in cur.fetchall()]
    conn.close()

    print(f"\n=== 最近 10 分钟的审计日志: {len(recent_rows)} 条 ===")

    # 2. 完整性
    MANDATORY = ['object_type', 'object_id', 'action', 'user_id', 'user_name',
                 'ip_address', 'created_at', 'trace_id']
    completeness_issues = []
    for r in recent_rows:
        for f in MANDATORY:
            if f == 'ip_address':
                continue  # ip 可以为空
            v = r.get(f)
            if v is None or v == '':
                completeness_issues.append({
                    'id': r['id'],
                    'action': r['action'],
                    'object_type': r['object_type'],
                    'missing': f,
                })

    # 3. 合规性
    VALID_ACTIONS = {'CREATE', 'UPDATE', 'DELETE', 'ASSOCIATE', 'DISSOCIATE',
                     'BATCH', 'IMPORT', 'EXPORT', 'AUDIT_WRITE_FAILED',
                     'DELETE_BLOCKED', 'LOGIN', 'LOGOUT', 'LOGIN_FAILED',
                     'READ', 'QUERY', 'STATE_TRANSITION', 'EXPORT_DOWNLOAD',
                     'IMPORT_PREVIEW', 'ACCESS_DENIED', 'RECOVER'}
    invalid_actions = []
    for r in recent_rows:
        a = r.get('action', '')
        if a and a not in VALID_ACTIONS:
            invalid_actions.append({
                'id': r['id'], 'action': a, 'object_type': r['object_type'],
            })

    # 4. 编码合规 (乱码检测 - 包含 鐢ㄦ埛 这类典型 UTF-8->GBK 误读)
    MOJIBAKE_PATTERNS = ['鐢ㄦ埛', '绯荤粺', '閰嶇疆', '閫氱敤', '缁忕悊', '鏃ユ湡']
    encoding_issues = []
    for r in recent_rows:
        for f in ('old_value', 'new_value', 'object_type', 'field_name', 'user_name'):
            v = str(r.get(f, '') or '')
            for pat in MOJIBAKE_PATTERNS:
                if pat in v:
                    encoding_issues.append({
                        'id': r['id'], 'field': f, 'pattern': pat,
                        'sample': v[:60],
                    })
                    break

    # 5. 可理解性
    # 5.1 user_name 是否包含 display_name (e.g. "张三 (zhangsan)")
    user_name_format = {'with_display': 0, 'username_only': 0, 'empty': 0, 'other': 0}
    for r in recent_rows:
        un = r.get('user_name', '') or ''
        if not un:
            user_name_format['empty'] += 1
        elif '(' in un and ')' in un:
            user_name_format['with_display'] += 1
        elif un in ('admin', 'system', 'anonymous'):
            user_name_format['username_only'] += 1
        else:
            user_name_format['other'] += 1

    # 5.2 target_display 缺失 (ASSOCIATE/DISSOCIATE)
    target_display_missing = []
    for r in recent_rows:
        if r.get('action') in ('ASSOCIATE', 'DISSOCIATE'):
            payload = r.get('new_value') or r.get('old_value') or ''
            if payload:
                try:
                    p = json.loads(payload)
                    if not p.get('target_display'):
                        target_display_missing.append({
                            'id': r['id'],
                            'action': r['action'],
                            'target_type': p.get('target_type'),
                            'target_id': p.get('target_id'),
                        })
                except Exception:
                    pass

    # 6. user_agent 缺失率
    no_ua = sum(1 for r in recent_rows if not r.get('user_agent'))
    ua_missing_rate = no_ua / len(recent_rows) if recent_rows else 0

    # 7. action_kind / outcome 字段填充率 (v2 字段)
    v2_fields = {
        'action_kind': sum(1 for r in recent_rows if r.get('action_kind')),
        'outcome': sum(1 for r in recent_rows if r.get('outcome')),
        'parent_action_id': sum(1 for r in recent_rows if r.get('parent_action_id')),
        'log_category': sum(1 for r in recent_rows if r.get('log_category')),
        'log_level': sum(1 for r in recent_rows if r.get('log_level')),
    }

    # 8. 异步写入器健康状态
    try:
        from meta.services.async_audit_writer import async_audit_writer
        stats = async_audit_writer.get_stats()
    except Exception as e:
        stats = {'error': str(e)}

    # 9. 按 action 统计
    action_dist = {}
    for r in recent_rows:
        a = r.get('action', 'UNKNOWN')
        action_dist[a] = action_dist.get(a, 0) + 1

    return {
        'total_recent_logs': len(recent_rows),
        'completeness': {
            'mandatory_fields': MANDATORY,
            'missing_count': len(completeness_issues),
            'issues_sample': completeness_issues[:10],
        },
        'compliance': {
            'invalid_action_count': len(invalid_actions),
            'invalid_actions_sample': invalid_actions[:10],
        },
        'encoding': {
            'mojibake_count': len(encoding_issues),
            'mojibake_sample': encoding_issues[:10],
            'patterns_checked': MOJIBAKE_PATTERNS,
        },
        'understandability': {
            'user_name_format': user_name_format,
            'target_display_missing_count': len(target_display_missing),
            'target_display_missing_sample': target_display_missing[:5],
            'user_agent_missing_rate': round(ua_missing_rate, 3),
        },
        'v2_fields_filled': v2_fields,
        'action_distribution': action_dist,
        'async_writer_stats': stats,
    }


def analyze_deleted_objects_recoverability(r: TestRunner, h: H) -> Dict:
    """
    分析每个被删除的对象:
    - 数据库里是否还有迹可循 (delete 审计日志)
    - 审计日志是否含 old_data (含完整字段)
    - 能否用审计日志恢复
    """
    conn = sqlite3.connect(DB_PATH, timeout=10)
    cur = conn.cursor()

    results = []
    for obj_type, items in h.deleted_data.items():
        for item in items:
            obj_id = item.get('id')
            if obj_id is None:
                continue
            # 1. 查最新 DELETE 日志
            cur.execute("""
                SELECT * FROM audit_logs
                WHERE object_type = ? AND object_id = ? AND action = 'DELETE'
                ORDER BY id DESC LIMIT 1
            """, (obj_type, str(obj_id)))
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
            log = dict(zip(cols, row)) if row else None

            # 2. 解析 extra_data 里的 deleted_data
            deleted_data = None
            has_full_old = False
            if log:
                extra = log.get('extra_data')
                if extra:
                    try:
                        ed = json.loads(extra)
                        deleted_data = ed.get('deleted_data')
                        if deleted_data and len(deleted_data) >= 3:
                            has_full_old = True
                    except Exception:
                        pass

            # 3. 尝试用日志恢复 (POST 回去)
            recovered_ok = False
            recover_msg = 'N/A'
            if has_full_old and deleted_data:
                # 去掉主键和时间戳
                payload = {k: v for k, v in deleted_data.items()
                           if k not in ('id', 'created_at', 'updated_at')}
                # 密码 hash 必填, 补一个 placeholder
                if obj_type == 'user' and 'password_hash' not in payload:
                    payload['password_hash'] = 'recovered_placeholder'
                # 找必填字段 (用 schema 推断太复杂, 先尝试直接 post)
                s, d = h._req('POST', f'/api/v2/bo/{obj_type}', payload)[:2]
                recovered_ok = s in (200, 201) and d.get('success')
                recover_msg = f'status={s} body={str(d)[:120]}'

            results.append({
                'object_type': obj_type,
                'object_id': obj_id,
                'has_delete_log': log is not None,
                'has_full_old_data': has_full_old,
                'old_data_keys': list(deleted_data.keys()) if deleted_data else [],
                'recover_attempt': recover_msg,
                'recover_ok': recovered_ok,
            })
    conn.close()
    return {'recoverability_tests': results}


# === Main ===
def main():
    print("=" * 80)
    print(f"  BO Action 全量 + 审计日志分析  (tag={TEST_RUN_TAG})")
    print("=" * 80)

    h = H()
    if not h.login():
        print("[FAIL] admin 登录失败, 退出")
        return 1
    print(f"  [OK] 登录成功, user_id={h.user_id}")

    r = TestRunner()
    print(f"\n[1/3] user CRUD ...")
    user_res = test_user_crud(h, r)
    print(f"\n[2/3] role CRUD ...")
    role_res = test_role_crud(h, r)
    print(f"\n[3/3] user_group CRUD ...")
    ug_res = test_user_group_crud(h, r)
    print(f"\n[4] product CRUD ...")
    prod_res = test_product_crud(h, r)
    print(f"\n[5] version CRUD ...")
    ver_res = test_version_crud(h, r)
    print(f"\n[6] assign/unassign ...")
    assoc_res = test_assign_unassign(h, r)
    print(f"\n[7] deepcreate ...")
    deep_res = test_deepcreate(h, r)
    print(f"\n[8] import/export ...")
    imp_res = test_import_export(h, r)
    print(f"\n[9] 其他 action ...")
    other_res = test_other_actions(h, r)

    print(f"\n[分析] 等异步审计写入 flush ...")
    time.sleep(2)
    try:
        from meta.services.async_audit_writer import async_audit_writer
        async_audit_writer.flush(timeout=3)
    except Exception:
        pass

    print(f"\n[分析] 分析审计日志 ...")
    try:
        audit = analyze_audit_logs(r)
    except Exception as e:
        import traceback
        traceback.print_exc()
        audit = {'error': str(e)}
    print(f"  - 本次测试相关日志: {audit.get('total_recent_logs', '?')} 条")
    print(f"  - 完整性问题: {audit.get('completeness', {}).get('missing_count', '?')}")
    print(f"  - 合规 (非法 action): {audit.get('compliance', {}).get('invalid_action_count', '?')}")
    print(f"  - 编码问题 (乱码): {audit.get('encoding', {}).get('mojibake_count', '?')}")
    print(f"  - target_display 缺失: {audit.get('understandability', {}).get('target_display_missing_count', '?')}")
    print(f"  - user_agent 缺失率: {audit.get('understandability', {}).get('user_agent_missing_rate', '?')}")

    print(f"\n[分析] 评估对象删除可恢复性 ...")
    try:
        recover = analyze_deleted_objects_recoverability(r, h)
    except Exception as e:
        import traceback
        traceback.print_exc()
        recover = {'error': str(e)}
    n_recover = len(recover.get('recoverability_tests', []))
    print(f"  - 共测试 {n_recover} 个删除对象")
    for x in recover.get('recoverability_tests', []):
        print(f"    {x['object_type']}#{x['object_id']}: "
              f"log={x['has_delete_log']}, old_keys={len(x['old_data_keys'])}, "
              f"recover={'OK' if x['recover_ok'] else 'FAIL'}")

    # 报告
    summary = r.summary()
    report = {
        'tag': TEST_RUN_TAG,
        'summary': summary,
        'object_results': {
            'user': user_res,
            'role': role_res,
            'user_group': ug_res,
            'product': prod_res,
            'version': ver_res,
            'assign_unassign': assoc_res,
            'deepcreate': deep_res,
            'import_export': imp_res,
            'other_actions': other_res,
        },
        'audit_analysis': audit,
        'recoverability': recover,
    }
    out = os.path.join(PROJECT_ROOT, 'test_temp', f'audit_report_{TEST_RUN_TAG}.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f"\n[报告] 已写入: {out}")
    print(f"[汇总] {summary['ok']}/{summary['total']} 通过 ({summary['fail']} 失败)")

    return 0 if summary['fail'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())

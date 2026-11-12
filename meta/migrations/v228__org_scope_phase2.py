# -*- coding: utf-8 -*-
"""v228 - 业务对象组织边界（Spec 24 Phase 2）

依据: docs/spec_权限体系升级/24_org_scope_business_object_phase2.md §7.1

范围:
  1. users.primary_org_id（Phase 1 未交付时补齐；仅作默认业务上下文，不参与授权判定）。
  2. idx_users_primary_org。
  3. control_parameter_defs 种子 org_scope_enforce = off（三态：off | compat | enforce）。

幂等:
  列/索引/参数先查后用；不改数据、不删列。
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime

MIGRATION_NAME = 'v228__org_scope_phase2'

USERS_TABLE = 'users'
PARAM_TABLE = 'control_parameter_defs'

ORG_SCOPE_PARAM = {
    'code': 'org_scope_enforce',
    'name': '业务对象组织边界开关',
    'domain': 'platform',
    'value_type': 'string',
    'target_bo': '',
    'default_value': 'off',
    'description': '业务对象组织边界三态开关：off（默认）/ compat（只记日志）/ enforce（读过滤+写校验）',
}


def _table_exists(conn, name):
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", [name]
    ).fetchone()
    return bool(row)


def _columns(conn, table):
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute('PRAGMA table_info(%s)' % table)}


def _do_user_column(conn):
    if not _table_exists(conn, USERS_TABLE):
        print('  - [SKIP] 缺表 %s' % USERS_TABLE)
        return
    if 'primary_org_id' in _columns(conn, USERS_TABLE):
        print('  - [SKIP] 列 %s.primary_org_id 已存在' % USERS_TABLE)
        return
    conn.execute('ALTER TABLE %s ADD COLUMN primary_org_id INTEGER NULL' % USERS_TABLE)
    print('  - [ALTER] 列 %s.primary_org_id' % USERS_TABLE)


def _do_user_index(conn):
    if not _table_exists(conn, USERS_TABLE):
        return
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_users_primary_org ON %s(primary_org_id)'
        % USERS_TABLE
    )
    print('  - [OK] 索引 idx_users_primary_org')


def _do_param(conn):
    if not _table_exists(conn, PARAM_TABLE):
        print('  - [SKIP] 缺表 %s' % PARAM_TABLE)
        return
    row = conn.execute(
        'SELECT id FROM %s WHERE code=?' % PARAM_TABLE, [ORG_SCOPE_PARAM['code']]
    ).fetchone()
    if row:
        print('  - [SKIP] 参数 %s 已存在 (id=%s)'
              % (ORG_SCOPE_PARAM['code'], row[0]))
        return
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn.execute(
        'INSERT INTO %s (code, name, domain, value_type, target_bo, '
        'default_value, description, status, created_at) '
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'active', ?)" % PARAM_TABLE,
        [ORG_SCOPE_PARAM['code'], ORG_SCOPE_PARAM['name'],
         ORG_SCOPE_PARAM['domain'], ORG_SCOPE_PARAM['value_type'],
         ORG_SCOPE_PARAM['target_bo'], ORG_SCOPE_PARAM['default_value'],
         ORG_SCOPE_PARAM['description'], now],
    )
    print('  - [NEW] 参数 %s = %s'
          % (ORG_SCOPE_PARAM['code'], ORG_SCOPE_PARAM['default_value']))


def migrate(db_path, skip_backup=False):
    print('[v228] 业务对象组织边界（Spec 24 Phase 2）')
    if hasattr(db_path, 'exists') and callable(getattr(db_path, 'exists')):
        exists = db_path.exists()
    else:
        exists = os.path.exists(str(db_path))
    if not exists:
        print('  - [SKIP] 库不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        _do_user_column(conn)
        _do_user_index(conn)
        _do_param(conn)
        conn.commit()
        print('[v228] 迁移提交完成')
        return True
    except Exception:
        conn.rollback()
        print('[v228] 失败，已回滚')
        raise
    finally:
        conn.close()


def verify(db_path):
    if not os.path.exists(str(db_path)):
        return {'ok': False, 'error': 'db not found'}
    conn = sqlite3.connect(str(db_path))
    try:
        checks = {}
        checks['users_primary_org'] = (
            True if not _table_exists(conn, USERS_TABLE)
            else 'primary_org_id' in _columns(conn, USERS_TABLE)
        )
        checks['param'] = (
            True if not _table_exists(conn, PARAM_TABLE)
            else bool(conn.execute(
                'SELECT 1 FROM %s WHERE code=? AND default_value=?'
                % PARAM_TABLE, [ORG_SCOPE_PARAM['code'], 'off']).fetchone())
        )
        ok = all(checks.values())
        print('[v228 verify] %s' % ('PASS' if ok else 'FAIL'))
        return bool(ok)
    finally:
        conn.close()


def rollback(db_path):
    """降级：删除开关种子；primary_org_id 保留（置空，SQLite 降级安全）"""
    if not os.path.exists(str(db_path)):
        print('[v228 rollback] DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if _table_exists(conn, PARAM_TABLE):
            conn.execute('DELETE FROM %s WHERE code=?' % PARAM_TABLE,
                         [ORG_SCOPE_PARAM['code']])
        if _table_exists(conn, USERS_TABLE) and 'primary_org_id' in _columns(conn, USERS_TABLE):
            conn.execute('UPDATE %s SET primary_org_id = NULL' % USERS_TABLE)
        conn.commit()
        print('[v228 rollback] 完成（primary_org_id 保留为空）')
        return True
    except Exception as exc:  # noqa: BLE001 - 降级失败需返回 False
        conn.rollback()
        print('[v228 rollback] 失败: %s' % exc)
        return False
    finally:
        conn.close()


downgrade = rollback

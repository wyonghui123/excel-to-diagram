# -*- coding: utf-8 -*-
"""[v178 2026-11-01] 通用审批规则模型（策略 / 条件 / 步骤）

依据:
  docs/specs/spec-purchase-order-object-model-2026-11-01.md §6.2 / §6.2.3
    Q4 / L-PO-2

设计:
  · 三张平台级表，完全按对象生效，不塞进 control_parameter_values：
      approval_policies          策略头（scope_bo 决定适用对象）
      approval_policy_conditions 条件因子（field_id 引用该对象字段 id）
      approval_policy_steps      审批链（步骤 + 金额分段 + 会签口径）
  · 条件求值口径（R1-R5）由 DocumentApprovalResolver 实现，本迁移只建结构。
  · 无命中策略 = 免审批；PO 默认不播种策略（保持既有「提交即可确认」行为）。
  · control_parameter_defs 新增组织级开关 approval_enabled（默认 true，
    用于紧急旁路）；旧 demand_approval_required / demand_approval_policy
    在 description 标 [DEPRECATED]（M3 期间继续生效，行为不变）。

幂等:
  表 / 列 / 索引 / 参数定义先查后用；重复执行打印 [SKIP]。

回滚:
  删索引 + 删表；approval_enabled 参数定义保留（可能已被组织取值引用）；
  已标记 DEPRECATED 的旧参数不动。
"""
import sqlite3
import sys
from pathlib import Path

POLICY_TABLE = 'approval_policies'
CONDITION_TABLE = 'approval_policy_conditions'
STEP_TABLE = 'approval_policy_steps'

PARAM_ENABLED = 'approval_enabled'
LEGACY_PARAMS = ('demand_approval_required', 'demand_approval_policy')
DEPRECATED_MARK = '[DEPRECATED 2026-11-01 -> approval_policies]'

TABLES = (
    (POLICY_TABLE, """
CREATE TABLE IF NOT EXISTS approval_policies (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    scope_bo VARCHAR(200) NOT NULL,
    trigger_action VARCHAR(200) NOT NULL DEFAULT 'submit',
    priority INTEGER NOT NULL DEFAULT 100,
    effective_from DATETIME,
    effective_to DATETIME,
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME
)
"""),
    (CONDITION_TABLE, """
CREATE TABLE IF NOT EXISTS approval_policy_conditions (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id INTEGER NOT NULL,
    group_no INTEGER NOT NULL DEFAULT 1,
    logic VARCHAR(200) NOT NULL DEFAULT 'and',
    field_id VARCHAR(200) NOT NULL,
    operator VARCHAR(200) NOT NULL DEFAULT '=',
    value_text VARCHAR(200),
    value_number REAL,
    value_json TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (policy_id) REFERENCES approval_policies(id)
)
"""),
    (STEP_TABLE, """
CREATE TABLE IF NOT EXISTS approval_policy_steps (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    policy_id INTEGER NOT NULL,
    step_no INTEGER NOT NULL DEFAULT 1,
    approver_type VARCHAR(200) NOT NULL DEFAULT 'role',
    approver_ref VARCHAR(200),
    min_amount REAL,
    max_amount REAL,
    approve_mode VARCHAR(200) NOT NULL DEFAULT 'any',
    sla_hours INTEGER,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (policy_id) REFERENCES approval_policies(id)
)
"""),
)

INDEXES = (
    ('uidx_approval_policy_code', POLICY_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uidx_approval_policy_code '
     'ON approval_policies(code)'),
    ('idx_approval_policy_scope', POLICY_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_approval_policy_scope '
     'ON approval_policies(scope_bo, trigger_action, status)'),
    ('idx_approval_policy_effective', POLICY_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_approval_policy_effective '
     'ON approval_policies(effective_from, effective_to)'),
    ('idx_approval_condition_policy', CONDITION_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_approval_condition_policy '
     'ON approval_policy_conditions(policy_id, group_no)'),
    ('uidx_approval_policy_step', STEP_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uidx_approval_policy_step '
     'ON approval_policy_steps(policy_id, step_no)'),
    ('idx_approval_step_approver', STEP_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_approval_step_approver '
     'ON approval_policy_steps(approver_type, approver_ref)'),
)

PARAM_DEF = (
    PARAM_ENABLED, '采购订单审批总开关', 'bool', 'true',
    '组织级紧急旁路：false 时该组织下提交的采购订单不解析审批策略（默认 true）',
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone() is not None


def _do_tables(conn: sqlite3.Connection) -> None:
    for name, ddl in TABLES:
        if _table_exists(conn, name):
            print(f'  - [SKIP] 表 {name} 已存在')
        else:
            conn.execute(ddl)
            print(f'  - [CREATE] 表 {name}')


def _do_indexes(conn: sqlite3.Connection) -> None:
    for name, table, sql in INDEXES:
        if _index_exists(conn, name):
            print(f'  - [SKIP] 索引 {name} 已存在')
            continue
        if not _table_exists(conn, table):
            print(f'  - [SKIP] 索引 {name} 依赖表 {table} 不存在')
            continue
        conn.execute(sql)
        print(f'  - [ADD] 索引 {name}')


def _do_param_enabled(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'control_parameter_defs'):
        print('  - control_parameter_defs 不存在, 跳过参数种子')
        return
    code, name, value_type, default_value, desc = PARAM_DEF
    row = conn.execute(
        'SELECT id FROM control_parameter_defs WHERE code=?', (code,)).fetchone()
    if row:
        conn.execute(
            'UPDATE control_parameter_defs SET name=?, domain=?, value_type=?, '
            'target_bo=?, default_value=?, description=?, status=? WHERE id=?',
            (name, 'procurement', value_type, 'purchase_order', default_value,
             desc, 'active', row[0]))
        print(f'  - [SKIP] 参数 {code} 已存在 (id={row[0]})')
        return
    conn.execute(
        'INSERT INTO control_parameter_defs '
        '(code, name, domain, value_type, target_bo, default_value, status, '
        ' description, created_at) '
        "VALUES (?, ?, 'procurement', ?, 'purchase_order', ?, 'active', ?, "
        "datetime('now'))",
        (code, name, value_type, default_value, desc))
    print(f'  - [NEW] 参数 {code}')


def _do_mark_legacy(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'control_parameter_defs'):
        return
    for code in LEGACY_PARAMS:
        row = conn.execute(
            'SELECT id, description FROM control_parameter_defs WHERE code=?',
            (code,)).fetchone()
        if not row:
            print(f'  - [SKIP] 旧参数 {code} 不存在')
            continue
        desc = row[1] or ''
        if DEPRECATED_MARK in desc:
            print(f'  - [SKIP] 旧参数 {code} 已标记 deprecated')
            continue
        conn.execute(
            'UPDATE control_parameter_defs SET description=? WHERE id=?',
            (f'{DEPRECATED_MARK} {desc}'.strip(), row[0]))
        print(f'  - [MARK] 旧参数 {code} -> deprecated')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v178] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v178] 开始: 通用审批规则模型')
        _do_tables(conn)
        _do_indexes(conn)
        _do_param_enabled(conn)
        _do_mark_legacy(conn)
        conn.commit()
        print('[v178] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v178] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v178 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        required_cols = {
            POLICY_TABLE: ('code', 'name', 'scope_bo', 'trigger_action',
                           'priority', 'effective_from', 'effective_to',
                           'status'),
            CONDITION_TABLE: ('policy_id', 'group_no', 'logic', 'field_id',
                              'operator', 'value_text', 'value_number',
                              'value_json'),
            STEP_TABLE: ('policy_id', 'step_no', 'approver_type', 'approver_ref',
                         'min_amount', 'max_amount', 'approve_mode', 'sla_hours'),
        }
        for table, cols in required_cols.items():
            if not _table_exists(conn, table):
                print(f'[v178 verify] FAIL: 缺表 {table}')
                ok = False
                continue
            have = _columns(conn, table)
            for col in cols:
                if col not in have:
                    print(f'[v178 verify] FAIL: 缺列 {table}.{col}')
                    ok = False

        for name, _table, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v178 verify] FAIL: 缺索引 {name}')
                ok = False

        if _table_exists(conn, 'control_parameter_defs'):
            row = conn.execute(
                'SELECT value_type, default_value FROM control_parameter_defs '
                'WHERE code=?', (PARAM_ENABLED,)).fetchone()
            if not row:
                print(f'[v178 verify] FAIL: 缺参数 {PARAM_ENABLED}')
                ok = False
            else:
                if row[0] != PARAM_DEF[2]:
                    print(f'[v178 verify] FAIL: 参数 {PARAM_ENABLED} value_type')
                    ok = False
                if (row[1] or '') != PARAM_DEF[3]:
                    print(f'[v178 verify] FAIL: 参数 {PARAM_ENABLED} default_value')
                    ok = False

        print('[v178 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v178 rollback] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for name, _table, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')
                print(f'  - [DROP] 索引 {name}')
        for table in (STEP_TABLE, CONDITION_TABLE, POLICY_TABLE):
            if _table_exists(conn, table):
                conn.execute(f'DROP TABLE IF EXISTS {table}')
                print(f'  - [DROP] 表 {table}')
        conn.commit()
        print('[v178 rollback] 完成（参数定义 / 旧参数标记保留）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v178 rollback] 失败: {e}')
        return False
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(get_meta_db_path())
    print('DB: %s' % db)

    if '--verify' in sys.argv:
        sys.exit(0 if verify(db) else 1)
    elif '--rollback' in sys.argv:
        sys.exit(0 if rollback(db) else 1)
    else:
        if not migrate(db):
            sys.exit(1)
        sys.exit(0 if verify(db) else 1)

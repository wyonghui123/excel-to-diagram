# -*- coding: utf-8 -*-
"""库存测试替身：内存 SQLite + DataSource 形状 + INV-1 种子。

只供 meta/tests/test_inventory_*.py 与桥接测试使用；不触碰真实库。
DDL 与种子直接复用 v201 迁移常量，避免测试与迁移漂移。
"""

import io
import sqlite3
from contextlib import redirect_stdout

from meta.migrations.v201__inventory_foundation import (
    BAL_TABLE, INDEXES, NUMBER_SEQUENCE, TABLES, TRANSACTION_TYPES, TX_TABLE,
    TYPES_TABLE,
)
from meta.migrations.v205__inventory_segment_reservation import (
    apply_segment_schema,
)
from meta.migrations.v216__reservation_closed_status import (
    apply_closed_status,
)

ORG_ID = 1
OTHER_ORG_ID = 2
LOCATION_ID = 7
OTHER_LOCATION_ID = 8
ITEM_ID = 900
UOM_ID = 3
BATCH_ID = 11

SCHEMA = """
CREATE TABLE orgs (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT,
    status TEXT DEFAULT 'active'
);
CREATE TABLE org_functions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id INTEGER,
    function_type TEXT,
    status TEXT DEFAULT 'active'
);
CREATE TABLE locations (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT,
    status TEXT DEFAULT 'active',
    org_id INTEGER
);
CREATE TABLE items (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT,
    status TEXT DEFAULT 'active'
);
CREATE TABLE uoms (
    id INTEGER PRIMARY KEY,
    code TEXT,
    name TEXT,
    status TEXT DEFAULT 'active'
);
CREATE TABLE batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_no TEXT NOT NULL,
    item_id INTEGER NOT NULL,
    org_id INTEGER NOT NULL,
    quality_status TEXT DEFAULT 'unrestricted',
    production_date TEXT,
    expiry_date TEXT,
    created_at TEXT,
    updated_at TEXT,
    UNIQUE (item_id, org_id, batch_no)
);
CREATE TABLE number_sequences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    pattern TEXT,
    scope_fields TEXT,
    date_field TEXT,
    start_value INTEGER,
    on_exhaust TEXT,
    preview TEXT,
    status TEXT DEFAULT 'active',
    description TEXT,
    created_at TEXT
);
CREATE TABLE control_parameter_defs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,
    name TEXT,
    domain TEXT,
    value_type TEXT,
    target_bo TEXT,
    default_value TEXT,
    status TEXT DEFAULT 'active',
    description TEXT,
    created_at TEXT
);
CREATE TABLE control_parameter_values (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    control_parameter_id INTEGER,
    value TEXT,
    status TEXT DEFAULT 'active'
);
"""


class _Tx:
    """最小事务上下文：外层 BEGIN IMMEDIATE，嵌套只透传。"""

    def __init__(self, ds):
        self.ds = ds
        self.owned = False

    def __enter__(self):
        if not self.ds.conn.in_transaction:
            self.ds.conn.execute('BEGIN IMMEDIATE')
            self.owned = True
        return self

    def __exit__(self, exc_type, exc, tb):
        if self.owned:
            if exc_type:
                self.ds.conn.rollback()
            else:
                self.ds.conn.commit()
        return False


class MemDS:
    """sqlite3 连接 → DataSource 形状（execute 返回 cursor 以取 lastrowid）。"""

    def __init__(self, conn):
        self.conn = conn

    @property
    def in_transaction(self):
        return bool(self.conn.in_transaction)

    def query(self, sql, params=None):
        cur = self.conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self.conn.execute(sql, list(params or []))

    def commit(self):
        self.conn.commit()

    def transaction(self):
        return _Tx(self)


def build_db():
    conn = sqlite3.connect(':memory:', isolation_level=None)
    conn.executescript(SCHEMA)
    _install_tables(conn)
    _seed_types(conn)
    _seed_sequence(conn)
    conn.commit()
    return conn


def _columns(conn, table):
    return {row[1] for row in conn.execute(
        'PRAGMA table_info(%s)' % table).fetchall()}


def _table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        [table]).fetchone() is not None


def _install_tables(conn):
    for table, ddl in TABLES:
        if not _table_exists(conn, table):
            conn.execute(ddl)
    for name, _table, ddl in INDEXES:
        conn.execute(ddl)
    # INV-2：段列 / 预留表 / 线索表 / 余额新唯一键（与 v205 单一 DDL 来源）
    with redirect_stdout(io.StringIO()):
        apply_segment_schema(conn)
        apply_closed_status(conn)


def _seed_types(conn):
    if not _table_exists(conn, TYPES_TABLE):
        return
    for code, name, category, direction, affects, sort_order, desc in \
            TRANSACTION_TYPES:
        if conn.execute(
                'SELECT 1 FROM %s WHERE code=?' % TYPES_TABLE,
                [code]).fetchone():
            continue
        conn.execute(
            "INSERT INTO %s (code, name, category, direction, affects_on_hand, "
            "status, sort_order, description, created_at) "
            "VALUES (?, ?, ?, ?, ?, 'active', ?, ?, datetime('now'))"
            % TYPES_TABLE,
            [code, name, category, direction, affects, sort_order, desc])


def _seed_sequence(conn):
    if conn.execute(
            'SELECT 1 FROM number_sequences WHERE code=?',
            [NUMBER_SEQUENCE[0]]).fetchone():
        return
    values = {
        'code': NUMBER_SEQUENCE[0],
        'name': NUMBER_SEQUENCE[1],
        'pattern': NUMBER_SEQUENCE[2],
        'scope_fields': None,
        'date_field': NUMBER_SEQUENCE[3],
        'start_value': NUMBER_SEQUENCE[4],
        'on_exhaust': NUMBER_SEQUENCE[5],
        'status': 'active',
        'description': NUMBER_SEQUENCE[6],
    }
    cols = _columns(conn, 'number_sequences')
    row = {k: v for k, v in values.items() if k in cols}
    keys = list(row)
    conn.execute(
        'INSERT INTO number_sequences (%s) VALUES (%s)'
        % (', '.join(keys), ', '.join('?' * len(keys))),
        [row[k] for k in keys])


def set_param(conn, code, value='0', def_id=None):
    cols = _columns(conn, 'control_parameter_defs')
    if conn.execute(
            'SELECT 1 FROM control_parameter_defs WHERE code=?',
            [code]).fetchone():
        if 'value_type' in cols:
            conn.execute(
                'UPDATE control_parameter_defs SET default_value=?, '
                "value_type='bool' WHERE code=?", [str(value), code])
        else:
            conn.execute(
                'UPDATE control_parameter_defs SET default_value=? WHERE code=?',
                [str(value), code])
        return
    if 'value_type' in cols:
        conn.execute(
            'INSERT INTO control_parameter_defs '
            '(id, code, default_value, status, value_type) VALUES (?, ?, ?, ?, ?)',
            [def_id, code, str(value), 'active', 'bool'])
    else:
        conn.execute(
            'INSERT INTO control_parameter_defs '
            '(id, code, default_value, status) VALUES (?, ?, ?, ?)',
            [def_id, code, str(value), 'active'])


def enable_posting(conn, enabled=True):
    set_param(conn, 'inventory_posting_enabled', '1' if enabled else '0')
    conn.commit()


def set_allow_negative(conn, enabled=False):
    set_param(conn, 'inventory_allow_negative', '1' if enabled else '0')
    conn.commit()


def seed(conn=None, allow_negative=False):
    conn = conn or build_db()
    conn.execute(
        'INSERT OR IGNORE INTO orgs (id, code, name, status) VALUES (?, ?, ?, ?)',
        [ORG_ID, 'ORG1', '库存组织1', 'active'])
    conn.execute(
        'INSERT OR IGNORE INTO orgs (id, code, name, status) VALUES (?, ?, ?, ?)',
        [OTHER_ORG_ID, 'ORG2', '库存组织2', 'active'])
    conn.execute(
        'INSERT OR IGNORE INTO org_functions (org_id, function_type, status) '
        "VALUES (?, 'inventory', 'active')", [ORG_ID])
    conn.execute(
        'INSERT OR IGNORE INTO org_functions (org_id, function_type, status) '
        "VALUES (?, 'inventory', 'active')", [OTHER_ORG_ID])
    if 'default_inventory_location_id' not in _columns(conn, 'orgs'):
        conn.execute(
            'ALTER TABLE orgs ADD COLUMN default_inventory_location_id INTEGER')
    conn.execute(
        'UPDATE orgs SET default_inventory_location_id = ? WHERE id = ?',
        [LOCATION_ID, ORG_ID])
    conn.execute(
        'INSERT OR IGNORE INTO locations (id, code, name, status, org_id) '
        'VALUES (?, ?, ?, ?, ?)',
        [LOCATION_ID, 'LOC7', '库位7', 'active', ORG_ID])
    conn.execute(
        'INSERT OR IGNORE INTO locations (id, code, name, status, org_id) '
        'VALUES (?, ?, ?, ?, ?)',
        [OTHER_LOCATION_ID, 'LOC8', '库位8', 'active', OTHER_ORG_ID])
    if 'base_uom' not in _columns(conn, 'items'):
        conn.execute('ALTER TABLE items ADD COLUMN base_uom INTEGER')
    conn.execute(
        'INSERT OR IGNORE INTO items (id, code, name, status, base_uom) '
        'VALUES (?, ?, ?, ?, ?)',
        [ITEM_ID, 'ITEM900', '物料900', 'active', UOM_ID])
    conn.execute(
        'INSERT OR IGNORE INTO uoms (id, code, name, status) VALUES (?, ?, ?, ?)',
        [UOM_ID, 'UOM3', '单位3', 'active'])
    conn.execute(
        'INSERT OR IGNORE INTO batches (id, batch_no, item_id, org_id, '
        "quality_status) VALUES (?, 'B001', ?, ?, 'unrestricted')",
        [BATCH_ID, ITEM_ID, ORG_ID])
    set_param(conn, 'inventory_posting_enabled', '1')
    set_param(conn, 'inventory_allow_negative',
              '1' if allow_negative else '0')
    conn.commit()
    return conn


def posting_service(conn):
    from meta.services.inventory_posting_service import InventoryPostingService
    return InventoryPostingService(MemDS(conn))


def guard_service(conn):
    from meta.services.inventory_guard_service import InventoryGuardService
    return InventoryGuardService(MemDS(conn))


def opening_service(conn):
    from meta.services.inventory_opening_service import InventoryOpeningService
    return InventoryOpeningService(MemDS(conn))


def install_inventory(conn, enable=True):
    """给既有测试替身（收货 / 调拨）补库存表、主数据列与参数。

    - orgs 补 default_inventory_location_id
    - items 补 base_uom（默认取 uom_id=3）
    - 建 batches（若缺）
    - 建 v201 三张库存表 + 索引 + 类型 + INV 序列 + 两个参数
    """
    if not _table_exists(conn, 'batches'):
        conn.execute(
            'CREATE TABLE batches (id INTEGER PRIMARY KEY AUTOINCREMENT, '
            'batch_no TEXT NOT NULL, item_id INTEGER NOT NULL, '
            'org_id INTEGER NOT NULL, '
            "quality_status TEXT DEFAULT 'unrestricted', "
            'production_date TEXT, expiry_date TEXT, created_at TEXT, '
            'updated_at TEXT, UNIQUE (item_id, org_id, batch_no))')
    if 'default_inventory_location_id' not in _columns(conn, 'orgs'):
        conn.execute(
            'ALTER TABLE orgs ADD COLUMN default_inventory_location_id INTEGER')
    if not _table_exists(conn, 'items'):
        conn.execute(
            'CREATE TABLE items (id INTEGER PRIMARY KEY, code TEXT, name TEXT, '
            'status TEXT DEFAULT \'active\', base_uom INTEGER)')
    if not _table_exists(conn, 'uoms'):
        conn.execute(
            'CREATE TABLE uoms (id INTEGER PRIMARY KEY, code TEXT, name TEXT, '
            'status TEXT DEFAULT \'active\')')
    if 'base_uom' not in _columns(conn, 'items'):
        conn.execute('ALTER TABLE items ADD COLUMN base_uom INTEGER')
    conn.execute('UPDATE items SET base_uom = 3 WHERE base_uom IS NULL')
    _install_tables(conn)
    _seed_types(conn)
    _seed_sequence(conn)
    set_param(conn, 'inventory_posting_enabled', '1' if enable else '0')
    set_param(conn, 'inventory_allow_negative', '0')
    conn.commit()
    return conn

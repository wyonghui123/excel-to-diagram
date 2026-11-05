# -*- coding: utf-8 -*-
"""[v217 2026-11-05] 包装容器状态机补齐 planned / in_transit

依据:
  docs/specs/p6-serial-number-model/spec.md §11.15.5 D19

范围:
  1. 重建 handling_units：CHECK 由 4 态扩到 6 态
     （planned / open / sealed / in_transit / shipped / void）。
  2. 重建 5 条索引（uq_hu_no / idx_hu_parent / idx_hu_root /
     idx_hu_location / idx_hu_status）。
  3. hu_status 枚举补 planned / in_transit，并按新顺序重排 sort_order。

为什么重建表:
  SQLite 无法原地修改 CHECK 约束；v211 的 DDL 把状态锁在 4 态，只能
  新建表 → 拷数据 → 删旧表 → 改名 → 重建索引。

明确不做:
  1. 不改 hu_transactions 的 txn_type（列无 CHECK，发运/到达复用 ship 事件，
     以 remark 区分）。
  2. 不产生 planned 行（装箱计划二期启用）。
  3. 不迁移业务数据：v216 之前不存在 in_transit，回滚时才需要把
     planned / in_transit 归并回旧态。

幂等:
  检测到表定义已含 in_transit 即跳过重建；索引 / 枚举值先查后用。

回滚:
  planned → open、in_transit → sealed；再按 4 态 DDL 重建；
  删除两个枚举值（先归并数据，避免悬挂引用）。
"""
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v217__handling_unit_status'

TABLE = 'handling_units'
TEMP_TABLE = 'handling_units__v217'

NEW_STATUSES = ('planned', 'open', 'sealed', 'in_transit', 'shipped', 'void')
OLD_STATUSES = ('open', 'sealed', 'shipped', 'void')

COLUMNS = (
    'id', 'created_by', 'updated_by', 'hu_no', 'hu_type',
    'packaging_item_id', 'org_id', 'location_id', 'parent_hu_id', 'root_hu_id',
    'status', 'is_reusable', 'cycle_no', 'gross_weight', 'tare_weight',
    'net_weight', 'volume', 'uom_id', 'source_doc_type', 'source_doc_id',
    'sealed_at', 'shipped_at', 'voided_at', 'remark', 'created_at', 'updated_at',
)

NEW_DDL = """
CREATE TABLE handling_units__v217 (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hu_no VARCHAR(40) NOT NULL,
    hu_type VARCHAR(20) NOT NULL DEFAULT 'carton',
    packaging_item_id INTEGER,
    org_id INTEGER NOT NULL,
    location_id INTEGER,
    parent_hu_id INTEGER,
    root_hu_id INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    is_reusable INTEGER NOT NULL DEFAULT 0,
    cycle_no INTEGER NOT NULL DEFAULT 1,
    gross_weight DECIMAL(18,4),
    tare_weight DECIMAL(18,4),
    net_weight DECIMAL(18,4),
    volume DECIMAL(18,6),
    uom_id INTEGER,
    source_doc_type VARCHAR(50),
    source_doc_id INTEGER,
    sealed_at DATETIME,
    shipped_at DATETIME,
    voided_at DATETIME,
    remark VARCHAR(255),
    created_at DATETIME,
    updated_at DATETIME,
    CHECK (hu_type IN ('pallet', 'carton', 'bin', 'container', 'other')),
    CHECK (status IN ('planned', 'open', 'sealed', 'in_transit', 'shipped', 'void')),
    FOREIGN KEY (org_id) REFERENCES orgs(id),
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (packaging_item_id) REFERENCES items(id),
    FOREIGN KEY (parent_hu_id) REFERENCES handling_units(id),
    FOREIGN KEY (root_hu_id) REFERENCES handling_units(id)
)
"""

OLD_DDL = """
CREATE TABLE handling_units__v217 (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    hu_no VARCHAR(40) NOT NULL,
    hu_type VARCHAR(20) NOT NULL DEFAULT 'carton',
    packaging_item_id INTEGER,
    org_id INTEGER NOT NULL,
    location_id INTEGER,
    parent_hu_id INTEGER,
    root_hu_id INTEGER,
    status VARCHAR(20) NOT NULL DEFAULT 'open',
    is_reusable INTEGER NOT NULL DEFAULT 0,
    cycle_no INTEGER NOT NULL DEFAULT 1,
    gross_weight DECIMAL(18,4),
    tare_weight DECIMAL(18,4),
    net_weight DECIMAL(18,4),
    volume DECIMAL(18,6),
    uom_id INTEGER,
    source_doc_type VARCHAR(50),
    source_doc_id INTEGER,
    sealed_at DATETIME,
    shipped_at DATETIME,
    voided_at DATETIME,
    remark VARCHAR(255),
    created_at DATETIME,
    updated_at DATETIME,
    CHECK (hu_type IN ('pallet', 'carton', 'bin', 'container', 'other')),
    CHECK (status IN ('open', 'sealed', 'shipped', 'void')),
    FOREIGN KEY (org_id) REFERENCES orgs(id),
    FOREIGN KEY (location_id) REFERENCES locations(id),
    FOREIGN KEY (packaging_item_id) REFERENCES items(id),
    FOREIGN KEY (parent_hu_id) REFERENCES handling_units(id),
    FOREIGN KEY (root_hu_id) REFERENCES handling_units(id)
)
"""

INDEXES = (
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_hu_no '
    'ON handling_units(org_id, hu_no)',
    'CREATE INDEX IF NOT EXISTS idx_hu_parent ON handling_units(parent_hu_id)',
    'CREATE INDEX IF NOT EXISTS idx_hu_root ON handling_units(root_hu_id)',
    'CREATE INDEX IF NOT EXISTS idx_hu_location ON handling_units(location_id)',
    'CREATE INDEX IF NOT EXISTS idx_hu_status ON handling_units(status)',
)

ENUM_ORDER = (
    ('planned', '已计划', 'Planned', 1),
    ('open', '打开', 'Open', 2),
    ('sealed', '已密封', 'Sealed', 3),
    ('in_transit', '在途', 'In Transit', 4),
    ('shipped', '已发运', 'Shipped', 5),
    ('void', '已作废', 'Void', 6),
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def _status_sql(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (TABLE,)).fetchone()
    return (row[0] or '') if row else ''


def _rebuild(conn: sqlite3.Connection, ddl: str) -> None:
    """新建 → 拷数据 → 删旧 → 改名 → 重建索引。调用方保证表存在。"""
    conn.execute('PRAGMA foreign_keys=OFF')
    conn.execute('DROP TABLE IF EXISTS %s' % TEMP_TABLE)
    conn.execute(ddl)
    columns = ', '.join(COLUMNS)
    conn.execute('INSERT INTO %s (%s) SELECT %s FROM %s'
                 % (TEMP_TABLE, columns, columns, TABLE))
    conn.execute('DROP TABLE %s' % TABLE)
    conn.execute('ALTER TABLE %s RENAME TO %s' % (TEMP_TABLE, TABLE))
    for sql in INDEXES:
        conn.execute(sql)


def _do_enums(conn: sqlite3.Connection) -> None:
    if not (_table_exists(conn, 'enum_types')
            and _table_exists(conn, 'enum_values')):
        print('  - enum_types / enum_values 不存在, 跳过枚举')
        return
    if not conn.execute("SELECT 1 FROM enum_types WHERE id='hu_status'").fetchone():
        print('  - [SKIP] hu_status 枚举类型不存在（v211 未执行）')
        return
    for code, name, name_en, sort_order in ENUM_ORDER:
        row = conn.execute(
            'SELECT 1 FROM enum_values WHERE enum_type_id=? AND code=?',
            ('hu_status', code)).fetchone()
        if row:
            conn.execute(
                'UPDATE enum_values SET sort_order=? WHERE enum_type_id=? AND code=?',
                (sort_order, 'hu_status', code))
            print('  - [SKIP] 枚举值 hu_status.%s 已存在' % code)
            continue
        conn.execute(
            "INSERT INTO enum_values (enum_type_id, code, name, name_en, "
            "sort_order, is_active, is_system, created_at) "
            "VALUES ('hu_status', ?, ?, ?, ?, 1, 0, datetime('now'))",
            (code, name, name_en, sort_order))
        print('  - [NEW] 枚举值 hu_status.%s' % code)


def _drop_enums(conn: sqlite3.Connection) -> None:
    if not (_table_exists(conn, 'enum_types')
            and _table_exists(conn, 'enum_values')):
        return
    for code in ('planned', 'in_transit'):
        conn.execute(
            'DELETE FROM enum_values WHERE enum_type_id=? AND code=?',
            ('hu_status', code))
    for code, name, name_en, sort_order in (
            ('open', '打开', 'Open', 1),
            ('sealed', '已密封', 'Sealed', 2),
            ('shipped', '已发运', 'Shipped', 3),
            ('void', '已作废', 'Void', 4)):
        conn.execute(
            'UPDATE enum_values SET name=?, name_en=?, sort_order=? '
            'WHERE enum_type_id=? AND code=?',
            (name, name_en, sort_order, 'hu_status', code))


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print('[v217] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v217] 开始: 容器状态机补 planned / in_transit')
        if not _table_exists(conn, TABLE):
            print('[v217] handling_units 不存在，跳过重建（v211 未执行）')
        elif 'in_transit' in _status_sql(conn):
            print('  - [SKIP] handling_units 已含 in_transit')
        else:
            _rebuild(conn, NEW_DDL)
            print('  - [NEW] handling_units 重建为 6 态')
        _do_enums(conn)
        conn.commit()
        print('[v217] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v217] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print('[v217 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        if not _table_exists(conn, TABLE):
            print('[v217 verify] FAIL: 缺表 handling_units')
            return False
        sql = _status_sql(conn)
        for status in ('planned', 'in_transit'):
            if status not in sql:
                print('[v217 verify] FAIL: CHECK 缺状态 %s' % status)
                ok = False
        for name in ('uq_hu_no', 'idx_hu_parent', 'idx_hu_root',
                     'idx_hu_location', 'idx_hu_status'):
            if not conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                    (name,)).fetchone():
                print('[v217 verify] FAIL: 缺索引 %s' % name)
                ok = False
        if _table_exists(conn, 'enum_values'):
            for status in ('planned', 'in_transit'):
                if not conn.execute(
                        'SELECT 1 FROM enum_values WHERE enum_type_id=? AND code=?',
                        ('hu_status', status)).fetchone():
                    print('[v217 verify] FAIL: 缺枚举值 hu_status.%s' % status)
                    ok = False
        if ok:
            print('[v217 verify] PASS')
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print('[v217] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v217] 回滚: 容器状态机恢复 4 态')
        if _table_exists(conn, TABLE):
            conn.execute(
                "UPDATE handling_units SET status='open' WHERE status='planned'")
            conn.execute(
                "UPDATE handling_units SET status='sealed', shipped_at=NULL "
                "WHERE status='in_transit'")
            _rebuild(conn, OLD_DDL)
            print('  - [OK] handling_units 重建为 4 态')
        _drop_enums(conn)
        conn.commit()
        print('[v217 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v217 rollback] 失败: %s' % e)
        raise
    finally:
        conn.close()

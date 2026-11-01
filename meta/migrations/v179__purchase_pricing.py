# -*- coding: utf-8 -*-
"""[v179 2026-11-01] 采购定价（规则表 / 价格阶梯 / 累计口径参数）

依据:
  docs/specs/spec-purchase-order-object-model-2026-11-01.md
    §4.4.2 / Q16 / §14 步骤 6A

范围:
  1. 建 purchase_pricing_determinations（采购定价规则表）
       键：purchase_org_id + document_type_id + supplier_party_id
       值：seq（匹配次序）+ rate_table_id + agreement_scope（local / global）
       —— 不复用销售 pricing_determination（键不同，合并会让一半列恒空）
  2. rate_tables 加 scope_bo（默认 'sales_order'，采购价目表置 'purchase_order'）
     —— 价目表容器与销售共用，只按 scope 分隔，不新建 supplier_price_list
  3. rate_records 加价格阶梯字段 qty_from / qty_to / ship_to_location_id
       —— 同一条件多档命中时由服务层取最低价
  4. control_parameter_defs 种子 price_break_cumulative（bool，无隐式默认，
     必须显式配置；true = 按累计数量选档，false = 按本次数量）

幂等:
  表 / 列 / 索引 / 参数定义先查后用；重复执行打印 [SKIP]。

回滚:
  删索引 + 删表；rate_tables.scope_bo / rate_records 阶梯列保留
  （SQLite 旧版本不支持 DROP COLUMN，且销售侧已按默认值使用）。
"""
import sqlite3
import sys
from pathlib import Path

DET_TABLE = 'purchase_pricing_determinations'
RATE_TABLE = 'rate_tables'
RECORD_TABLE = 'rate_records'

RATE_TABLE_COLUMNS = (
    ('scope_bo', "VARCHAR(200) NOT NULL DEFAULT 'sales_order'"),
)
RATE_RECORD_COLUMNS = (
    ('qty_from', 'REAL'),
    ('qty_to', 'REAL'),
    ('ship_to_location_id', 'INTEGER'),
)

PARAM_DEF = (
    'price_break_cumulative', '价格阶梯是否按累计数量选档', 'bool', None,
    'NULL = 未配置（取价服务报错提示需显式配置）；'
    'true = 按累计数量选档；false = 按本次数量选档',
)

TABLES = (
    (DET_TABLE, """
CREATE TABLE IF NOT EXISTS purchase_pricing_determinations (
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code VARCHAR(200) UNIQUE NOT NULL,
    name VARCHAR(200) NOT NULL,
    purchase_org_id INTEGER,
    document_type_id INTEGER,
    supplier_party_id INTEGER,
    base_date_from DATETIME,
    base_date_to DATETIME,
    seq INTEGER NOT NULL DEFAULT 10,
    rate_table_id INTEGER,
    agreement_scope VARCHAR(200) NOT NULL DEFAULT 'local',
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (purchase_org_id) REFERENCES orgs(id),
    FOREIGN KEY (document_type_id) REFERENCES type_definitions(id),
    FOREIGN KEY (supplier_party_id) REFERENCES parties(id),
    FOREIGN KEY (rate_table_id) REFERENCES rate_tables(id)
)
"""),
)

INDEXES = (
    ('uidx_purchase_pricing_det_code', DET_TABLE,
     'CREATE UNIQUE INDEX IF NOT EXISTS uidx_purchase_pricing_det_code '
     'ON purchase_pricing_determinations(code)'),
    ('idx_purchase_pricing_det_org_supplier', DET_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_purchase_pricing_det_org_supplier '
     'ON purchase_pricing_determinations(purchase_org_id, supplier_party_id, seq)'),
    ('idx_purchase_pricing_det_scope', DET_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_purchase_pricing_det_scope '
     'ON purchase_pricing_determinations(agreement_scope, status)'),
    ('idx_purchase_pricing_det_table', DET_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_purchase_pricing_det_table '
     'ON purchase_pricing_determinations(rate_table_id)'),
    ('idx_rate_table_scope', RATE_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_rate_table_scope '
     'ON rate_tables(scope_bo, status)'),
    ('idx_rate_record_break', RECORD_TABLE,
     'CREATE INDEX IF NOT EXISTS idx_rate_record_break '
     'ON rate_records(rate_table_id, qty_from, qty_to)'),
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


def _ensure_columns(conn: sqlite3.Connection, table: str, columns) -> None:
    if not _table_exists(conn, table):
        print(f'  - [SKIP] 表 {table} 不存在（由既有对象创建）')
        return
    have = _columns(conn, table)
    for name, ddl in columns:
        if name in have:
            print(f'  - [SKIP] 列 {table}.{name} 已存在')
            continue
        conn.execute(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}')
        print(f'  - [ALTER] 列 {table}.{name}')


def _do_indexes(conn: sqlite3.Connection) -> None:
    for name, table, sql in INDEXES:
        if _index_exists(conn, name):
            print(f'  - [SKIP] 索引 {name} 已存在')
            continue
        if not _table_exists(conn, table):
            print(f'  - [SKIP] 索引 {name} 依赖表 {table} 不存在')
            continue
        required = sql.split('(')[1].split(')')[0].split(',')
        cols = _columns(conn, table)
        missing = [c.strip() for c in required if c.strip() not in cols]
        if missing:
            print(f'  - [SKIP] 索引 {name} 依赖列缺失: {missing}')
            continue
        conn.execute(sql)
        print(f'  - [ADD] 索引 {name}')


def _do_param(conn: sqlite3.Connection) -> None:
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


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v179] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v179] 开始: 采购定价（规则表 / 价格阶梯 / 累计口径参数）')
        _do_tables(conn)
        _ensure_columns(conn, RATE_TABLE, RATE_TABLE_COLUMNS)
        _ensure_columns(conn, RECORD_TABLE, RATE_RECORD_COLUMNS)
        _do_indexes(conn)
        _do_param(conn)
        conn.commit()
        print('[v179] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v179] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v179 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        required_cols = {
            DET_TABLE: ('code', 'name', 'purchase_org_id', 'document_type_id',
                        'supplier_party_id', 'base_date_from', 'base_date_to',
                        'seq', 'rate_table_id', 'agreement_scope', 'status'),
            RATE_TABLE: ('scope_bo',),
            RECORD_TABLE: ('qty_from', 'qty_to', 'ship_to_location_id'),
        }
        for table, cols in required_cols.items():
            if not _table_exists(conn, table):
                print(f'[v179 verify] FAIL: 缺表 {table}')
                ok = False
                continue
            have = _columns(conn, table)
            for col in cols:
                if col not in have:
                    print(f'[v179 verify] FAIL: 缺列 {table}.{col}')
                    ok = False

        for name, _table, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v179 verify] FAIL: 缺索引 {name}')
                ok = False

        # 销售取价零回归：既有价目表必须有 scope_bo 且默认为 sales_order
        if _table_exists(conn, RATE_TABLE) and 'scope_bo' in _columns(conn, RATE_TABLE):
            row = conn.execute(
                "SELECT COUNT(1) FROM rate_tables WHERE scope_bo IS NULL").fetchone()
            if row[0]:
                print(f'[v179 verify] FAIL: {row[0]} 条 rate_tables 缺 scope_bo')
                ok = False

        if _table_exists(conn, 'control_parameter_defs'):
            row = conn.execute(
                'SELECT value_type, default_value FROM control_parameter_defs '
                'WHERE code=?', (PARAM_DEF[0],)).fetchone()
            if not row:
                print(f'[v179 verify] FAIL: 缺参数 {PARAM_DEF[0]}')
                ok = False
            else:
                if row[0] != PARAM_DEF[2]:
                    print(f'[v179 verify] FAIL: 参数 {PARAM_DEF[0]} value_type')
                    ok = False
                if row[1] is not None:
                    print(f'[v179 verify] FAIL: 参数 {PARAM_DEF[0]} 不应有隐式默认值')
                    ok = False

        print('[v179 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print(f'[v179 rollback] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for name, _table, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')
                print(f'  - [DROP] 索引 {name}')
        if _table_exists(conn, DET_TABLE):
            conn.execute(f'DROP TABLE IF EXISTS {DET_TABLE}')
            print(f'  - [DROP] 表 {DET_TABLE}')
        conn.commit()
        print('[v179 rollback] 完成（rate_tables / rate_records 新增列保留）')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v179 rollback] 失败: {e}')
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

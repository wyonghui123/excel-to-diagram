# -*- coding: utf-8 -*-
"""[v216 2026-11-05] 单据 ↔ 包装容器关系桥表（document_hu_links）

依据:
  docs/specs/p6-serial-number-model/spec.md §11.15（D17 / D18 / P1 已落）

背景:
  v211 只给单据行加了单值 `hu_no`，无法表达「一行多箱」与「一箱多行」：
  - `handling_unit_items` 没有单据行引用（只有 item / batch / serial / qty）；
  - 一行只能写一个容器号，拆箱无处记录。
  本迁移建独立关系表，把「单据行 ↔ 容器」从文本字段下沉为一等关系（对标
  SAP `VEPO.VBELN/POSNR + VEMNG`、Oracle `WSH_DELIVERY_ASSIGNMENTS`）。

范围:
  1. 建表 document_hu_links（doc_type / doc_id / line_id / hu_id / direction /
     link_type / tentative / qty）。
  2. 4 条索引；其中唯一索引用表达式 COALESCE(line_id, 0)，
     因为 SQLite 普通 UNIQUE 遇到 NULL 会放过重复行。
  3. 注册 2 个枚举：document_hu_link_type / document_hu_direction。
  4. 权限 2 条（read / list）+ 授权 admin / default；不建独立菜单（二期由
     MOMP 的「关联单据」tab 承载）。
  5. 存量回填：receipt_lines / shipment_lines / transfer_order_lines 的 hu_no
     反查 handling_units.id；同号多容器（跨组织）无法判定时不回填并计数告警。

明确不做:
  hu_status 增加 planned / in_transit **不在本迁移**：v211 的 handling_units
  有 `CHECK (status IN ('open','sealed','shipped','void'))`，SQLite 改 CHECK
  必须重建表（含索引与子表外键），风险独立，另开 v217 处理。

幂等:
  表 / 索引 / 枚举 / 权限 / 授权 / 回填 均先查后用；重复执行打印 [SKIP]。

回滚:
  删索引 → 删表 → 删权限与授权（枚举值保留，避免影响已引用数据）。
"""
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v216__document_hu_links'

LINK_TABLE = 'document_hu_links'

TABLES = (
    (LINK_TABLE, """
CREATE TABLE IF NOT EXISTS document_hu_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type VARCHAR(30) NOT NULL,
    doc_id INTEGER NOT NULL,
    line_id INTEGER,
    hu_id INTEGER NOT NULL,
    direction VARCHAR(10) NOT NULL,
    link_type VARCHAR(20) NOT NULL DEFAULT 'packed',
    tentative INTEGER NOT NULL DEFAULT 0,
    qty DECIMAL(18,4),
    org_id INTEGER,
    created_at DATETIME NOT NULL,
    created_by VARCHAR(200),
    updated_at DATETIME,
    remark VARCHAR(255),
    CHECK (direction IN ('in', 'out')),
    CHECK (link_type IN ('planned', 'packed', 'shipped')),
    FOREIGN KEY (hu_id) REFERENCES handling_units(id)
)
"""),
)

INDEXES = (
    (LINK_TABLE, 'uq_document_hu_link',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_document_hu_link '
     'ON document_hu_links(doc_type, doc_id, COALESCE(line_id, 0), hu_id, direction)'),
    (LINK_TABLE, 'idx_document_hu_doc',
     'CREATE INDEX IF NOT EXISTS idx_document_hu_doc '
     'ON document_hu_links(doc_type, doc_id)'),
    (LINK_TABLE, 'idx_document_hu_hu',
     'CREATE INDEX IF NOT EXISTS idx_document_hu_hu '
     'ON document_hu_links(hu_id, direction)'),
    (LINK_TABLE, 'idx_document_hu_line',
     'CREATE INDEX IF NOT EXISTS idx_document_hu_line ON document_hu_links(line_id)'),
)

ENUM_SEEDS = (
    ('document_hu_link_type', '单据容器关系状态',
     '关系推进（计划 / 已装箱 / 已发运）',
     (('planned', '已计划', 'Planned'),
      ('packed', '已装箱', 'Packed'),
      ('shipped', '已发运', 'Shipped'))),
    ('document_hu_direction', '单据容器方向',
     '关系方向（入库 / 出库）',
     (('in', '入库', 'Inbound'),
      ('out', '出库', 'Outbound'))),
)

PERMISSIONS = (
    ('document_hu_link:document_hu_link_read', '单据容器关系查看',
     'document_hu_link', 'read'),
    ('document_hu_link:document_hu_link_list', '单据容器关系查询',
     'document_hu_link', 'list'),
)

GRANT_TO_SETS = ('admin', 'default')

# (单据行表, 单据外键列, doc_type, direction, link_type, 数量列候选)
# 生产库 receipt_lines 用 qty_received，部分测试替身 / 历史库用 qty，运行时探测。
BACKFILL_SPECS = (
    ('receipt_lines', 'receipt_id', 'receipt', 'in', 'packed',
     ('qty_received', 'qty')),
    ('shipment_lines', 'delivery_id', 'shipment', 'out', 'shipped',
     ('qty', 'qty_received')),
    ('transfer_order_lines', 'transfer_order_id', 'transfer_order', 'out',
     'shipped', ('qty', 'qty_received')),
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    try:
        return {row[1] for row in conn.execute(
            'PRAGMA table_info(%s)' % table).fetchall()}
    except sqlite3.Error:
        return set()


def _index_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
        (name,),
    ).fetchone() is not None


def _do_tables(conn: sqlite3.Connection) -> None:
    for table, sql in TABLES:
        if _table_exists(conn, table):
            print('  - [SKIP] 表 %s 已存在' % table)
            continue
        conn.execute(sql)
        print('  - [NEW] 表 %s' % table)


def _do_indexes(conn: sqlite3.Connection) -> None:
    for _table, name, sql in INDEXES:
        if _index_exists(conn, name):
            print('  - [SKIP] 索引 %s 已存在' % name)
            continue
        conn.execute(sql)
        print('  - [NEW] 索引 %s' % name)


def _do_enums(conn: sqlite3.Connection) -> None:
    if not (_table_exists(conn, 'enum_types')
            and _table_exists(conn, 'enum_values')):
        print('  - enum_types / enum_values 不存在, 跳过枚举种子')
        return
    for type_id, type_name, description, values in ENUM_SEEDS:
        if conn.execute('SELECT 1 FROM enum_types WHERE id=?',
                        (type_id,)).fetchone():
            print('  - [SKIP] 枚举类型 %s 已存在' % type_id)
        else:
            conn.execute(
                "INSERT INTO enum_types (id, name, category, mutability, "
                "dimension_schema, description, created_at) "
                "VALUES (?, ?, 'business', 'extensible', NULL, ?, datetime('now'))",
                (type_id, type_name, description),
            )
            print('  - [NEW] 枚举类型 %s (%s)' % (type_id, type_name))
        for sort_order, (code, value_name, name_en) in enumerate(values, start=1):
            if conn.execute(
                    'SELECT 1 FROM enum_values WHERE enum_type_id=? AND code=?',
                    (type_id, code)).fetchone():
                continue
            conn.execute(
                "INSERT INTO enum_values (enum_type_id, code, name, name_en, "
                "sort_order, is_active, is_system, created_at) "
                "VALUES (?, ?, ?, ?, ?, 1, 0, datetime('now'))",
                (type_id, code, value_name, name_en, sort_order),
            )
            print('    - [NEW] 枚举值 %s.%s' % (type_id, code))


def _do_permissions(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'permissions'):
        print('  - permissions 表不存在, 跳过权限写入')
        return
    created = 0
    for code, name, resource_type, action in PERMISSIONS:
        cur = conn.execute(
            'INSERT OR IGNORE INTO permissions (code, name, resource_type, action) '
            'VALUES (?, ?, ?, ?)', (code, name, resource_type, action))
        if cur.rowcount:
            created += 1
            print('  - [NEW] 权限 %s (%s)' % (code, name))
    print('  - [SUMMARY] permissions: +%s' % created)


def _do_grants(conn: sqlite3.Connection) -> None:
    if not (_table_exists(conn, 'permissions')
            and _table_exists(conn, 'permission_sets')
            and _table_exists(conn, 'permission_set_permissions')):
        print('  - 权限集相关表缺失, 跳过授权')
        return
    cols = _columns(conn, 'permission_set_permissions')
    if 'permission_set_id' in cols:
        id_col = 'permission_set_id'
    elif 'role_id' in cols:
        id_col = 'role_id'
    else:
        return
    has_code_col = 'permission_code' in cols
    granted = 0
    for set_code in GRANT_TO_SETS:
        row = conn.execute(
            'SELECT id FROM permission_sets WHERE code=? AND is_active=1',
            (set_code,)).fetchone()
        if not row:
            continue
        permission_set_id = row[0]
        for code, _name, _rtype, _action in PERMISSIONS:
            prow = conn.execute(
                'SELECT id FROM permissions WHERE code=?', (code,)).fetchone()
            if not prow:
                continue
            if conn.execute(
                    'SELECT 1 FROM permission_set_permissions WHERE '
                    '%s = ? AND permission_id = ?' % id_col,
                    (permission_set_id, prow[0])).fetchone():
                continue
            if has_code_col:
                conn.execute(
                    'INSERT INTO permission_set_permissions '
                    '(%s, permission_code, permission_id, granted, created_at) '
                    "VALUES (?, ?, ?, 1, datetime('now'))" % id_col,
                    (permission_set_id, code, prow[0]))
            else:
                conn.execute(
                    'INSERT INTO permission_set_permissions '
                    '(%s, permission_id, granted, created_at) '
                    "VALUES (?, ?, 1, datetime('now'))" % id_col,
                    (permission_set_id, prow[0]))
            granted += 1
    print('  - [SUMMARY] permission_set_permissions: +%s' % granted)


def _do_backfill(conn: sqlite3.Connection) -> None:
    """把存量单据行 hu_no 转成关系行；同号多容器时不猜测，跳过并告警。"""
    if not _table_exists(conn, 'handling_units'):
        print('  - handling_units 不存在, 跳过回填')
        return
    inserted = skipped = 0
    for table, doc_fk, doc_type, direction, link_type, qty_cols in BACKFILL_SPECS:
        if not _table_exists(conn, table) or 'hu_no' not in _columns(conn, table):
            continue
        qty_col = next(
            (c for c in qty_cols if c in _columns(conn, table)), None)
        if not qty_col:
            continue
        rows = conn.execute(
            "SELECT l.{fk} AS doc_id, l.id AS line_id, l.{qty} AS qty, "
            "       l.hu_no AS hu_no, "
            "       (SELECT COUNT(*) FROM handling_units h "
            "         WHERE h.hu_no = l.hu_no) AS hu_count, "
            "       (SELECT MIN(h.id) FROM handling_units h "
            "         WHERE h.hu_no = l.hu_no) AS hu_id "
            "FROM {table} l "
            "WHERE TRIM(COALESCE(l.hu_no, '')) <> ''".format(
                fk=doc_fk, qty=qty_col, table=table)).fetchall()
        for doc_id, line_id, qty, hu_no, hu_count, hu_id in rows:
            if not hu_count:
                skipped += 1
                continue
            if hu_count > 1:
                skipped += 1
                print('  - [WARN] %s 行 %s 容器号 %s 命中 %s 个组织，跳过回填'
                      % (table, line_id, hu_no, hu_count))
                continue
            if conn.execute(
                    'SELECT 1 FROM document_hu_links WHERE doc_type=? AND '
                    'doc_id=? AND COALESCE(line_id, 0)=? AND hu_id=? AND '
                    'direction=?',
                    (doc_type, doc_id, line_id, hu_id, direction)).fetchone():
                continue
            conn.execute(
                'INSERT INTO document_hu_links (doc_type, doc_id, line_id, hu_id, '
                ' direction, link_type, tentative, qty, org_id, created_at, '
                ' updated_at) '
                "VALUES (?, ?, ?, ?, ?, ?, 0, ?, NULL, datetime('now'), datetime('now'))",
                (doc_type, doc_id, line_id, hu_id, direction, link_type, qty),
            )
            inserted += 1
    print('  - [SUMMARY] 回填 link: +%s，跳过 %s 行' % (inserted, skipped))


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v216] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v216] 开始: 单据 ↔ 包装容器关系桥表')
        _do_tables(conn)
        _do_indexes(conn)
        _do_enums(conn)
        _do_permissions(conn)
        _do_grants(conn)
        _do_backfill(conn)
        conn.commit()
        print('[v216] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v216] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v216 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        for table, _sql in TABLES:
            if not _table_exists(conn, table):
                print('[v216 verify] FAIL: 缺表 %s' % table)
                ok = False
        required = {'doc_type', 'doc_id', 'line_id', 'hu_id', 'direction',
                    'link_type', 'tentative', 'qty', 'org_id', 'created_at'}
        if _table_exists(conn, LINK_TABLE):
            missing = required - _columns(conn, LINK_TABLE)
            if missing:
                print('[v216 verify] FAIL: %s 缺列 %s'
                      % (LINK_TABLE, sorted(missing)))
                ok = False
        for _table, name, _sql in INDEXES:
            if not _index_exists(conn, name):
                print('[v216 verify] FAIL: 缺索引 %s' % name)
                ok = False
        if _table_exists(conn, 'enum_types'):
            for type_id, _name, _desc, values in ENUM_SEEDS:
                if not conn.execute('SELECT 1 FROM enum_types WHERE id=?',
                                    (type_id,)).fetchone():
                    print('[v216 verify] FAIL: 缺枚举类型 %s' % type_id)
                    ok = False
                for code, _vname, _en in values:
                    if not conn.execute(
                            'SELECT 1 FROM enum_values WHERE enum_type_id=? '
                            'AND code=?', (type_id, code)).fetchone():
                        print('[v216 verify] FAIL: 缺枚举值 %s.%s'
                              % (type_id, code))
                        ok = False
        if _table_exists(conn, 'permissions'):
            for code, *_ in PERMISSIONS:
                if not conn.execute('SELECT 1 FROM permissions WHERE code=?',
                                    (code,)).fetchone():
                    print('[v216 verify] FAIL: 缺权限 %s' % code)
                    ok = False
        if ok:
            print('[v216 verify] PASS')
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v216] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v216] 回滚: 单据 ↔ 包装容器关系桥表')
        for _table, name, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute('DROP INDEX IF EXISTS %s' % name)
        if _table_exists(conn, LINK_TABLE):
            conn.execute('DROP TABLE IF EXISTS %s' % LINK_TABLE)
        if _table_exists(conn, 'permissions'):
            for code, *_ in PERMISSIONS:
                if _table_exists(conn, 'permission_set_permissions'):
                    conn.execute(
                        'DELETE FROM permission_set_permissions WHERE permission_id '
                        'IN (SELECT id FROM permissions WHERE code=?)', (code,))
                conn.execute('DELETE FROM permissions WHERE code=?', (code,))
        conn.commit()
        print('[v216 rollback] 完成（枚举值保留）')
        return True
    except Exception as e:
        conn.rollback()
        print('[v216 rollback] 失败: %s' % e)
        raise
    finally:
        conn.close()

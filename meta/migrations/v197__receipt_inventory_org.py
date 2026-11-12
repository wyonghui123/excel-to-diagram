# -*- coding: utf-8 -*-
"""[v197 2026-11-03] 收货库存组织维度 TBD-6

依据:
  docs/specs/spec-receipt-object-model-2026-11-01.md TBD-6
  （Oracle Fusion SHIP_TO_ORG_ID 对应口径）

范围:
  1. receipts 增列 inventory_org_id（INTEGER，可空）；
     与既有 org_id（收货法人）正交，不改 org_id 语义（v195 法人校验不变）。
  2. 回填（仅处理 inventory_org_id IS NULL 的行）：
     · source_doc_type='transfer_order' 且 source_doc_id 非空 →
       取 transfer_orders.to_org_id（表不存在则跳过该来源）；
     · source_doc_type='purchase_order' → purchase_org_id 非空且该组织具备
       org_functions.function_type='inventory' 时写入 purchase_org_id；
       否则留空；
     · 其他来源留空。

幂等:
  列先查后用，重复执行打印 [SKIP]；回填只处理空列行，重复执行回填条数为 0。

回滚:
  SQLite 不支持 DROP COLUMN ⇒ 列保留（[KEEP]），仅把列值清 NULL（[CLEAR]）。

前置:
  回填依赖 transfer_orders / org_functions 两表；缺任一则该来源不参与回填
  （列照样创建）。
"""
import sqlite3
import sys
from pathlib import Path

# 允许以 `python meta/migrations/v197__receipt_inventory_org.py` 直接执行
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

MIGRATION_NAME = 'v197__receipt_inventory_org'

RECEIPT_TABLE = 'receipts'
COLUMN = 'inventory_org_id'
TRANSFER_ORDER_TABLE = 'transfer_orders'
ORG_FUNCTION_TABLE = 'org_functions'
FUNCTION_INVENTORY = 'inventory'
SOURCE_TRANSFER_ORDER = 'transfer_order'
SOURCE_PURCHASE_ORDER = 'purchase_order'

#: verify 抽样上限
VERIFY_SAMPLE_LIMIT = 20


class _ConnDS:
    """把 sqlite3.Connection 包成服务所需的 DataSource 形状（仅 query）。"""

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def query(self, sql, params=None):
        cur = self._conn.execute(sql, list(params or []))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def execute(self, sql, params=None):
        return self._conn.execute(sql, list(params or []))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}


def _do_column(conn: sqlite3.Connection) -> bool:
    if not _table_exists(conn, RECEIPT_TABLE):
        print(f'  - [SKIP] 表 {RECEIPT_TABLE} 不存在')
        return False
    if COLUMN in _columns(conn, RECEIPT_TABLE):
        print(f'  - [SKIP] 列 {RECEIPT_TABLE}.{COLUMN} 已存在')
        return True
    conn.execute('ALTER TABLE %s ADD COLUMN %s INTEGER NULL'
                 % (RECEIPT_TABLE, COLUMN))
    print(f'  - [CREATE] 列 {RECEIPT_TABLE}.{COLUMN}')
    return True


def _has_inventory_function(conn: sqlite3.Connection, org_id) -> bool:
    """复用调拨守卫的职能判定；缺表按「不具备」处理（回填留空）。"""
    if not _table_exists(conn, ORG_FUNCTION_TABLE):
        return False
    try:
        from meta.services.transfer_order_guard_service import (
            TransferOrderGuardService)
        return TransferOrderGuardService(
            _ConnDS(conn))._org_has_function(org_id, FUNCTION_INVENTORY)
    except Exception:
        return False


def _do_backfill(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        'SELECT id, source_doc_type, source_doc_id, purchase_org_id '
        'FROM %s WHERE %s IS NULL ORDER BY id' % (RECEIPT_TABLE, COLUMN)
    ).fetchall()
    if not rows:
        print('  - [SKIP] 回填：无待回填收货单')
        return

    has_to_table = _table_exists(conn, TRANSFER_ORDER_TABLE)
    has_org_function = _table_exists(conn, ORG_FUNCTION_TABLE)
    if not has_to_table:
        print(f'  - [SKIP] 回填调拨来源：缺表 {TRANSFER_ORDER_TABLE}')
    if not has_org_function:
        print(f'  - [SKIP] 回填采购来源：缺表 {ORG_FUNCTION_TABLE}')

    filled_to = 0
    filled_po = 0
    for receipt_id, source_type, source_doc_id, purchase_org_id in rows:
        target = None
        if source_type == SOURCE_TRANSFER_ORDER and has_to_table \
                and source_doc_id is not None:
            row = conn.execute(
                'SELECT to_org_id FROM %s WHERE id = ?' % TRANSFER_ORDER_TABLE,
                [source_doc_id]).fetchone()
            target = row[0] if row else None
        elif source_type == SOURCE_PURCHASE_ORDER and has_org_function \
                and purchase_org_id is not None:
            if _has_inventory_function(conn, purchase_org_id):
                target = purchase_org_id
        if target is None:
            continue
        conn.execute(
            'UPDATE %s SET %s = ? WHERE id = ?' % (RECEIPT_TABLE, COLUMN),
            [target, receipt_id])
        if source_type == SOURCE_TRANSFER_ORDER:
            filled_to += 1
        else:
            filled_po += 1
    print(f'  - [BACKFILL] 回填 {filled_to + filled_po} 条（扫描 {len(rows)} 条：'
          f'调拨 {filled_to} / 采购 {filled_po}）')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v197] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v197] 开始: 收货库存组织维度')
        if _do_column(conn) and COLUMN in _columns(conn, RECEIPT_TABLE):
            _do_backfill(conn)
        conn.commit()
        print('[v197] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v197] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print('[v197 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        if not _table_exists(conn, RECEIPT_TABLE):
            print(f'[v197 verify] SKIP: 表 {RECEIPT_TABLE} 不存在')
            return True
        if COLUMN not in _columns(conn, RECEIPT_TABLE):
            print(f'[v197 verify] FAIL: 缺列 {RECEIPT_TABLE}.{COLUMN}')
            return False

        total = conn.execute(
            'SELECT COUNT(*) FROM %s WHERE %s IS NOT NULL'
            % (RECEIPT_TABLE, COLUMN)).fetchone()[0]
        print(f'  - 收货库存组织已写入 {total} 条')

        if not _table_exists(conn, TRANSFER_ORDER_TABLE):
            print(f'[v197 verify] SKIP 抽样: 缺表 {TRANSFER_ORDER_TABLE}')
        else:
            rows = conn.execute(
                "SELECT r.id, r.%s, t.to_org_id FROM %s r JOIN %s t "
                "ON t.id = r.source_doc_id WHERE r.source_doc_type = ? "
                "AND r.%s IS NOT NULL ORDER BY r.id LIMIT %d"
                % (COLUMN, RECEIPT_TABLE, TRANSFER_ORDER_TABLE,
                   COLUMN, VERIFY_SAMPLE_LIMIT),
                [SOURCE_TRANSFER_ORDER]).fetchall()
            for receipt_id, stored, expected in rows:
                if str(stored) != str(expected):
                    print(f'[v197 verify] FAIL: 收货单 {receipt_id} 库存组织 '
                          f'{stored} ≠ 调拨单 to_org_id {expected}')
                    ok = False
            print(f'  - 抽调查拨来源 {len(rows)} 条（上限 {VERIFY_SAMPLE_LIMIT}）')

        print('[v197 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v197 rollback] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if not _table_exists(conn, RECEIPT_TABLE):
            print(f'  - [SKIP] 表 {RECEIPT_TABLE} 不存在')
        elif COLUMN not in _columns(conn, RECEIPT_TABLE):
            print(f'  - [SKIP] 列 {RECEIPT_TABLE}.{COLUMN} 不存在')
        else:
            cur = conn.execute(
                'UPDATE %s SET %s = NULL WHERE %s IS NOT NULL'
                % (RECEIPT_TABLE, COLUMN, COLUMN))
            print(f'  - [CLEAR] 清空库存组织 {cur.rowcount} 条')
            print(f'  - [KEEP] 列 {RECEIPT_TABLE}.{COLUMN}'
                  '（SQLite 不支持 DROP COLUMN）')
        conn.commit()
        print('[v197 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v197 rollback] 失败: {e}')
        return False
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
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

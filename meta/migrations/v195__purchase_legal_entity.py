# -*- coding: utf-8 -*-
"""[v195 2026-11-02] 采购订单 TBD-10：采购法人只读快照

依据:
  docs/specs/tasks-transfer-order-object-model-2026-11-02.md TBD-10

范围:
  1. purchase_orders 增列 purchase_legal_entity_id（INTEGER，可空）；
  2. 回填：对 purchase_org_id 非空且快照为空的 PO，复用调拨守卫的
     组织上溯口径（`TransferOrderGuardService._resolve_org_legal_entity`）
     解析 `legal_entity` 职能组织 id 写入；解析失败留空（不阻断）。

幂等:
  列先查后用，重复执行打印 [SKIP]；回填只处理快照为空的行，
  重复执行回填条数为 0。

回滚:
  SQLite 不支持 DROP COLUMN ⇒ 列保留（[KEEP]），仅把快照值清 NULL。

前置:
  回填依赖 orgs / org_functions 两表；缺任一则 SKIP 回填（列照样创建）。
"""
import sqlite3
import sys
from pathlib import Path

# 允许以 `python meta/migrations/v195__purchase_legal_entity.py` 直接执行
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

MIGRATION_NAME = 'v195__purchase_legal_entity'

ORDER_TABLE = 'purchase_orders'
ORDER_ORG_COLUMN = 'purchase_org_id'
COLUMN = 'purchase_legal_entity_id'
ORG_TABLE = 'orgs'
ORG_FUNCTION_TABLE = 'org_functions'

#: verify 抽样上限
VERIFY_SAMPLE_LIMIT = 20


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection, table: str) -> set:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f'PRAGMA table_info({table})').fetchall()}


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


def _resolve_legal_entity(conn: sqlite3.Connection, org_id):
    """复用调拨守卫的组织上溯口径，不重写法人解析。"""
    from meta.services.transfer_order_guard_service import TransferOrderGuardService
    return TransferOrderGuardService(_ConnDS(conn))._resolve_org_legal_entity(org_id)


def _do_column(conn: sqlite3.Connection) -> bool:
    if not _table_exists(conn, ORDER_TABLE):
        print(f'  - [SKIP] 表 {ORDER_TABLE} 不存在')
        return False
    if COLUMN in _columns(conn, ORDER_TABLE):
        print(f'  - [SKIP] 列 {ORDER_TABLE}.{COLUMN} 已存在')
        return True
    conn.execute('ALTER TABLE %s ADD COLUMN %s INTEGER NULL' % (ORDER_TABLE, COLUMN))
    print(f'  - [CREATE] 列 {ORDER_TABLE}.{COLUMN}')
    return True


def _do_backfill(conn: sqlite3.Connection) -> None:
    missing = [t for t in (ORG_TABLE, ORG_FUNCTION_TABLE) if not _table_exists(conn, t)]
    if missing:
        print(f'  - [SKIP] 回填：缺依赖表 {missing}')
        return

    rows = conn.execute(
        'SELECT id, %s FROM %s WHERE %s IS NOT NULL AND %s IS NULL '
        'ORDER BY id' % (ORDER_ORG_COLUMN, ORDER_TABLE, ORDER_ORG_COLUMN, COLUMN)
    ).fetchall()
    if not rows:
        print('  - [SKIP] 回填：无待回填采购订单')
        return

    filled = 0
    unresolved = 0
    for order_id, org_id in rows:
        legal_entity_id = _resolve_legal_entity(conn, org_id)
        if legal_entity_id is None:
            unresolved += 1
            continue
        conn.execute(
            'UPDATE %s SET %s = ? WHERE id = ?' % (ORDER_TABLE, COLUMN),
            [legal_entity_id, order_id])
        filled += 1
    print(f'  - [BACKFILL] 回填 {filled} 条（扫描 {len(rows)} 条，'
          f'未解析 {unresolved} 条）')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v195] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v195] 开始: 采购订单法人快照')
        if _do_column(conn) and COLUMN in _columns(conn, ORDER_TABLE):
            _do_backfill(conn)
        conn.commit()
        print('[v195] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v195] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print('[v195 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        if not _table_exists(conn, ORDER_TABLE):
            print(f'[v195 verify] SKIP: 表 {ORDER_TABLE} 不存在')
            return True
        if COLUMN not in _columns(conn, ORDER_TABLE):
            print(f'[v195 verify] FAIL: 缺列 {ORDER_TABLE}.{COLUMN}')
            return False

        total = conn.execute(
            'SELECT COUNT(*) FROM %s WHERE %s IS NOT NULL' % (ORDER_TABLE, COLUMN)
        ).fetchone()[0]
        print(f'  - 快照已写入 {total} 条')

        missing = [t for t in (ORG_TABLE, ORG_FUNCTION_TABLE)
                   if not _table_exists(conn, t)]
        if missing:
            print(f'[v195 verify] SKIP 抽样: 缺依赖表 {missing}')
        else:
            rows = conn.execute(
                'SELECT id, %s, %s FROM %s WHERE %s IS NOT NULL '
                'ORDER BY id LIMIT %d'
                % (ORDER_ORG_COLUMN, COLUMN, ORDER_TABLE, COLUMN,
                   VERIFY_SAMPLE_LIMIT)).fetchall()
            for order_id, org_id, snapshot in rows:
                resolved = _resolve_legal_entity(conn, org_id)
                if resolved is None:
                    print(f'[v195 verify] FAIL: PO {order_id} 采购组织 {org_id} '
                          f'无法上溯法人（快照 {snapshot}）')
                    ok = False
                elif str(resolved) != str(snapshot):
                    print(f'[v195 verify] FAIL: PO {order_id} 快照 {snapshot} '
                          f'≠ 上溯结果 {resolved}')
                    ok = False
            print(f'  - 抽样校验 {len(rows)} 条（上限 {VERIFY_SAMPLE_LIMIT}）')

        print('[v195 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v195 rollback] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if not _table_exists(conn, ORDER_TABLE):
            print(f'  - [SKIP] 表 {ORDER_TABLE} 不存在')
        elif COLUMN not in _columns(conn, ORDER_TABLE):
            print(f'  - [SKIP] 列 {ORDER_TABLE}.{COLUMN} 不存在')
        else:
            cur = conn.execute(
                'UPDATE %s SET %s = NULL WHERE %s IS NOT NULL'
                % (ORDER_TABLE, COLUMN, COLUMN))
            print(f'  - [CLEAR] 清空快照 {cur.rowcount} 条')
            print(f'  - [KEEP] 列 {ORDER_TABLE}.{COLUMN}（SQLite 不支持 DROP COLUMN）')
        conn.commit()
        print('[v195 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v195 rollback] 失败: {e}')
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

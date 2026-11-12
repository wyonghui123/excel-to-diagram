# -*- coding: utf-8 -*-
"""[v198 2026-11-03] 库位组织归属 TBD-7

依据:
  docs/specs/spec-transfer-order-object-model-2026-11-02.md TBD-7
  （Oracle Locator 挂 Inventory Org / SAP Storage Location 挂 Plant 的口径）

范围:
  1. locations 增列 org_id（INTEGER，可空）；空值 = 共享 / 未归属，
     调拨与收货的库位归属校验遇空直接放行（兼容历史数据与共享场地）。
  2. 回填（仅处理 org_id IS NULL 的库位）：
     · 调拨单引用：from_location_id → 该 TO 的 from_org_id；
       to_location_id → to_org_id；
     · 收货单引用：deliver_to_location_id → 该收货的 inventory_org_id，
       空则回退 org_id；
     · 同一库位推断出多个不同组织 ⇒ 冲突，保持 NULL（不强行赋值）；
     · 缺表 / 缺列的分支跳过，不阻断。

幂等:
  列先查后用，重复执行打印 [SKIP]；回填只处理空列行，重复执行回填条数为 0。

回滚:
  SQLite 不支持 DROP COLUMN ⇒ 列保留（[KEEP]），仅把列值清 NULL（[CLEAR]）。

前置:
  回填依赖 transfer_orders / receipts；缺任一则该来源不参与推断（列照样创建）。
"""
import sqlite3
import sys
from pathlib import Path

# 允许以 `python meta/migrations/v198__location_org.py` 直接执行
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

MIGRATION_NAME = 'v198__location_org'

LOCATION_TABLE = 'locations'
COLUMN = 'org_id'
TRANSFER_ORDER_TABLE = 'transfer_orders'
RECEIPT_TABLE = 'receipts'

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


def _do_column(conn: sqlite3.Connection) -> bool:
    if not _table_exists(conn, LOCATION_TABLE):
        print(f'  - [SKIP] 表 {LOCATION_TABLE} 不存在')
        return False
    if COLUMN in _columns(conn, LOCATION_TABLE):
        print(f'  - [SKIP] 列 {LOCATION_TABLE}.{COLUMN} 已存在')
        return True
    conn.execute('ALTER TABLE %s ADD COLUMN %s INTEGER NULL'
                 % (LOCATION_TABLE, COLUMN))
    print(f'  - [CREATE] 列 {LOCATION_TABLE}.{COLUMN}')
    return True


def _infer_location_orgs(conn: sqlite3.Connection) -> dict:
    """从调拨单 / 收货单引用推断库位归属：`{location_id(str): {org_id(str)}}`。"""
    inferred = {}

    def add(location_id, org_id):
        if location_id is None or org_id is None:
            return
        inferred.setdefault(str(location_id), set()).add(str(org_id))

    to_cols = _columns(conn, TRANSFER_ORDER_TABLE)
    if not to_cols:
        print(f'  - [SKIP] 回填调拨来源：缺表 {TRANSFER_ORDER_TABLE}')
    elif {'from_location_id', 'from_org_id',
          'to_location_id', 'to_org_id'} - to_cols:
        print(f'  - [SKIP] 回填调拨来源：{TRANSFER_ORDER_TABLE} 缺列')
    else:
        for from_loc, from_org, to_loc, to_org in conn.execute(
                'SELECT from_location_id, from_org_id, to_location_id, to_org_id '
                'FROM %s' % TRANSFER_ORDER_TABLE).fetchall():
            add(from_loc, from_org)
            add(to_loc, to_org)

    receipt_cols = _columns(conn, RECEIPT_TABLE)
    inventory_col = 'inventory_org_id' if 'inventory_org_id' in receipt_cols \
        else 'NULL'
    if not receipt_cols:
        print(f'  - [SKIP] 回填收货来源：缺表 {RECEIPT_TABLE}')
    elif {'deliver_to_location_id', 'org_id'} - receipt_cols:
        print(f'  - [SKIP] 回填收货来源：{RECEIPT_TABLE} 缺列')
    else:
        for location_id, inventory_org_id, org_id in conn.execute(
                'SELECT deliver_to_location_id, %s, org_id FROM %s'
                % (inventory_col, RECEIPT_TABLE)).fetchall():
            add(location_id, inventory_org_id if inventory_org_id is not None
                else org_id)

    return inferred


def _do_backfill(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        'SELECT id FROM %s WHERE %s IS NULL ORDER BY id'
        % (LOCATION_TABLE, COLUMN)).fetchall()
    if not rows:
        print('  - [SKIP] 回填：无待回填库位')
        return

    inferred = _infer_location_orgs(conn)
    filled = 0
    conflict = 0
    no_reference = 0
    for (location_id,) in rows:
        org_ids = inferred.get(str(location_id))
        if not org_ids:
            no_reference += 1
            continue
        if len(org_ids) > 1:
            conflict += 1
            print(f'  - [CONFLICT] 库位 {location_id} 推断出多个组织'
                  f' {sorted(org_ids)}，保持 NULL')
            continue
        target = next(iter(org_ids))
        conn.execute(
            'UPDATE %s SET %s = ? WHERE id = ?' % (LOCATION_TABLE, COLUMN),
            [int(target) if target.isdigit() else target, location_id])
        filled += 1
    print(f'  - [BACKFILL] 回填 {filled} 条（扫描 {len(rows)} 条：'
          f'冲突留空 {conflict} / 无引用 {no_reference}）')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v198] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v198] 开始: 库位组织归属')
        if _do_column(conn) and COLUMN in _columns(conn, LOCATION_TABLE):
            _do_backfill(conn)
        conn.commit()
        print('[v198] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v198] 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print('[v198 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        if not _table_exists(conn, LOCATION_TABLE):
            print(f'[v198 verify] SKIP: 表 {LOCATION_TABLE} 不存在')
            return True
        if COLUMN not in _columns(conn, LOCATION_TABLE):
            print(f'[v198 verify] FAIL: 缺列 {LOCATION_TABLE}.{COLUMN}')
            return False

        total = conn.execute(
            'SELECT COUNT(*) FROM %s WHERE %s IS NOT NULL'
            % (LOCATION_TABLE, COLUMN)).fetchone()[0]
        print(f'  - 库位归属已写入 {total} 条')

        to_cols = _columns(conn, TRANSFER_ORDER_TABLE)
        if not to_cols:
            print(f'[v198 verify] SKIP 抽样: 缺表 {TRANSFER_ORDER_TABLE}')
        else:
            for field, org_field in (('from_location_id', 'from_org_id'),
                                     ('to_location_id', 'to_org_id')):
                if {field, org_field} - to_cols:
                    continue
                rows = conn.execute(
                    'SELECT t.id, t.%s, t.%s, l.%s FROM %s t JOIN %s l '
                    'ON l.id = t.%s WHERE t.%s IS NOT NULL '
                    'AND l.%s IS NOT NULL ORDER BY t.id LIMIT %d'
                    % (field, org_field, COLUMN, TRANSFER_ORDER_TABLE,
                       LOCATION_TABLE, field, field, COLUMN,
                       VERIFY_SAMPLE_LIMIT)).fetchall()
                for order_id, location_id, expected, stored in rows:
                    if str(stored) != str(expected):
                        print(f'[v198 verify] FAIL: 调拨单 {order_id} 库位 '
                              f'{location_id}（{field}）所属组织 {stored} '
                              f'≠ {org_field} {expected}')
                        ok = False
                print(f'  - 抽调查拨 {field} 引用 {len(rows)} 条'
                      f'（上限 {VERIFY_SAMPLE_LIMIT}）')

        print('[v198 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v198 rollback] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if not _table_exists(conn, LOCATION_TABLE):
            print(f'  - [SKIP] 表 {LOCATION_TABLE} 不存在')
        elif COLUMN not in _columns(conn, LOCATION_TABLE):
            print(f'  - [SKIP] 列 {LOCATION_TABLE}.{COLUMN} 不存在')
        else:
            cur = conn.execute(
                'UPDATE %s SET %s = NULL WHERE %s IS NOT NULL'
                % (LOCATION_TABLE, COLUMN, COLUMN))
            print(f'  - [CLEAR] 清空库位归属 {cur.rowcount} 条')
            print(f'  - [KEEP] 列 {LOCATION_TABLE}.{COLUMN}'
                  '（SQLite 不支持 DROP COLUMN）')
        conn.commit()
        print('[v198 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v198 rollback] 失败: {e}')
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

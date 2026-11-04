# -*- coding: utf-8 -*-
"""[v204 2026-11-04] 生产工单完工入库移动类型（P6c）

依据:
  docs/specs/p6c-serial-genealogy/spec.md
  docs/specs/p6c-serial-genealogy/tasks.md

范围:
  1. 向 inventory_transaction_types 插入 RCV_WO（category=receipt, direction=in）。
  2. 不改表结构、不加索引、不加权限 / 菜单 / 参数。

幂等:
  先按 code 查后插入；重复执行打印 [SKIP]。

回滚:
  删除 code='RCV_WO' 的移动类型行；若已被库存事务引用则不删（保留事实）。
"""
import sqlite3
from datetime import datetime
from pathlib import Path

MIGRATION_NAME = 'v204__inventory_work_order_receipt_type'

TYPES_TABLE = 'inventory_transaction_types'
TX_TABLE = 'inventory_transactions'

RCV_WO = ('RCV_WO', '生产工单完工入库', 'receipt', 'in', 1, 60,
          '生产工单来源收货过账形成的入库')


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _do_upgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TYPES_TABLE):
        print('  - [SKIP] inventory_transaction_types 不存在')
        return
    row = conn.execute(
        'SELECT id FROM %s WHERE code = ?' % TYPES_TABLE, (RCV_WO[0],)
    ).fetchone()
    if row:
        print('  - [SKIP] 移动类型 %s 已存在' % RCV_WO[0])
        return
    conn.execute(
        'INSERT INTO %s (code, name, category, direction, affects_on_hand, '
        'status, sort_order, description, created_at) '
        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)' % TYPES_TABLE,
        (RCV_WO[0], RCV_WO[1], RCV_WO[2], RCV_WO[3], RCV_WO[4], 'active',
         RCV_WO[5], RCV_WO[6], datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
    )
    print('  - [ADD] 移动类型 %s（%s）' % (RCV_WO[0], RCV_WO[1]))


def _do_downgrade(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TYPES_TABLE):
        return
    row = conn.execute(
        'SELECT id FROM %s WHERE code = ?' % TYPES_TABLE, (RCV_WO[0],)
    ).fetchone()
    if not row:
        print('  - [SKIP] 移动类型 %s 不存在' % RCV_WO[0])
        return
    if _table_exists(conn, TX_TABLE):
        used = conn.execute(
            'SELECT 1 FROM %s WHERE transaction_type_id = ? LIMIT 1'
            % TX_TABLE, (row[0],)
        ).fetchone()
        if used:
            print('  - [SKIP] %s 已被库存事务引用，保留' % RCV_WO[0])
            return
    conn.execute('DELETE FROM %s WHERE id = ?' % TYPES_TABLE, (row[0],))
    print('  - [DEL] 移动类型 %s' % RCV_WO[0])


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print('[v204] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v204] 开始: 生产工单完工入库移动类型（P6c）')
        _do_upgrade(conn)
        conn.commit()
        print('[v204] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v204] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v204 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if not _table_exists(conn, TYPES_TABLE):
            print('[v204 verify] FAIL: 缺表 %s' % TYPES_TABLE)
            return False
        row = conn.execute(
            'SELECT category, direction, status FROM %s WHERE code = ?'
            % TYPES_TABLE, (RCV_WO[0],)
        ).fetchone()
        if not row:
            print('[v204 verify] FAIL: 缺移动类型 %s' % RCV_WO[0])
            return False
        if row[0] != 'receipt' or row[1] != 'in' or row[2] != 'active':
            print('[v204 verify] FAIL: %s 字段不符 %s' % (RCV_WO[0], row))
            return False
        print('[v204 verify] PASS')
        return True
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1:
        print(migrate(Path(sys.argv[1]), skip_backup=True))
        print(verify(Path(sys.argv[1])))

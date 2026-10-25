# -*- coding: utf-8 -*-
"""[v126] 销售订单波次 1 W1-C：往来单位地址桥接

依据:
  docs/superpowers/specs/2026-10-25-sales-order-wave1-detailed-plan.md
    §5.2 对象字段 / §5.5 不变量 / §5.6 迁移与验收

背景:
  `address` 是纯地址库（只被引用、不承载用途 / 角色），「某往来单位的收货地址」
  由 `party_addresses` 承载「地址 × 往来单位 × 角色」。订单收货 / 收票地址默认值
  从本表的 `is_default=1` 行解析（见 meta/services/party_address_service.py）。

本迁移做两件事:
  1. 确认表已由 sync_schema 建好（不重复建表，避免与 YAML 双源），补齐四条索引
  2. 若地址库已有启用地址，为现有客户 / 供应商各配一条 ship_to 默认地址
     （无地址数据则跳过，不阻断迁移）

幂等:
  索引 CREATE ... IF NOT EXISTS；种子 INSERT OR IGNORE。
  重复执行只输出 [SKIP]。

回滚:
  只删本迁移补的索引；表、种子数据保留（对象由 YAML 声明）。
"""
import sqlite3
from pathlib import Path

TABLE = 'party_addresses'

UNIQUE_INDEX = 'uidx_party_address_party_addr_role'
DEFAULT_INDEX = 'uidx_party_address_default'
ADDRESS_INDEX = 'idx_party_address_address'
STATUS_INDEX = 'idx_party_address_status'

#: 必填列（NOT NULL）
REQUIRED_COLUMNS = ('party_id', 'address_id', 'role', 'is_default')
#: 可空列
NULLABLE_COLUMNS = ('description',)

_INDEX_DDL = {
    UNIQUE_INDEX: (
        f'CREATE UNIQUE INDEX IF NOT EXISTS {UNIQUE_INDEX} '
        f'ON {TABLE} (party_id, address_id, role)'),
    DEFAULT_INDEX: (
        f'CREATE UNIQUE INDEX IF NOT EXISTS {DEFAULT_INDEX} '
        f"ON {TABLE} (party_id, role) "
        f"WHERE is_default = 1 AND status = 'active'"),
    ADDRESS_INDEX: (
        f'CREATE INDEX IF NOT EXISTS {ADDRESS_INDEX} ON {TABLE} (address_id)'),
    STATUS_INDEX: (
        f'CREATE INDEX IF NOT EXISTS {STATUS_INDEX} ON {TABLE} (status)'),
}


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _index_sql(conn: sqlite3.Connection, name: str):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone()
    return row[0] if row else None


def _duplicate_triples(conn: sqlite3.Connection):
    return conn.execute(
        f'SELECT party_id, address_id, role, COUNT(*) AS n '
        f'FROM {TABLE} GROUP BY party_id, address_id, role '
        f'HAVING n > 1').fetchall()


def _duplicate_defaults(conn: sqlite3.Connection):
    return conn.execute(
        f'SELECT party_id, role, COUNT(*) AS n FROM {TABLE} '
        f"WHERE is_default = 1 AND status = 'active' "
        f'GROUP BY party_id, role HAVING n > 1').fetchall()


def _seed_default_ship_to(conn: sqlite3.Connection) -> int:
    """为现有客户 / 供应商各配一条 ship_to 默认地址；无地址数据则跳过。"""
    if not _table_exists(conn, 'addresses'):
        print('  - [SKIP] 地址库表不存在，跳过种子')
        return 0
    row = conn.execute(
        "SELECT id FROM addresses WHERE status = 'active' ORDER BY id LIMIT 1"
    ).fetchone()
    if not row:
        print('  - [SKIP] 地址库无启用地址，跳过种子')
        return 0
    address_id = row[0]

    parties = conn.execute(
        'SELECT pr.party2_id FROM customer_accounts ca '
        'JOIN party_relations pr ON pr.id = ca.relation_id'
    ).fetchall()
    if _table_exists(conn, 'vendor_accounts'):
        parties += conn.execute(
            'SELECT pr.party2_id FROM vendor_accounts va '
            'JOIN party_relations pr ON pr.id = va.relation_id'
        ).fetchall()

    inserted = 0
    seen = set()
    for (party_id,) in parties:
        if party_id in seen:
            continue
        seen.add(party_id)
        cur = conn.execute(
            f'INSERT OR IGNORE INTO {TABLE} '
            '(party_id, address_id, role, is_default, status, created_at, updated_at) '
            "VALUES (?, ?, 'ship_to', 1, 'active', datetime('now'), datetime('now'))",
            (party_id, address_id))
        inserted += cur.rowcount
    print(f'  - [SEED] ship_to 默认地址: 新增 {inserted} 条（地址 {address_id}）')
    return inserted


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v126] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v126] 开始: 往来单位地址表索引与种子')
        if not _table_exists(conn, TABLE):
            print(f'[v126] 表 {TABLE} 不存在：请先执行 '
                  f'`python -m meta.tools.sync_schema --source sqlite '
                  f'--local {db_path} --execute` 建表')
            return False

        if _duplicate_triples(conn):
            print(f'[v126] 发现重复 (往来单位, 地址, 角色) 组合，无法建唯一索引')
            return False
        if _duplicate_defaults(conn):
            print('[v126] 发现同角色多条启用默认地址，无法建部分唯一索引')
            return False

        for name, ddl in _INDEX_DDL.items():
            if _index_sql(conn, name):
                print(f'  - [SKIP] 索引 {name} 已存在')
            else:
                conn.execute(ddl)
                print(f'  - [NEW] 索引 {name}')

        _seed_default_ship_to(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v126] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言表结构、四条索引口径与「同角色至多一条默认」齐备。"""
    if not db_path.exists():
        print('[v126 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, TABLE):
            print(f'[v126 verify] FAIL: 表 {TABLE} 不存在')
            return False

        info = {row[1]: row for row in conn.execute(f'PRAGMA table_info({TABLE})')}
        for column in REQUIRED_COLUMNS:
            if column not in info:
                print(f'[v126 verify] FAIL: 缺列 {TABLE}.{column}')
                return False
            if info[column][3] != 1:
                print(f'[v126 verify] FAIL: {TABLE}.{column} 应为 NOT NULL')
                return False
        for column in NULLABLE_COLUMNS:
            if column in info and info[column][3] != 0:
                print(f'[v126 verify] FAIL: {TABLE}.{column} 应可空')
                return False

        if 'status' not in info:
            print(f'[v126 verify] FAIL: 缺列 {TABLE}.status')
            return False
        if str(info['status'][4]).strip("'\"") != 'active':
            print(f'[v126 verify] FAIL: status 默认值异常 {info["status"][4]!r}')
            return False

        unique_sql = _index_sql(conn, UNIQUE_INDEX)
        if not unique_sql or 'UNIQUE' not in unique_sql.upper():
            print(f'[v126 verify] FAIL: 缺唯一索引 {UNIQUE_INDEX}')
            return False
        default_sql = _index_sql(conn, DEFAULT_INDEX)
        if not default_sql or 'UNIQUE' not in default_sql.upper() \
                or 'IS_DEFAULT' not in default_sql.upper():
            print(f'[v126 verify] FAIL: 缺部分唯一索引 {DEFAULT_INDEX}')
            return False
        if not _index_sql(conn, ADDRESS_INDEX) or not _index_sql(conn, STATUS_INDEX):
            print('[v126 verify] FAIL: 缺普通索引')
            return False

        if _duplicate_triples(conn) or _duplicate_defaults(conn):
            print('[v126 verify] FAIL: 存在重复组合或同角色多条默认地址')
            return False

        print(f'[v126 verify] OK: {TABLE} 结构就位，索引与默认唯一性齐备')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """只删本迁移补的索引；表与数据由 YAML 管理、保留。"""
    if not db_path.exists():
        print(f'[v126] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        for name in _INDEX_DDL:
            if _index_sql(conn, name):
                conn.execute(f'DROP INDEX {name}')
                print(f'  - [DROP] 索引 {name}')
            else:
                print(f'  - [SKIP] 索引 {name} 不存在')
        print(f'  - [KEEP] 表 {TABLE} 与数据保留 (由 YAML 声明)')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v126] rollback 失败: {e}')
        raise
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    import sys
    from meta.core.db_path import get_meta_db_path

    _args = [a for a in sys.argv[1:] if a != '--rollback']
    _db = Path(_args[0]) if _args else Path(get_meta_db_path())
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v126] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v126] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v126] verify: {"PASS" if _v else "FAIL"}')

# -*- coding: utf-8 -*-
"""[v164] 履约单 + 履约路由规则（含 4 条默认路由种子）

依据:
  docs/superpowers/specs/2026-10-29-so-wave3/spec.md §10.18.3 / §10.18.6
  docs/superpowers/specs/2026-10-29-so-wave3/tasks.md T4.5

设计:
  · 两张表由 fulfillment_order.yaml / fulfillment_routing_rule.yaml 声明，
    `sync_schema` 生成；本迁移只做「兜底 CREATE + 兜底索引 + 种子」。
  · `fulfillment_orders` 是业务锚（fulfillment_no / site_id / fulfillment_type），
    **不写 workflow_runs**（执行实例由 4b 编排批次驱动，§10.18.6）。
  · `fulfillment_routing_rules` 先 4 条默认规则（不做通用规则引擎）：
      priority 10  procurement_type='stock'   → wf-fulfill-stock
      priority 20  procurement_type='make'    → wf-fulfill-mto
      priority 30  procurement_type='service' → wf-fulfill-service
      priority 100 全通配（兜底）              → wf-fulfilled-mixed
  · `site_id` 为整数列，不加外键 relation（站点对象批次 5 落地）。

幂等:
  表 / 索引先查后用；种子按 (workflow_key, priority) 先查后用；重复执行打印 [SKIP]。

回滚:
  删索引 + 删表（先子表后父表）；种子随表一并删除。
"""
import sqlite3
import sys
from pathlib import Path

ORDERS_TABLE = 'fulfillment_orders'
RULES_TABLE = 'fulfillment_routing_rules'

ORDERS_DDL = """
CREATE TABLE IF NOT EXISTS fulfillment_orders (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    fulfillment_no       TEXT NOT NULL,
    order_id             INTEGER NOT NULL,
    customer_account_id  INTEGER NULL,
    site_id              INTEGER NULL,
    fulfillment_type     TEXT NOT NULL DEFAULT 'delivery',
    status               TEXT NOT NULL DEFAULT 'draft',
    workflow_run_id      INTEGER NULL,
    planned_date         TEXT NULL,
    notes                TEXT NULL,
    created_at           TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at           TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

RULES_DDL = """
CREATE TABLE IF NOT EXISTS fulfillment_routing_rules (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    priority          INTEGER NOT NULL DEFAULT 100,
    item_type         TEXT NULL,
    procurement_type  TEXT NULL,
    delivery_mode     TEXT NULL,
    site_id           INTEGER NULL,
    workflow_key      TEXT NOT NULL,
    is_default        INTEGER NOT NULL DEFAULT 0,
    enabled           INTEGER NOT NULL DEFAULT 1,
    remark            TEXT NULL,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at        TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

INDEXES = (
    ('uq_fulfillment_no',
     f'CREATE UNIQUE INDEX IF NOT EXISTS uq_fulfillment_no '
     f'ON {ORDERS_TABLE}(fulfillment_no)'),
    ('idx_fulfillment_order_order',
     f'CREATE INDEX IF NOT EXISTS idx_fulfillment_order_order '
     f'ON {ORDERS_TABLE}(order_id)'),
    ('idx_fulfillment_order_status',
     f'CREATE INDEX IF NOT EXISTS idx_fulfillment_order_status '
     f'ON {ORDERS_TABLE}(status)'),
    ('idx_fulfillment_routing_lookup',
     f'CREATE INDEX IF NOT EXISTS idx_fulfillment_routing_lookup '
     f'ON {RULES_TABLE}(enabled, priority)'),
    ('idx_fulfillment_routing_workflow',
     f'CREATE INDEX IF NOT EXISTS idx_fulfillment_routing_workflow '
     f'ON {RULES_TABLE}(workflow_key)'),
)

#: 4 条默认路由（priority, item_type, procurement_type, delivery_mode,
#: site_id, workflow_key, is_default, remark）
DEFAULT_RULES = (
    (10, None, 'stock', None, None, 'wf-fulfill-stock', 1,
     '库存直发：pick → ship → deliver'),
    (20, None, 'make', None, None, 'wf-fulfill-mto', 1,
     '按单生产：produce → pick → ship → deliver'),
    (30, None, 'service', None, None, 'wf-fulfill-service', 1,
     '纯服务：dispatch → onsite → confirm → close'),
    (100, None, None, None, None, 'wf-fulfilled-mixed', 1,
     '兜底：实物 + 上门（ship → deliver → install → accept）'),
)

TABLES = (
    (ORDERS_TABLE, ORDERS_DDL),
    (RULES_TABLE, RULES_DDL),
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


def _seed_default_rules(conn: sqlite3.Connection) -> None:
    for (priority, item_type, procurement_type, delivery_mode, site_id,
         workflow_key, is_default, remark) in DEFAULT_RULES:
        exists = conn.execute(
            f'SELECT id FROM {RULES_TABLE} WHERE workflow_key = ? AND priority = ?',
            (workflow_key, priority)).fetchone()
        if exists:
            print(f'  - [SKIP] 种子规则 {workflow_key}（priority={priority}）已存在')
            continue
        conn.execute(
            f'INSERT INTO {RULES_TABLE} '
            '(priority, item_type, procurement_type, delivery_mode, site_id, '
            'workflow_key, is_default, enabled, remark) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)',
            (priority, item_type, procurement_type, delivery_mode, site_id,
             workflow_key, is_default, remark))
        print(f'  - [SEED] 种子规则 {workflow_key}（priority={priority}）')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v164] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v164] 开始: 履约单 + 履约路由规则')

        for name, ddl in TABLES:
            if _table_exists(conn, name):
                print(f'  - [SKIP] 表 {name} 已存在')
            else:
                conn.execute(ddl)
                print(f'  - [CREATE] 表 {name}')

        for name, sql in INDEXES:
            if _index_exists(conn, name):
                print(f'  - [SKIP] 索引 {name} 已存在')
            else:
                conn.execute(sql)
                print(f'  - [ADD] 索引 {name}')

        _seed_default_rules(conn)

        conn.commit()
        print('[v164] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v164] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v164 verify] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        required_columns = {
            ORDERS_TABLE: (
                'fulfillment_no', 'order_id', 'customer_account_id', 'site_id',
                'fulfillment_type', 'status', 'workflow_run_id', 'planned_date',
                'notes'),
            RULES_TABLE: (
                'priority', 'item_type', 'procurement_type', 'delivery_mode',
                'site_id', 'workflow_key', 'is_default', 'enabled', 'remark'),
        }

        for table, columns in required_columns.items():
            if not _table_exists(conn, table):
                print('[v164 verify] FAIL: 缺表 %s' % table)
                ok = False
                continue
            have = _columns(conn, table)
            for column in columns:
                if column not in have:
                    print('[v164 verify] FAIL: 缺列 %s.%s' % (table, column))
                    ok = False

        for name, _sql in INDEXES:
            if not _index_exists(conn, name):
                print('[v164 verify] FAIL: 缺索引 %s' % name)
                ok = False

        if _table_exists(conn, RULES_TABLE):
            for _priority, _item_type, _procurement_type, _delivery_mode, \
                    _site_id, workflow_key, _is_default, _remark in DEFAULT_RULES:
                row = conn.execute(
                    f'SELECT id FROM {RULES_TABLE} WHERE workflow_key = ?',
                    (workflow_key,)).fetchone()
                if not row:
                    print('[v164 verify] FAIL: 缺种子规则 %s' % workflow_key)
                    ok = False

        print('[v164 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v164 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v164 rollback] 开始回滚')
        for name, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX {name}')
                print(f'  - [DROP] 索引 {name}')
            else:
                print(f'  - [SKIP] 索引 {name} 不存在')

        for name, _ddl in reversed(TABLES):
            if _table_exists(conn, name):
                conn.execute(f'DROP TABLE {name}')
                print(f'  - [DROP] 表 {name}')
            else:
                print(f'  - [SKIP] 表 {name} 不存在')

        conn.commit()
        print('[v164 rollback] 完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v164 rollback] 失败: %s' % e)
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

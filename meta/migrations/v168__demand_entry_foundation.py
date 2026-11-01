# -*- coding: utf-8 -*-
"""[v168 2026-10-31] 统一需求入口地基（M1）

依据:
  docs/specs/spec-unified-demand-execution-milestone-2026-10-31.md §2 M1
  docs/specs/spec-procurement-task-object-model-2026-10-31.md §3.2 / T1 / T-D13 / T-D13a
  docs/specs/spec-shared-service-center-object-model-2026-10-31.md §3 / S1 / S2 / S4 / S-D5

设计:
  · 五张表由 `service_catalog_item.yaml` / `service_request.yaml` /
    `service_request_line.yaml` / `requisition.yaml` / `requisition_line.yaml`
    声明、`sync_schema` 生成；本迁移只做「断言 + 兜底 CREATE + 补索引 + 权限」
  · 审批不新建表：复用 tasks(type=approval)（S-D5）；本迁移只校验 tasks.type 可用
  · 权限码双段式 {bo}:{bo}_{action}，与既有 permissions 表一致
  · 不写菜单：M1 只交付数据地基，导航在后续波次补齐

幂等:
  表 / 索引先查后用；重复执行打印 [SKIP]，DB 终态一致。

回滚:
  删索引 + 删表（先子表后头表）。**保留** permissions 行 —— 可能已被角色授予。
"""
import sqlite3
import sys
from pathlib import Path

CATALOG_TABLE = 'service_catalog_items'
REQUEST_TABLE = 'service_requests'
REQUEST_LINE_TABLE = 'service_request_lines'
REQUISITION_TABLE = 'requisitions'
REQUISITION_LINE_TABLE = 'requisition_lines'

CATALOG_DDL = """
CREATE TABLE IF NOT EXISTS service_catalog_items (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    code                    VARCHAR(200) NOT NULL UNIQUE,
    name                    VARCHAR(200) NOT NULL,
    status                  VARCHAR(200) NOT NULL DEFAULT 'draft',
    default_priority        VARCHAR(200) NOT NULL DEFAULT 'medium',
    default_provider_org_id INTEGER NULL,
    requires_approval       INTEGER NOT NULL DEFAULT 0,
    approval_policy         TEXT NULL,
    description             TEXT NULL,
    created_at              DATETIME,
    updated_at              DATETIME,
    FOREIGN KEY (default_provider_org_id) REFERENCES orgs(id)
)
"""

REQUEST_DDL = """
CREATE TABLE IF NOT EXISTS service_requests (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    request_no         VARCHAR(200) UNIQUE,
    title              VARCHAR(200) NOT NULL,
    status             VARCHAR(200) NOT NULL DEFAULT 'draft',
    priority           VARCHAR(200) NOT NULL DEFAULT 'medium',
    requester_org_id   INTEGER NOT NULL,
    provider_org_id    INTEGER NOT NULL,
    requester_party_id INTEGER NULL,
    need_date          DATETIME NULL,
    description        TEXT NULL,
    closed_at          DATETIME NULL,
    created_at         DATETIME,
    updated_at         DATETIME,
    FOREIGN KEY (requester_org_id) REFERENCES orgs(id),
    FOREIGN KEY (provider_org_id) REFERENCES orgs(id),
    -- party_internal 是视图，SQLite 不允许 FK 指向视图；物理列存 parties.id
    FOREIGN KEY (requester_party_id) REFERENCES parties(id)
)
"""

REQUEST_LINE_DDL = """
CREATE TABLE IF NOT EXISTS service_request_lines (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id              INTEGER NOT NULL,
    line_no                 VARCHAR(200) NOT NULL,
    line_type               VARCHAR(200) NOT NULL DEFAULT 'service',
    catalog_item_id         INTEGER NULL,
    item_id                 INTEGER NULL,
    description             VARCHAR(200) NULL,
    qty                     REAL NULL,
    uom_id                  INTEGER NULL,
    need_date               DATETIME NULL,
    deliver_to_location_id  INTEGER NULL,
    status                  VARCHAR(200) NOT NULL DEFAULT 'open',
    created_at              DATETIME,
    updated_at              DATETIME,
    FOREIGN KEY (request_id) REFERENCES service_requests(id),
    FOREIGN KEY (catalog_item_id) REFERENCES service_catalog_items(id),
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (uom_id) REFERENCES uoms(id),
    FOREIGN KEY (deliver_to_location_id) REFERENCES locations(id)
)
"""

REQUISITION_DDL = """
CREATE TABLE IF NOT EXISTS requisitions (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    requisition_no          VARCHAR(200) UNIQUE,
    status                  VARCHAR(200) NOT NULL DEFAULT 'draft',
    priority                VARCHAR(200) NOT NULL DEFAULT 'medium',
    requester_org_id        INTEGER NOT NULL,
    deliver_to_org_id       INTEGER NOT NULL,
    deliver_to_location_id  INTEGER NULL,
    need_date               DATETIME NOT NULL,
    requested_by_party_id   INTEGER NULL,
    description             TEXT NULL,
    closed_at               DATETIME NULL,
    created_at              DATETIME,
    updated_at              DATETIME,
    FOREIGN KEY (requester_org_id) REFERENCES orgs(id),
    FOREIGN KEY (deliver_to_org_id) REFERENCES orgs(id),
    FOREIGN KEY (deliver_to_location_id) REFERENCES locations(id),
    -- party_internal 是视图，SQLite 不允许 FK 指向视图；物理列存 parties.id
    FOREIGN KEY (requested_by_party_id) REFERENCES parties(id)
)
"""

REQUISITION_LINE_DDL = """
CREATE TABLE IF NOT EXISTS requisition_lines (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    requisition_id           INTEGER NOT NULL,
    line_no                  VARCHAR(200) NOT NULL,
    line_type                VARCHAR(200) NOT NULL DEFAULT 'goods',
    item_id                  INTEGER NULL,
    description              VARCHAR(200) NULL,
    qty                      REAL NOT NULL,
    uom_id                   INTEGER NULL,
    need_date                DATETIME NULL,
    deliver_to_location_id   INTEGER NULL,
    requested_source_org_id  INTEGER NULL,
    resolved_source_org_id   INTEGER NULL,
    status                   VARCHAR(200) NOT NULL DEFAULT 'open',
    created_at               DATETIME,
    updated_at               DATETIME,
    FOREIGN KEY (requisition_id) REFERENCES requisitions(id),
    FOREIGN KEY (item_id) REFERENCES items(id),
    FOREIGN KEY (uom_id) REFERENCES uoms(id),
    FOREIGN KEY (deliver_to_location_id) REFERENCES locations(id),
    FOREIGN KEY (requested_source_org_id) REFERENCES orgs(id),
    FOREIGN KEY (resolved_source_org_id) REFERENCES orgs(id)
)
"""

TABLES = (
    (CATALOG_TABLE, CATALOG_DDL),
    (REQUEST_TABLE, REQUEST_DDL),
    (REQUEST_LINE_TABLE, REQUEST_LINE_DDL),
    (REQUISITION_TABLE, REQUISITION_DDL),
    (REQUISITION_LINE_TABLE, REQUISITION_LINE_DDL),
)

INDEXES = (
    ('uidx_service_catalog_item_code',
     f'CREATE UNIQUE INDEX IF NOT EXISTS uidx_service_catalog_item_code '
     f'ON {CATALOG_TABLE}(code)'),
    ('idx_service_catalog_item_status',
     f'CREATE INDEX IF NOT EXISTS idx_service_catalog_item_status '
     f'ON {CATALOG_TABLE}(status)'),
    ('idx_service_catalog_item_provider',
     f'CREATE INDEX IF NOT EXISTS idx_service_catalog_item_provider '
     f'ON {CATALOG_TABLE}(default_provider_org_id)'),
    ('uidx_service_request_no',
     f'CREATE UNIQUE INDEX IF NOT EXISTS uidx_service_request_no '
     f'ON {REQUEST_TABLE}(request_no)'),
    ('idx_service_request_status_requester',
     f'CREATE INDEX IF NOT EXISTS idx_service_request_status_requester '
     f'ON {REQUEST_TABLE}(status, requester_org_id)'),
    ('idx_service_request_provider_status',
     f'CREATE INDEX IF NOT EXISTS idx_service_request_provider_status '
     f'ON {REQUEST_TABLE}(provider_org_id, status)'),
    ('idx_service_request_need_date',
     f'CREATE INDEX IF NOT EXISTS idx_service_request_need_date '
     f'ON {REQUEST_TABLE}(need_date)'),
    ('uidx_service_request_line_no',
     f'CREATE UNIQUE INDEX IF NOT EXISTS uidx_service_request_line_no '
     f'ON {REQUEST_LINE_TABLE}(request_id, line_no)'),
    ('idx_service_request_line_catalog',
     f'CREATE INDEX IF NOT EXISTS idx_service_request_line_catalog '
     f'ON {REQUEST_LINE_TABLE}(catalog_item_id)'),
    ('idx_service_request_line_item',
     f'CREATE INDEX IF NOT EXISTS idx_service_request_line_item '
     f'ON {REQUEST_LINE_TABLE}(item_id)'),
    ('idx_service_request_line_request_status',
     f'CREATE INDEX IF NOT EXISTS idx_service_request_line_request_status '
     f'ON {REQUEST_LINE_TABLE}(request_id, status)'),
    ('uidx_requisition_no',
     f'CREATE UNIQUE INDEX IF NOT EXISTS uidx_requisition_no '
     f'ON {REQUISITION_TABLE}(requisition_no)'),
    ('idx_requisition_status_requester',
     f'CREATE INDEX IF NOT EXISTS idx_requisition_status_requester '
     f'ON {REQUISITION_TABLE}(status, requester_org_id)'),
    ('idx_requisition_deliver_need_date',
     f'CREATE INDEX IF NOT EXISTS idx_requisition_deliver_need_date '
     f'ON {REQUISITION_TABLE}(deliver_to_org_id, need_date)'),
    ('uidx_requisition_line_no',
     f'CREATE UNIQUE INDEX IF NOT EXISTS uidx_requisition_line_no '
     f'ON {REQUISITION_LINE_TABLE}(requisition_id, line_no)'),
    ('idx_requisition_line_item',
     f'CREATE INDEX IF NOT EXISTS idx_requisition_line_item '
     f'ON {REQUISITION_LINE_TABLE}(item_id)'),
    ('idx_requisition_line_requisition_status',
     f'CREATE INDEX IF NOT EXISTS idx_requisition_line_requisition_status '
     f'ON {REQUISITION_LINE_TABLE}(requisition_id, status)'),
    ('idx_requisition_line_requested_source',
     f'CREATE INDEX IF NOT EXISTS idx_requisition_line_requested_source '
     f'ON {REQUISITION_LINE_TABLE}(requested_source_org_id)'),
    ('idx_requisition_line_resolved_source',
     f'CREATE INDEX IF NOT EXISTS idx_requisition_line_resolved_source '
     f'ON {REQUISITION_LINE_TABLE}(resolved_source_org_id)'),
)

# 权限声明: (code, name, resource_type, action)
PERMISSIONS = (
    ('service_catalog_item:service_catalog_item_create', '新建服务目录项',
     'service_catalog_item', 'create'),
    ('service_catalog_item:service_catalog_item_read', '查看服务目录项',
     'service_catalog_item', 'read'),
    ('service_catalog_item:service_catalog_item_update', '修改服务目录项',
     'service_catalog_item', 'update'),
    ('service_catalog_item:service_catalog_item_delete', '删除服务目录项',
     'service_catalog_item', 'delete'),
    ('service_catalog_item:service_catalog_item_list', '查询服务目录项列表',
     'service_catalog_item', 'list'),
    ('service_request:service_request_create', '新建服务请求',
     'service_request', 'create'),
    ('service_request:service_request_read', '查看服务请求',
     'service_request', 'read'),
    ('service_request:service_request_update', '修改服务请求',
     'service_request', 'update'),
    ('service_request:service_request_delete', '删除服务请求',
     'service_request', 'delete'),
    ('service_request:service_request_list', '查询服务请求列表',
     'service_request', 'list'),
    ('service_request:service_request_approve', '审批服务请求',
     'service_request', 'approve'),
    ('requisition:requisition_create', '新建采购申请',
     'requisition', 'create'),
    ('requisition:requisition_read', '查看采购申请',
     'requisition', 'read'),
    ('requisition:requisition_update', '修改采购申请',
     'requisition', 'update'),
    ('requisition:requisition_delete', '删除采购申请',
     'requisition', 'delete'),
    ('requisition:requisition_list', '查询采购申请列表',
     'requisition', 'list'),
    ('requisition:requisition_approve', '审批采购申请',
     'requisition', 'approve'),
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


def _do_indexes(conn: sqlite3.Connection) -> None:
    for name, sql in INDEXES:
        if _index_exists(conn, name):
            print(f'  - [SKIP] 索引 {name} 已存在')
        else:
            conn.execute(sql)
            print(f'  - [ADD] 索引 {name}')


def _do_permissions(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'permissions'):
        print('  - permissions 表不存在, 跳过权限写入')
        return
    created = 0
    for code, name, resource_type, action in PERMISSIONS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO permissions (code, name, resource_type, action) "
            "VALUES (?, ?, ?, ?)",
            (code, name, resource_type, action),
        )
        if cur.rowcount:
            created += 1
            print(f'  - [NEW] 权限 {code} ({name})')
    print(f'  - [SUMMARY] permissions: +{created} 新增')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v168] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v168] 开始: 统一需求入口地基（M1）')
        _do_tables(conn)
        _do_indexes(conn)
        _do_permissions(conn)
        conn.commit()
        print('[v168] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v168] 失败: %s' % e)
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v168 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        ok = True
        required = {
            CATALOG_TABLE: ('code', 'name', 'status', 'default_priority',
                            'default_provider_org_id', 'requires_approval',
                            'approval_policy'),
            REQUEST_TABLE: ('request_no', 'title', 'status', 'priority',
                            'requester_org_id', 'provider_org_id',
                            'requester_party_id', 'need_date'),
            REQUEST_LINE_TABLE: ('request_id', 'line_no', 'line_type',
                                 'catalog_item_id', 'item_id', 'qty', 'uom_id',
                                 'status'),
            REQUISITION_TABLE: ('requisition_no', 'status', 'priority',
                                'requester_org_id', 'deliver_to_org_id',
                                'deliver_to_location_id', 'need_date'),
            REQUISITION_LINE_TABLE: ('requisition_id', 'line_no', 'line_type',
                                     'item_id', 'qty', 'uom_id',
                                     'requested_source_org_id',
                                     'resolved_source_org_id', 'status'),
        }
        for table, cols in required.items():
            if not _table_exists(conn, table):
                print(f'[v168 verify] FAIL: 缺表 {table}')
                ok = False
                continue
            have = _columns(conn, table)
            for col in cols:
                if col not in have:
                    print(f'[v168 verify] FAIL: 缺列 {table}.{col}')
                    ok = False

        for name, _sql in INDEXES:
            if not _index_exists(conn, name):
                print(f'[v168 verify] FAIL: 缺索引 {name}')
                ok = False

        if _table_exists(conn, 'permissions'):
            for code, _name, _rtype, _action in PERMISSIONS:
                if not conn.execute(
                        'SELECT 1 FROM permissions WHERE code=?', (code,)
                ).fetchone():
                    print(f'[v168 verify] FAIL: 缺权限 {code}')
                    ok = False

        # S-D5：审批复用 tasks(type=approval)；表存在时断言 type 列可用
        if _table_exists(conn, 'tasks'):
            if 'type' not in _columns(conn, 'tasks'):
                print('[v168 verify] FAIL: tasks 缺 type 列，无法承载 approval')
                ok = False
        else:
            print('[v168 verify] SKIP: tasks 表尚未创建（由任务子系统迁移负责）')

        print('[v168 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v168 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        for name, _sql in INDEXES:
            if _index_exists(conn, name):
                conn.execute(f'DROP INDEX IF EXISTS {name}')
                print(f'  - [DROP] 索引 {name}')

        # 先子表后头表
        for table in (REQUEST_LINE_TABLE, REQUISITION_LINE_TABLE,
                      CATALOG_TABLE, REQUEST_TABLE, REQUISITION_TABLE):
            if _table_exists(conn, table):
                conn.execute(f'DROP TABLE IF EXISTS {table}')
                print(f'  - [DROP] 表 {table}')
            else:
                print(f'  - [SKIP] 表 {table} 不存在')

        conn.commit()
        print('[v168 rollback] 完成（permissions 行保留）')
        return True
    except Exception as e:
        conn.rollback()
        print('[v168 rollback] 失败: %s' % e)
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

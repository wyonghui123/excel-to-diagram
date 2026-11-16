# -*- coding: utf-8 -*-
"""v279 —— 集成模块 M1 数据层：连接配置 / 导入 staging / 投递事实扩展。

依据:
  docs/specs/spec-integration-module-2026-11-15.md
    §3 领域模型（单一事实模型）/ §4 数据模型 / §11 里程碑 M1

内容:
  1. 新建 `integration_connection`（配置对象）：渠道 / 方向 / 端点 / 认证方式，
     密钥只存引用 `secret_ref`（env:INTEGRATION_SECRET_<id>），不存明文。
  2. 新建 `import_staging_rows`（事实表）：批次身份复用 `task_runs.id`
     （`batch_run_id` 为弱引用，不建 FK，沿用 v246 `task_runs` 风格），
     对外批次号 `batch_no` + `row_no` 唯一，行级错误词表化。
  3. `notification_deliveries` 原地加 3 列：`connection_id` / `target_type` /
     `direction`；不新建投递表，批次汇总按 `status` 实时聚合。
  4. 回填:
     a) `change_subscriptions` 中 distinct 的 `webhook_url` → 生成 webhook 连接，
        `auth_type` 取 hmac（有 secret）/ none，`code` 用 'wh_' + url 短 hash；
        `webhook_secret` 只在 `secret_ref` 写引用，明文保留在原列作迁移期只读兼容。
     b) `notification_deliveries.target_type`：人渠道（in_app/email/sms/im/feishu）
        记 human，其余（webhook/rest/file 等）记 system。

边界:
  · 不新建投递表 / 批次表 / 事件旁路表（§3 单一事实模型）；
  · `notification_deliveries` 唯一键 `(event_id, subscription_id, channel)` 不变；
  · 不回填 `connection_id`（由后续映射/投递写入时按连接 code 填写）；
  · 所有 DDL 幂等（IF NOT EXISTS），ALTER 前用 PRAGMA table_info 守卫，
    回填一律 `WHERE ... IS NULL` / 按 code 去重，可重复执行。
"""

import hashlib
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v279__integration_module'

CONNECTION_TABLE = 'integration_connection'
STAGING_TABLE = 'import_staging_rows'
DELIVERY_TABLE = 'notification_deliveries'
SUBSCRIPTION_TABLE = 'change_subscriptions'

CONNECTION_DDL = """
CREATE TABLE IF NOT EXISTS integration_connection (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            VARCHAR(200) NOT NULL,
    name            VARCHAR(200) NOT NULL,
    channel_type    VARCHAR(200) NOT NULL,
    direction       VARCHAR(200) NOT NULL DEFAULT 'outbound',
    endpoint        VARCHAR(500) NOT NULL,
    auth_type       VARCHAR(200) NOT NULL DEFAULT 'none',
    secret_ref      VARCHAR(500),
    header_template TEXT,
    timeout_ms      INTEGER NOT NULL DEFAULT 15000,
    retry_max       INTEGER NOT NULL DEFAULT 5,
    enabled         INTEGER NOT NULL DEFAULT 1,
    owner_user_id   INTEGER,
    created_at      DATETIME NOT NULL,
    updated_at      DATETIME NOT NULL
)
"""

STAGING_DDL = """
CREATE TABLE IF NOT EXISTS import_staging_rows (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_run_id     INTEGER,
    batch_no         VARCHAR(200) NOT NULL,
    object_type      VARCHAR(200) NOT NULL,
    row_no           INTEGER NOT NULL,
    raw_payload      TEXT NOT NULL,
    status           VARCHAR(200) NOT NULL DEFAULT 'pending',
    error_field      VARCHAR(200),
    error_code       VARCHAR(200),
    error_message    TEXT,
    target_record_id INTEGER,
    created_at       DATETIME NOT NULL
)
"""

TABLES = (
    (CONNECTION_TABLE, CONNECTION_DDL),
    (STAGING_TABLE, STAGING_DDL),
)

INDEXES = (
    ('uq_integration_connection_code',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_integration_connection_code '
     'ON integration_connection(code)'),
    ('idx_integration_connection_channel',
     'CREATE INDEX IF NOT EXISTS idx_integration_connection_channel '
     'ON integration_connection(channel_type, enabled)'),
    # 由索引规则引擎自 updated_at（时间戳语义）派生，与 schema YAML 派生保持一致
    ('idx_integration_connection_updated_at',
     'CREATE INDEX IF NOT EXISTS idx_integration_connection_updated_at '
     'ON integration_connection(updated_at)'),
    ('uq_import_staging_row',
     'CREATE UNIQUE INDEX IF NOT EXISTS uq_import_staging_row '
     'ON import_staging_rows(batch_no, row_no)'),
    ('idx_import_staging_batch',
     'CREATE INDEX IF NOT EXISTS idx_import_staging_batch '
     'ON import_staging_rows(batch_no, status)'),
    # 同上：created_at 时间戳语义派生索引
    ('idx_import_staging_rows_created_at',
     'CREATE INDEX IF NOT EXISTS idx_import_staging_rows_created_at '
     'ON import_staging_rows(created_at)'),
)

#: (列, 列定义)；SQLite 不支持 ADD COLUMN IF NOT EXISTS，统一走 PRAGMA 守卫。
NEW_DELIVERY_COLUMNS = (
    ('connection_id', 'INTEGER REFERENCES integration_connection(id)'),
    ('target_type', 'VARCHAR(200)'),
    ('direction', 'VARCHAR(200)'),
)

#: 面向人的投递渠道（target_type='human'）；其余渠道一律 'system'。
HUMAN_CHANNELS = ('in_app', 'email', 'sms', 'im', 'feishu')


def _has_table(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name = ?", [table]
    ).fetchone()
    return bool(row)


def _has_index(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND name = ?", [name]
    ).fetchone()
    return bool(row)


def _columns(conn: sqlite3.Connection, table: str) -> set:
    try:
        rows = conn.execute('PRAGMA table_info(%s)' % table).fetchall()
    except sqlite3.DatabaseError:
        return set()
    return {row[1] for row in rows}


def _do_tables(conn: sqlite3.Connection) -> None:
    for table, ddl in TABLES:
        if _has_table(conn, table):
            print('  - [SKIP] 表 %s 已存在' % table)
            continue
        conn.execute(ddl)
        print('  - [NEW] 表 %s' % table)


def _do_indexes(conn: sqlite3.Connection) -> None:
    for name, sql in INDEXES:
        if _has_index(conn, name):
            print('  - [SKIP] 索引 %s 已存在' % name)
            continue
        conn.execute(sql)
        print('  - [NEW] 索引 %s' % name)


def _do_delivery_columns(conn: sqlite3.Connection) -> None:
    if not _has_table(conn, DELIVERY_TABLE):
        print('  - [SKIP] 表 %s 不存在，跳过加列' % DELIVERY_TABLE)
        return
    existing = _columns(conn, DELIVERY_TABLE)
    for column, ddl in NEW_DELIVERY_COLUMNS:
        if column in existing:
            print('  - [OK] %s.%s 已存在' % (DELIVERY_TABLE, column))
            continue
        conn.execute(
            'ALTER TABLE %s ADD COLUMN %s %s' % (DELIVERY_TABLE, column, ddl))
        print('  - [NEW] %s.%s' % (DELIVERY_TABLE, column))


def _connection_code(url: str) -> str:
    """稳定可读的连接编码：'wh_' + url 的 sha1 前 12 位。"""
    digest = hashlib.sha1(url.strip().encode('utf-8')).hexdigest()
    return 'wh_' + digest[:12]


def _seed_connections(conn: sqlite3.Connection) -> None:
    """distinct webhook_url → webhook 连接；密钥只写 secret_ref 引用。"""
    if not _has_table(conn, SUBSCRIPTION_TABLE):
        print('  - [SKIP] 表 %s 不存在，跳过连接回填' % SUBSCRIPTION_TABLE)
        return
    rows = conn.execute(
        'SELECT webhook_url, '
        "MAX(CASE WHEN webhook_secret IS NOT NULL "
        "AND TRIM(webhook_secret) <> '' THEN webhook_secret END) "
        'FROM %s '
        'WHERE webhook_url IS NOT NULL AND TRIM(webhook_url) <> \'\' '
        'GROUP BY webhook_url' % SUBSCRIPTION_TABLE).fetchall()
    for url, secret in rows:
        code = _connection_code(url)
        exists = conn.execute(
            'SELECT 1 FROM %s WHERE code = ?' % CONNECTION_TABLE,
            [code]).fetchone()
        if exists:
            print('  - [SKIP] 连接 %s 已存在' % code)
            continue
        has_secret = bool(secret and secret.strip())
        cur = conn.execute(
            'INSERT INTO %s (code, name, channel_type, direction, endpoint, '
            'auth_type, secret_ref, header_template, timeout_ms, retry_max, '
            'enabled, owner_user_id, created_at, updated_at) '
            "VALUES (?, ?, 'webhook', 'outbound', ?, ?, NULL, NULL, "
            "15000, 5, 1, NULL, datetime('now'), datetime('now'))"
            % CONNECTION_TABLE,
            [code, '变更订阅 Webhook %s' % code, url,
             'hmac' if has_secret else 'none'])
        # 只存引用；明文保留在 change_subscriptions.webhook_secret（迁移期只读兼容）
        if has_secret:
            conn.execute(
                'UPDATE %s SET secret_ref = ? WHERE id = ?' % CONNECTION_TABLE,
                ['env:INTEGRATION_SECRET_%d' % cur.lastrowid, cur.lastrowid])
        print('  - [NEW] 连接 %s ← %s%s'
              % (code, url, '（hmac，密钥仅存引用）' if has_secret else ''))


def _backfill_target_type(conn: sqlite3.Connection) -> None:
    """已有投递行补 target_type；重复执行命中 0 行。"""
    if not _has_table(conn, DELIVERY_TABLE):
        print('  - [SKIP] 表 %s 不存在，跳过 target_type 回填' % DELIVERY_TABLE)
        return
    if 'target_type' not in _columns(conn, DELIVERY_TABLE):
        print('  - [SKIP] %s.target_type 不存在，跳过回填' % DELIVERY_TABLE)
        return
    human = ', '.join("'%s'" % channel for channel in HUMAN_CHANNELS)
    cur = conn.execute(
        "UPDATE %s SET target_type = CASE WHEN channel IN (%s) "
        "THEN 'human' ELSE 'system' END WHERE target_type IS NULL"
        % (DELIVERY_TABLE, human))
    print('  - [OK] target_type 回填 %d 行' % (cur.rowcount or 0))


def migrate(db_path, skip_backup=True) -> bool:
    """migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    path = Path(db_path)
    if not path.exists():
        print('[v279] SKIP: database not found: %s' % path)
        return False

    conn = sqlite3.connect(str(path), timeout=10)
    try:
        print('[v279] 开始: 集成模块 M1 数据层')
        conn.execute('BEGIN')
        _do_tables(conn)
        _do_indexes(conn)
        _do_delivery_columns(conn)
        _seed_connections(conn)
        _backfill_target_type(conn)
        conn.commit()
        print('[v279] 完成')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


#: 部分历史迁移以 `upgrade()` 命名；保留别名便于手工调用。
upgrade = migrate


def verify(db_path) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v279 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        ok = True
        for table, _ddl in TABLES:
            if not _has_table(conn, table):
                print('[v279 verify] FAIL: 缺表 %s' % table)
                ok = False
        for name, _sql in INDEXES:
            if not _has_index(conn, name):
                print('[v279 verify] FAIL: 缺索引 %s' % name)
                ok = False
        if _has_table(conn, DELIVERY_TABLE):
            columns = _columns(conn, DELIVERY_TABLE)
            for column, _ddl in NEW_DELIVERY_COLUMNS:
                if column not in columns:
                    print('[v279 verify] FAIL: 缺列 %s.%s'
                          % (DELIVERY_TABLE, column))
                    ok = False
        return ok
    finally:
        conn.close()
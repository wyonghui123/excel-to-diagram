# -*- coding: utf-8 -*-
"""[v269 2026-11-13] 平台级附件（内容 + 多态链接）

依据: docs/specs/spec-platform-attachment-2026-11-13.md §3.4 / §3.5 / §3.7 / §15.5
范围: 2 表 + 5 索引 + attachment_category 码表种子；不动任何既有表。
回滚: 删索引 / 2 表 / attachment_category 码值；上传目录不自动删除（保留取证）。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v269__platform_attachment'

ATTACHMENT_TABLE = 'attachments'
LINK_TABLE = 'attachment_links'

# 与 meta/schemas/generated_schema.sql 逐字一致
ATTACHMENT_DDL = """
CREATE TABLE IF NOT EXISTS attachments (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    original_file_name VARCHAR(200) NOT NULL,
    display_name VARCHAR(200),
    mime_type VARCHAR(200) NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 VARCHAR(200) NOT NULL,
    storage_backend VARCHAR(200) NOT NULL DEFAULT 'fs',
    storage_key VARCHAR(200) NOT NULL,
    category VARCHAR(200) NOT NULL DEFAULT 'other',
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    scan_status VARCHAR(200) NOT NULL DEFAULT 'unchecked',
    supersedes_id INTEGER,
    uploaded_by VARCHAR(200) NOT NULL,
    uploaded_at DATETIME NOT NULL,
    description TEXT
)
"""

LINK_DDL = """
CREATE TABLE IF NOT EXISTS attachment_links (
    created_at DATETIME,
    created_by VARCHAR(200),
    updated_by VARCHAR(200),
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    attachment_id INTEGER NOT NULL,
    target_type VARCHAR(200) NOT NULL,
    target_id INTEGER NOT NULL,
    link_role VARCHAR(200) NOT NULL DEFAULT 'supporting',
    seq INTEGER NOT NULL DEFAULT 10,
    is_primary INTEGER NOT NULL DEFAULT 0,
    visibility VARCHAR(200) NOT NULL DEFAULT 'internal',
    status VARCHAR(200) NOT NULL DEFAULT 'active',
    description TEXT
)
"""

INDEX_DDL = (
    'CREATE INDEX IF NOT EXISTS ix_attachments_sha256 '
    'ON attachments(sha256)',
    'CREATE INDEX IF NOT EXISTS ix_attachments_status '
    'ON attachments(status)',
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_attachment_link_active '
    'ON attachment_links(attachment_id, target_type, target_id, link_role) '
    "WHERE status = 'active'",
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_attachment_link_primary '
    'ON attachment_links(target_type, target_id, link_role) '
    "WHERE is_primary = 1 AND status = 'active'",
    'CREATE INDEX IF NOT EXISTS ix_attachment_link_target '
    'ON attachment_links(target_type, target_id, status, seq)',
)

INDEX_NAMES = (
    'ix_attachments_sha256',
    'ix_attachments_status',
    'uq_attachment_link_active',
    'uq_attachment_link_primary',
    'ix_attachment_link_target',
)

ENUM_TYPE_ID = 'attachment_category'

# [v0.7 P0.2-1] 码值 / 中文名不再手写第二份：
#   码值真源 = models_enums.AttachmentCategory；中文名真源 = migrate_enums.ENUM_VALUE_NAME_MAP。
#   启动时 migrate_enums() 会按同一份数据幂等补齐（本迁移的 seed 仅保证迁移自包含可验证）。
from meta.core.models_enums import AttachmentCategory  # noqa: E402
from meta.scripts.migrate_enums import ENUM_VALUE_NAME_MAP  # noqa: E402

CATEGORIES = tuple(
    (member.value,
     ENUM_VALUE_NAME_MAP[ENUM_TYPE_ID][member.value],
     (idx + 1) * 10)
    for idx, member in enumerate(AttachmentCategory)
)


# --------------------------------------------------------------------- helpers

def _connect(db_path):
    return sqlite3.connect(str(db_path))


def _table_exists(conn, table):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        [table]).fetchone() is not None


def _index_exists(conn, index):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
        [index]).fetchone() is not None


# --------------------------------------------------------------------- tables

def _do_tables(conn):
    for table, ddl in ((ATTACHMENT_TABLE, ATTACHMENT_DDL),
                       (LINK_TABLE, LINK_DDL)):
        existed = _table_exists(conn, table)
        conn.execute(ddl)
        print('[v269] %s: %s' % ('SKIP' if existed else 'CREATE', table))
    for ddl in INDEX_DDL:
        conn.execute(ddl)
    print('[v269] 索引: %d 条就绪' % len(INDEX_NAMES))


# ----------------------------------------------------------------- enum seed

def _seed_enum(conn):
    if not (_table_exists(conn, 'enum_types')
            and _table_exists(conn, 'enum_values')):
        print('[v269] SKIP: 码表不存在（未写 attachment_category）')
        return
    row = conn.execute('SELECT id FROM enum_types WHERE id = ?',
                       [ENUM_TYPE_ID]).fetchone()
    if row:
        print('[v269] SKIP: 枚举类型 %s 已存在' % ENUM_TYPE_ID)
    else:
        conn.execute(
            'INSERT INTO enum_types (id, name, category, mutability, '
            "description, created_at) VALUES (?, ?, 'business', 'extensible', "
            "?, datetime('now'))",
            [ENUM_TYPE_ID, '附件分类', '附件分类码表（可由业务扩展）'])
        print('[v269] CREATE: 枚举类型 %s' % ENUM_TYPE_ID)
    for code, label, sort_order in CATEGORIES:
        existing = conn.execute(
            'SELECT id FROM enum_values WHERE enum_type_id = ? AND code = ?',
            [ENUM_TYPE_ID, code]).fetchone()
        if existing:
            conn.execute(
                'UPDATE enum_values SET name = ?, sort_order = ?, '
                'is_active = 1 WHERE id = ?',
                [label, sort_order, existing[0]])
            print('[v269] SKIP: 码值 %s.%s 已存在（已对齐）'
                  % (ENUM_TYPE_ID, code))
            continue
        conn.execute(
            'INSERT INTO enum_values (enum_type_id, code, name, sort_order, '
            "is_system, is_active, created_at) VALUES (?, ?, ?, ?, 0, 1, "
            "datetime('now'))",
            [ENUM_TYPE_ID, code, label, sort_order])
        print('[v269] CREATE: 码值 %s.%s' % (ENUM_TYPE_ID, code))


# ------------------------------------------------------------------- migrate

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v269] 开始: 平台级附件（2 表 + 5 索引 + 码表）')
    conn = _connect(db_path)
    try:
        _do_tables(conn)
        _seed_enum(conn)
        conn.commit()
        print('[v269] 完成: attachments / attachment_links / '
              'attachment_category')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# -------------------------------------------------------------------- verify

def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    problems = []
    conn = _connect(db_path)
    try:
        for table in (ATTACHMENT_TABLE, LINK_TABLE):
            if not _table_exists(conn, table):
                problems.append('缺少表 %s' % table)
        for index in INDEX_NAMES:
            if not _index_exists(conn, index):
                problems.append('缺少索引 %s' % index)
        if _table_exists(conn, 'enum_values'):
            for code, label, _sort in CATEGORIES:
                row = conn.execute(
                    'SELECT name, is_active FROM enum_values '
                    'WHERE enum_type_id = ? AND code = ?',
                    [ENUM_TYPE_ID, code]).fetchone()
                if not row:
                    problems.append('缺少码值 %s.%s' % (ENUM_TYPE_ID, code))
                    continue
                if row[0] != label:
                    problems.append('码值 %s.%s name=%r（期望 %r）'
                                    % (ENUM_TYPE_ID, code, row[0], label))
                if row[1] != 1:
                    problems.append('码值 %s.%s is_active=%r（期望 1）'
                                    % (ENUM_TYPE_ID, code, row[1]))
        else:
            problems.append('缺少表 enum_values')
    finally:
        conn.close()

    if problems:
        for problem in problems:
            print('[v269] FAIL: %s' % problem)
        return False
    print('[v269] PASS: 2 表 / 5 索引 / %d 码值齐备' % len(CATEGORIES))
    return True


# ------------------------------------------------------------------- rollback

def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    print('[v269] 开始回滚: 删索引 / 2 表 / attachment_category')
    conn = _connect(db_path)
    try:
        for index in INDEX_NAMES:
            if _index_exists(conn, index):
                conn.execute('DROP INDEX IF EXISTS %s' % index)
                print('[v269] DROP: 索引 %s' % index)
        for table in (LINK_TABLE, ATTACHMENT_TABLE):
            if _table_exists(conn, table):
                conn.execute('DROP TABLE IF EXISTS %s' % table)
                print('[v269] DROP: 表 %s' % table)
        if _table_exists(conn, 'enum_values'):
            conn.execute('DELETE FROM enum_values WHERE enum_type_id = ?',
                         [ENUM_TYPE_ID])
        if _table_exists(conn, 'enum_types'):
            conn.execute('DELETE FROM enum_types WHERE id = ?', [ENUM_TYPE_ID])
        print('[v269] DROP: 枚举类型 %s' % ENUM_TYPE_ID)
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else 'meta/architecture.db'
    migrate(Path(target))
    verify(Path(target))
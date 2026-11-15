# -*- coding: utf-8 -*-
"""[v274 2026-11-15] 单据打印平台（模板 / 绑定 / 打印记录）

依据: docs/specs/spec-print-platform-2026-11-15.md §4.1 / §4.2 / §4.3
范围: 3 表 + 4 索引；不动任何既有表。可打印清单不落库（派生自 type_definitions），
      因此本迁移不新建「可打印类型注册表」。
回滚: 删索引 / 3 表；归档 PDF 不自动删除（附件平台内容保留取证）。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v274__print_platform'

TEMPLATE_TABLE = 'print_templates'
BINDING_TABLE = 'print_bindings'
RUN_TABLE = 'print_runs'

# 与 meta/schemas/generated_schema.sql 逐字一致（由 sync_schema --generate 产出）
TEMPLATE_DDL = """
CREATE TABLE IF NOT EXISTS print_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bo_code VARCHAR(200) NOT NULL,
    type_code VARCHAR(200) NOT NULL DEFAULT '',
    code VARCHAR(200) NOT NULL,
    name VARCHAR(200) NOT NULL,
    version INTEGER NOT NULL,
    status VARCHAR(200) NOT NULL,
    html TEXT NOT NULL,
    css TEXT DEFAULT '',
    variables_json TEXT NOT NULL,
    paper_size VARCHAR(200) DEFAULT 'A4',
    orientation VARCHAR(200) DEFAULT 'portrait',
    margin_top REAL DEFAULT 10,
    margin_right REAL DEFAULT 10,
    margin_bottom REAL DEFAULT 10,
    margin_left REAL DEFAULT 10,
    scope_type VARCHAR(200) DEFAULT 'system',
    scope_id VARCHAR(200),
    effective_from VARCHAR(200),
    effective_to VARCHAR(200),
    created_by VARCHAR(200) NOT NULL,
    created_at DATETIME NOT NULL,
    published_at DATETIME,
    archived_at DATETIME
)
"""

BINDING_DDL = """
CREATE TABLE IF NOT EXISTS print_bindings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bo_code VARCHAR(200) NOT NULL,
    type_code VARCHAR(200) NOT NULL DEFAULT '',
    scope_type VARCHAR(200) DEFAULT 'system',
    scope_id VARCHAR(200),
    condition_json TEXT NOT NULL DEFAULT '{}',
    priority INTEGER NOT NULL DEFAULT 100,
    template_id INTEGER NOT NULL,
    is_default INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
)
"""

RUN_DDL = """
CREATE TABLE IF NOT EXISTS print_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bo_code VARCHAR(200) NOT NULL,
    type_code VARCHAR(200) NOT NULL DEFAULT '',
    doc_id VARCHAR(200) NOT NULL,
    doc_no VARCHAR(200),
    doc_rev VARCHAR(200),
    template_id INTEGER NOT NULL,
    template_version INTEGER NOT NULL,
    trigger VARCHAR(200) NOT NULL,
    is_formal INTEGER NOT NULL DEFAULT 0,
    is_reprint INTEGER NOT NULL DEFAULT 0,
    print_seq INTEGER NOT NULL DEFAULT 0,
    watermark VARCHAR(200) NOT NULL DEFAULT 'NONE',
    attachment_id INTEGER,
    payload_hash VARCHAR(200),
    job_run_id VARCHAR(200),
    status VARCHAR(200) NOT NULL,
    error_code VARCHAR(200),
    error_message TEXT,
    operator_id VARCHAR(200) NOT NULL,
    operator_name VARCHAR(200) NOT NULL,
    created_at DATETIME NOT NULL
)
"""

INDEX_DDL = (
    'CREATE UNIQUE INDEX IF NOT EXISTS uq_print_template_version '
    'ON print_templates(bo_code, type_code, code, version)',
    'CREATE INDEX IF NOT EXISTS idx_print_templates_bo_status '
    'ON print_templates(bo_code, status)',
    'CREATE INDEX IF NOT EXISTS idx_print_bindings_lookup '
    'ON print_bindings(bo_code, type_code, is_active, priority)',
    'CREATE INDEX IF NOT EXISTS idx_print_runs_doc '
    'ON print_runs(bo_code, doc_id, created_at)',
    'CREATE INDEX IF NOT EXISTS idx_print_runs_job '
    'ON print_runs(job_run_id)',
)

INDEX_NAMES = (
    'uq_print_template_version',
    'idx_print_templates_bo_status',
    'idx_print_bindings_lookup',
    'idx_print_runs_doc',
    'idx_print_runs_job',
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
    for table, ddl in ((TEMPLATE_TABLE, TEMPLATE_DDL),
                       (BINDING_TABLE, BINDING_DDL),
                       (RUN_TABLE, RUN_DDL)):
        existed = _table_exists(conn, table)
        conn.execute(ddl)
        print('[v274] %s: %s' % ('SKIP' if existed else 'CREATE', table))
    for ddl in INDEX_DDL:
        conn.execute(ddl)
    print('[v274] 索引: %d 条就绪' % len(INDEX_NAMES))


# ------------------------------------------------------------------- migrate

def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    print('[v274] 开始: 单据打印平台（3 表 + 5 索引）')
    conn = _connect(db_path)
    try:
        _do_tables(conn)
        conn.commit()
        print('[v274] 完成: print_templates / print_bindings / print_runs')
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
        for table in (TEMPLATE_TABLE, BINDING_TABLE, RUN_TABLE):
            if not _table_exists(conn, table):
                problems.append('缺少表 %s' % table)
        for index in INDEX_NAMES:
            if not _index_exists(conn, index):
                problems.append('缺少索引 %s' % index)
    finally:
        conn.close()

    if problems:
        for problem in problems:
            print('[v274] FAIL: %s' % problem)
        return False
    print('[v274] PASS: 3 表 / %d 索引齐备' % len(INDEX_NAMES))
    return True


# ------------------------------------------------------------------- rollback

def rollback(db_path: Path) -> bool:
    db_path = Path(db_path)
    print('[v274] 开始回滚: 删索引 / 3 表')
    conn = _connect(db_path)
    try:
        for index in INDEX_NAMES:
            if _index_exists(conn, index):
                conn.execute('DROP INDEX IF EXISTS %s' % index)
                print('[v274] DROP: 索引 %s' % index)
        for table in (RUN_TABLE, BINDING_TABLE, TEMPLATE_TABLE):
            if _table_exists(conn, table):
                conn.execute('DROP TABLE IF EXISTS %s' % table)
                print('[v274] DROP: 表 %s' % table)
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
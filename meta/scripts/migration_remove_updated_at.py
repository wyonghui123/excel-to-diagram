# -*- coding: utf-8 -*-
"""
Migration: 移除 BO 框架表的物理 updated_at 列

【背景 2026-06-05】
v1.4 SSOT：updated_at 是计算字段，从 audit_logs 实时派生。
当前 8 张 BO 框架管理的表还保留着物理 `updated_at` 列，
与 BO 框架的 persistence_interceptor._enrich_audit_virtual_fields 派生逻辑重复。

本脚本：
  1. 备份 DB
  2. 对每张表执行 12 步 SQLite 重建表法
  3. 移除 updated_at 列
  4. 数据 100% 保留

回滚：
  本脚本创建 `meta/architecture.db.bak.<timestamp>` 备份文件
  cp 回去即可回滚

受影响的表（仅 BO 框架管理的表，task/permission/scheduled 类不处理）：
  - products
  - business_objects
  - domains
  - sub_domains
  - service_modules
  - relationships
  - new_objects

跳过（保留 updated_at 列）：
  - task_executions / task_queues / scheduled_tasks / ai_async_tasks (任务调度类)
  - menu_permissions / permission_bundles / permission_rules (权限类)
  - filter_variants (UI 状态)
  - versions (version 业务状态)
  - user_groups (SSOT v1.4 P3 已采用派生)
  - roles (SSOT v1.4 P3 已采用派生)
  - role_intents (专用 intent_resolver DAO 管理，直接 SQL 写入 updated_at)

用法：
  python d:\filework\excel-to-diagram\meta\scripts\migration_remove_updated_at.py
"""
import sqlite3
import os
import sys
import shutil
import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


# 仅处理 BO 框架管理的表（其他表的 updated_at 有其他用途）
# 注意：role_intents 不在 BO 框架，由 intent_resolver.py 专用 DAO 管理
#       它直接 SQL 写入 updated_at，**不应该**被本脚本处理
BO_TABLES = [
    'products',
    'business_objects',
    'domains',
    'sub_domains',
    'service_modules',
    'relationships',
    'new_objects',
]


def get_db_path():
    default = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        'architecture.db'
    )
    return os.environ.get('SQLITE_DB_PATH', default)


def backup_db(db_path):
    if not os.path.exists(db_path):
        logger.error('DB not found: %s', db_path)
        return None
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = f'{db_path}.bak.{ts}'
    shutil.copy2(db_path, backup_path)
    logger.info('DB backed up: %s', backup_path)
    return backup_path


def table_has_column(cursor, table_name, column_name):
    cursor.execute(f'PRAGMA table_info({table_name})')
    return column_name in [r[1] for r in cursor.fetchall()]


def drop_column(cursor, table, column='updated_at'):
    """SQLite 12 步重表法：移除指定列"""
    if not table_has_column(cursor, table, column):
        return False, f'{table}: no {column} column, skip'

    # 1. 获取列定义
    cursor.execute(f'PRAGMA table_info({table})')
    all_cols = [(r[1], r[2]) for r in cursor.fetchall()]
    keep_cols = [c for c in all_cols if c[0] != column]

    # 2. 备份索引
    cursor.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
        (table,)
    )
    indexes = [r[0] for r in cursor.fetchall()]

    # 2.5 清理残留的 _bak_<table>_* 表（说明上次 migration 中断）
    # Fix 2026-06-05: 防止中断后 _bak 残留导致后续 FK 失败
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE ?",
        (f'_bak_{table}_%',)
    )
    for (bak_name,) in cursor.fetchall():
        logger.warning('  发现残留备份表: %s，先清理', bak_name)
        cursor.execute(f'DROP TABLE IF EXISTS {bak_name}')

    # 3. 重建表
    cursor.execute('PRAGMA foreign_keys=OFF')
    cursor.execute('BEGIN')

    try:
        temp = f'_bak_{table}_{datetime.now().strftime("%H%M%S")}'
        cursor.execute(f'ALTER TABLE {table} RENAME TO {temp}')

        col_defs = ', '.join([f'{n} {t}' for n, t in keep_cols])
        cursor.execute(f'CREATE TABLE {table} ({col_defs})')

        keep_names = [c[0] for c in keep_cols]
        cols_csv = ', '.join(keep_names)
        cursor.execute(
            f'INSERT INTO {table} ({cols_csv}) SELECT {cols_csv} FROM {temp}'
        )
        cursor.execute(f'DROP TABLE {temp}')

        for idx_sql in indexes:
            try:
                cursor.execute(idx_sql)
            except Exception as e:
                logger.warning('  %s: index restore failed: %s', table, e)

        cursor.execute('COMMIT')
        return True, f'{table}: dropped {column} (kept {len(keep_cols)} cols)'
    except Exception as e:
        cursor.execute('ROLLBACK')
        return False, f'{table}: FAILED: {e}'
    finally:
        cursor.execute('PRAGMA foreign_keys=ON')


def main():
    db_path = get_db_path()
    logger.info('DB: %s', db_path)

    backup = backup_db(db_path)
    if not backup:
        return False

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    success, fail = 0, 0
    for table in BO_TABLES:
        ok, msg = drop_column(cur, table)
        if ok:
            success += 1
            logger.info('  [DECORATIVE] %s', msg)
        else:
            fail += 1
            if 'skip' not in msg:
                logger.error('  [DECORATIVE] %s', msg)
            else:
                logger.info('  - %s', msg)
    conn.commit()

    # Verify
    logger.info('--- Verification ---')
    all_pass = True
    for table in BO_TABLES:
        if table_has_column(cur, table, 'updated_at'):
            logger.error('  %s: updated_at STILL EXISTS', table)
            all_pass = False
    conn.close()

    logger.info('--- Summary ---')
    logger.info('Dropped: %d / Failed: %d / Tables: %d', success, fail, len(BO_TABLES))
    logger.info('Backup:  %s', backup)

    if all_pass:
        logger.info('Migration completed successfully')
    else:
        logger.error('Some tables still have updated_at column')

    return all_pass


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)

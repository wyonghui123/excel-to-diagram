# -*- coding: utf-8 -*-
"""[V007.45 P0] 给 audit_logs 表加 created_at_epoch + 复合索引

背景:
  meta/core/audit_derived_fields.py 用 MAX(created_at_epoch) 优化排序聚合,
  但 yonaa 部署的 audit_logs 表从未加过这一列 (migration_ssot_stage1.py 仅
  本地手动跑过, 未集成到 deploy 流程)。
  后果:
    - _execute_audit_query 每次都打 WARNING "no such column: created_at_epoch"
    - fallback 路径走 MAX(created_at) TEXT 聚合, 264K 行全表扫描
    - 关系范围等 updated_at 排序慢, 前端"持续转"

修法:
  1. ALTER TABLE audit_logs ADD COLUMN created_at_epoch BIGINT
  2. Backfill: SET created_at_epoch = (strftime('%s', created_at) * 1000)
  3. CREATE INDEX idx_audit_ssot_updated
     ON audit_logs(object_type, object_id, action, created_at_epoch DESC)
  4. idempotent: 列已存在/索引已存在不报错

部署:
  SSH yonaa:
    cd /opt/app/deployments/v20260708_xxx
    /opt/miniconda3-py39/bin/python meta/migrations/v007_45_add_audit_logs_created_at_epoch.py
"""
import sqlite3
import os
import sys
import shutil
import re
from pathlib import Path
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)


# [V007.45 P0] 所有 VirtualSort/audit_derived 涉及的表
# 严格说 created_at_epoch 只属于 audit_logs, 其他表不需要这一列
TABLES_TO_MIGRATE = [
    {
        'table': 'audit_logs',
        'column': 'created_at_epoch',
        'type': 'BIGINT',
        'backfill_sql': """
            UPDATE audit_logs
            SET created_at_epoch = (strftime('%s', created_at) * 1000)
            WHERE created_at_epoch IS NULL AND created_at IS NOT NULL
        """,
        'index_sql': """
            CREATE INDEX IF NOT EXISTS idx_audit_ssot_updated
            ON audit_logs(object_type, object_id, action, created_at_epoch DESC)
        """,
    },
    # 未来其他表需要 derived created_at_epoch 时, 在此追加
]


def migrate_one(db_path: Path, table_spec: dict) -> bool:
    """迁移单个表 (idempotent)"""
    if not db_path.exists():
        logger.error(f'[SKIP] db not found: {db_path}')
        return False

    # Backup
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = db_path.with_suffix(f'.bak.v007_45.{ts}')
    try:
        shutil.copy2(db_path, backup_path)
        logger.info(f'[BACKUP] {backup_path}')
    except Exception as e:
        logger.warning(f'[WARN] backup failed: {e}, continue without backup')

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()

    table = table_spec['table']

    # 1. 检查表是否存在
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    )
    if not cur.fetchone():
        logger.warning(f'[SKIP] {table} 表不存在, 跳过')
        conn.close()
        return True

    # 2. 检查列是否已存在 (idempotent)
    cur.execute(f'PRAGMA table_info({table})')
    cols = [r[1] for r in cur.fetchall()]
    col = table_spec['column']

    if col not in cols:
        logger.info(f'[ADD] {table}.{col} ({table_spec["type"]})')
        cur.execute(f'ALTER TABLE {table} ADD COLUMN {col} {table_spec["type"]}')
    else:
        logger.info(f'[SKIP] {table}.{col} 已存在')

    # 3. Backfill
    backfill_sql = table_spec.get('backfill_sql')
    if backfill_sql:
        cur.execute(
            f"SELECT COUNT(*) FROM {table} "
            f"WHERE {col} IS NULL AND created_at IS NOT NULL"
        )
        null_count = cur.fetchone()[0]
        logger.info(f'[BACKFILL] {null_count} 行待 backfill')
        if null_count > 0:
            cur.execute(backfill_sql)
            logger.info(f'[OK] Backfilled {null_count} rows')

    # 4. 索引
    if 'index_sql' in table_spec:
        cur.execute(table_spec['index_sql'])
        logger.info(f'[INDEX] {table} 索引创建完成 (IF NOT EXISTS)')

    conn.commit()

    # 5. 验证
    cur.execute(f'PRAGMA table_info({table})')
    cols_after = [r[1] for r in cur.fetchall()]
    col_ok = col in cols_after
    logger.info(f'[VERIFY] {table}.{col}: {"[OK]" if col_ok else "[FAIL]"}')

    if 'index_sql' in table_spec:
        m = re.search(r'CREATE INDEX IF NOT EXISTS (\w+)', table_spec['index_sql'])
        if m:
            idx_name = m.group(1)
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND name=?",
                (idx_name,)
            )
            idx_ok = bool(cur.fetchone())
            logger.info(f'[VERIFY] {idx_name}: {"[OK]" if idx_ok else "[FAIL]"}')

    conn.close()
    return True


def main():
    """主入口: 默认从环境变量读 DB_PATH, 支持 yonaa 部署路径"""
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
    else:
        env_db = os.environ.get(
            'ARCH_DB_PATH', '/opt/app/deployments/meta/architecture.db'
        )
        db_path = Path(env_db)

    logger.info(f'[V007.45] 目标 db: {db_path}')
    ok = True
    for spec in TABLES_TO_MIGRATE:
        if not migrate_one(db_path, spec):
            ok = False
    if ok:
        logger.info('[V007.45] migration done')
    else:
        logger.error('[V007.45] migration failed')
        sys.exit(1)


if __name__ == '__main__':
    main()
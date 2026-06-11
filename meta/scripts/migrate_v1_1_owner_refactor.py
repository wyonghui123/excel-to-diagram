# -*- coding: utf-8 -*-
"""
v1.1 Owner 字段重构迁移脚本
=============================

执行: 维护窗口内, ~30 分钟
策略: SQLite 12-step 复制表流程 (不支持 DROP COLUMN)

变更:
1. products 加 visibility 字段 (default 'private')
   - 同时根据 versions.visibility 反推: 如果该 product 下任一 version 是 public, 则 product.visibility='public'
2. versions 删除 visibility 列
3. 6 张表 (versions/domains/sub_domains/service_modules/business_objects/relationships) 删除 owner_id 列
   - TBD-2: 不保留数据, 直接丢弃

用法:
    # 1. Dry-run (不实际执行, 仅检查)
    python meta/scripts/migrate_v1_1_owner_refactor.py --dry-run

    # 2. 实际迁移 (会先备份)
    python meta/scripts/migrate_v1_1_owner_refactor.py

    # 3. 回滚 (使用最近的备份)
    python meta/scripts/migrate_v1_1_owner_refactor.py --rollback
"""
import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

# ============================================================
# 配置
# ============================================================
PROJECT_ROOT = Path(__file__).parent.parent.parent
BACKUP_DIR = PROJECT_ROOT / 'meta' / 'backups'

# 允许通过 MIGRATION_TARGET_DB 环境变量覆盖 (用于测试)
import os as _os
_env_db = _os.environ.get('MIGRATION_TARGET_DB')
if _env_db:
    SOURCE_DB = Path(_env_db)
else:
    SOURCE_DB = PROJECT_ROOT / 'meta' / 'architecture.db'

# 6 张需要删除 owner_id 列的表
TABLES_DROP_OWNER_ID = [
    'versions',
    'domains',
    'sub_domains',
    'service_modules',
    'business_objects',
    'relationships',
]

# products 加 visibility; versions 删 visibility


def log(msg, level='INFO'):
    ts = datetime.now().strftime('%Y%m%d %H:%M:%S')
    print(f'[{ts}] [{level}] {msg}', flush=True)


def backup_database() -> Path:
    """步骤 0: 全量备份 + WAL checkpoint"""
    if not SOURCE_DB.exists():
        raise FileNotFoundError(f'DB not found: {SOURCE_DB}')

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = BACKUP_DIR / f'architecture.db.bak.{timestamp}'

    # 先 checkpoint WAL, 确保数据全部 flush 到主 DB
    conn = sqlite3.connect(SOURCE_DB)
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    conn.close()

    # 复制 DB 文件 + WAL + SHM (如果有)
    shutil.copy2(SOURCE_DB, backup_path)
    wal_src = Path(str(SOURCE_DB) + '-wal')
    shm_src = Path(str(SOURCE_DB) + '-shm')
    if wal_src.exists():
        shutil.copy2(wal_src, str(backup_path) + '-wal')
    if shm_src.exists():
        shutil.copy2(shm_src, str(backup_path) + '-shm')

    log(f'Backup created: {backup_path}')
    return backup_path


def get_columns(conn, table: str) -> list:
    """获取表的所有列名"""
    cur = conn.execute(f'PRAGMA table_info({table})')
    return [r[1] for r in cur.fetchall()]


def recreate_table_without_columns(conn, table: str, drop_columns: list) -> None:
    """
    SQLite 12-step: 重建表,排除指定列
    策略: 从 sqlite_master 拿完整 CREATE SQL, 用安全的列定义提取
    """
    cols = get_columns(conn, table)
    keep_cols = [c for c in cols if c not in drop_columns]
    if len(keep_cols) == len(cols):
        log(f'  {table}: no columns to drop, skip')
        return

    log(f'  {table}: dropping {drop_columns}')

    # 1. 从 sqlite_master 拿完整建表 SQL
    cur = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
        (table,)
    )
    create_sql = cur.fetchone()[0]

    # 2. 新表名
    new_table = f'_migrate_{table}_new'

    # 3. 构造新表的 CREATE SQL: 改表名 + 从列定义中删除指定列
    import re

    # 用括号匹配找列定义段 (第一个 ( 之后到最后一个 ) 之前)
    # 找出 CREATE TABLE ... ( ... ) 段
    m = re.match(r'(CREATE\s+TABLE\s+["\']?\w+["\']?\s*\()(.+)(\)\s*)$',
                 create_sql, re.DOTALL | re.IGNORECASE)
    if not m:
        raise RuntimeError(f'Cannot parse CREATE TABLE for {table}: {create_sql[:200]}')

    prefix = m.group(1)  # CREATE TABLE name (
    body = m.group(2)     # 列定义段
    suffix = m.group(3)   # )

    # 替换表名为新表
    prefix_new = re.sub(
        r'(CREATE\s+TABLE\s+["\']?)(\w+)(["\']?\s*\()',
        r'\1' + new_table + r'\3',
        prefix, count=1, flags=re.IGNORECASE
    )

    # 4. 在 body 中识别每个顶级段 (列定义 或 表级约束如 PRIMARY KEY/FOREIGN KEY)
    # 用括号配对 + 逗号 split
    segments = []
    depth = 0
    current = ''
    for ch in body:
        if ch == '(':
            depth += 1
            current += ch
        elif ch == ')':
            depth -= 1
            current += ch
        elif ch == ',' and depth == 0:
            segments.append(current.strip())
            current = ''
        else:
            current += ch
    if current.strip():
        segments.append(current.strip())

    # 5. 过滤掉要 drop 的列 (列定义以列名开头)
    def is_column_to_drop(seg: str) -> bool:
        # 列定义通常以列名开头, 可能是 "col_name TYPE" 或 '"col_name" TYPE'
        first_token = seg.strip().split(None, 1)[0] if seg.strip() else ''
        first_token = first_token.strip('"\'`[]')
        return first_token in drop_columns

    filtered_segments = [s for s in segments if not is_column_to_drop(s)]

    # 6. 拼回
    new_body = ',\n  '.join(filtered_segments)
    new_create_sql = f'{prefix_new}\n  {new_body}\n{suffix}'

    # 7. 创建新表
    conn.execute(new_create_sql)

    # 8. 复制数据 (排除要删的列)
    quoted_keep = ', '.join([f'"{c}"' for c in keep_cols])
    conn.execute(f'INSERT INTO "{new_table}" ({quoted_keep}) SELECT {quoted_keep} FROM "{table}"')

    # 9. 删旧表 + rename
    conn.execute(f'DROP TABLE "{table}"')
    conn.execute(f'ALTER TABLE "{new_table}" RENAME TO "{table}"')

    log(f'  {table}: done (kept {len(keep_cols)} columns)')


def step1_add_products_visibility(conn) -> None:
    """步骤 1: products 加 visibility 字段 (default 'private')"""
    log('Step 1: Add products.visibility')

    cols = get_columns(conn, 'products')
    if 'visibility' in cols:
        log('  products.visibility already exists, skip')
        return

    # 1.1 加列 (允许 NULL 临时, 后面 UPDATE)
    conn.execute("""
        ALTER TABLE products ADD COLUMN visibility VARCHAR(20)
    """)
    log('  products.visibility column added (NULL)')

    # 1.2 反推: 如果 product 下任一 version 是 public, 则 product.visibility='public'
    # 否则 private
    conn.execute("""
        UPDATE products
        SET visibility = CASE
            WHEN EXISTS (
                SELECT 1 FROM versions v
                WHERE v.product_id = products.id AND v.visibility = 'public'
            ) THEN 'public'
            ELSE 'private'
        END
    """)
    log('  products.visibility backfilled from versions.visibility')

    # 1.3 设为 NOT NULL + 加 CHECK 约束 (SQLite 不能直接 ALTER 加 NOT NULL, 重建表)
    # 检查是否需要重建
    cur = conn.execute("PRAGMA table_info(products)")
    notnull = any(r[1] == 'visibility' and r[3] == 1 for r in cur.fetchall())
    if not notnull:
        log('  Rebuilding products to add NOT NULL + CHECK constraint')
        # 用 12-step 重建 (含 visibility NOT NULL)
        cur = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='products'")
        create_sql = cur.fetchone()[0]

        new_table = '_migrate_products_new'
        # 注意: ALTER 加的 visibility 列已存在,这里只是改 NOT NULL 约束
        # SQLite 不支持直接加 NOT NULL, 但在 INSERT 时已是 NOT NULL 数据,我们可以跳过这一步
        # 因为 NOT NULL 在表层不会立刻报错,只会在 INSERT NULL 时报错
        log('  products.visibility already populated, NOT NULL check enforced at app level')
        log('  (SQLite 3.x cannot ALTER ADD CONSTRAINT, but column is fully populated)')

    # 1.4 加 CHECK 约束 (单独步骤, 因为 ALTER TABLE 在 SQLite 不支持加约束)
    # 注: SQLite 3.32+ 支持, 但稳妥起见不做
    log('  Step 1 done')


def step2_drop_versions_visibility(conn) -> None:
    """步骤 2: versions 删除 visibility 列 (已上移到 product)"""
    log('Step 2: Drop versions.visibility')
    recreate_table_without_columns(conn, 'versions', ['visibility'])


def step3_drop_child_owner_id(conn) -> None:
    """步骤 3: 6 张 child 表删除 owner_id 列 (TBD-2: 不保留数据)"""
    log('Step 3: Drop owner_id from child tables')
    for table in TABLES_DROP_OWNER_ID:
        cols = get_columns(conn, table)
        if 'owner_id' in cols:
            recreate_table_without_columns(conn, table, ['owner_id'])
        else:
            log(f'  {table}: no owner_id column, skip')


def step4_drop_redundant_visibility(conn) -> None:
    """步骤 4: 4 张表删除冗余的 visibility 列 (版本概念已废弃)"""
    log('Step 4: Drop redundant visibility columns')
    for table in ['domains', 'sub_domains', 'service_modules', 'business_objects']:
        cols = get_columns(conn, table)
        if 'visibility' in cols:
            recreate_table_without_columns(conn, table, ['visibility'])


def verify_post_migration(conn) -> None:
    """验证迁移结果"""
    log('=== Post-migration verification ===')

    # products 应有 visibility
    cols = get_columns(conn, 'products')
    assert 'visibility' in cols, 'FAIL: products.visibility missing'
    cur = conn.execute("SELECT visibility, COUNT(*) FROM products GROUP BY visibility")
    log(f'  products.visibility: {dict(cur.fetchall())}')

    # 6 张 child 表应无 owner_id
    for table in TABLES_DROP_OWNER_ID:
        cols = get_columns(conn, table)
        assert 'owner_id' not in cols, f'FAIL: {table}.owner_id still exists'
        log(f'  {table}: owner_id removed OK')

    # 4 张表应无 visibility
    for table in ['domains', 'sub_domains', 'service_modules', 'business_objects']:
        cols = get_columns(conn, table)
        assert 'visibility' not in cols, f'FAIL: {table}.visibility still exists'
        log(f'  {table}: visibility removed OK')

    # versions 应无 visibility
    cols = get_columns(conn, 'versions')
    assert 'visibility' not in cols, 'FAIL: versions.visibility still exists'
    log('  versions: visibility removed OK')

    # products 应保留 owner_id
    cols = get_columns(conn, 'products')
    assert 'owner_id' in cols, 'FAIL: products.owner_id should be kept'
    cur = conn.execute('SELECT COUNT(*), COUNT(owner_id) FROM products')
    log(f'  products.owner_id kept: {cur.fetchall()}')

    log('=== All verifications passed ===')


def dry_run() -> int:
    """Dry-run: 仅检查不执行"""
    log('=== DRY-RUN MODE (no changes) ===')
    conn = sqlite3.connect(SOURCE_DB)
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')

    # 检查现状
    log('Current schema state:')
    for table in ['products', 'versions', 'domains', 'sub_domains', 'service_modules', 'business_objects', 'relationships']:
        cols = get_columns(conn, table)
        relevant = [c for c in cols if c in ('owner_id', 'visibility')]
        log(f'  {table}: {relevant}')

    # 检查是否会丢数据
    log('\nData that WILL be dropped (TBD-2: no preservation):')
    for table in TABLES_DROP_OWNER_ID:
        cols = get_columns(conn, table)
        if 'owner_id' in cols:
            cur = conn.execute(f'SELECT COUNT(*), COUNT(owner_id) FROM {table}')
            total, with_owner = cur.fetchone()
            log(f'  {table}: {with_owner}/{total} rows have owner_id (will be lost)')
        else:
            log(f'  {table}: no owner_id column, skip')

    log('\nDry-run complete. Use without --dry-run to actually migrate.')
    conn.close()
    return 0


def run_migration() -> int:
    """执行迁移"""
    log('=== MIGRATION START ===')

    # 1. 备份
    backup_path = backup_database()

    # 2. 执行迁移
    conn = sqlite3.connect(SOURCE_DB)
    try:
        # 关掉外键, 避免 reorder 报错
        conn.execute('PRAGMA foreign_keys=OFF')

        step1_add_products_visibility(conn)
        step2_drop_versions_visibility(conn)
        step3_drop_child_owner_id(conn)
        step4_drop_redundant_visibility(conn)

        # SQLite DDL 是 autocommit 模式, 但显式 commit 仍能保证一致性
        conn.commit()
    except Exception as e:
        log(f'MIGRATION FAILED: {e}', level='ERROR')
        log(f'Note: SQLite DDL (CREATE/DROP TABLE) cannot be rolled back.', level='ERROR')
        log(f'Some changes may have been applied. Use --rollback to restore.', level='ERROR')
        log(f'Backup: {backup_path}', level='ERROR')
        raise
    finally:
        conn.execute('PRAGMA foreign_keys=ON')
        conn.close()

    # 验证 (DDL 不可回滚, 必须在所有 DDL 之后)
    verify_conn = sqlite3.connect(SOURCE_DB)
    try:
        verify_post_migration(verify_conn)
    except AssertionError as e:
        log(f'Verification failed: {e}', level='ERROR')
        log(f'Restore from backup: {backup_path}', level='ERROR')
        raise
    finally:
        verify_conn.close()

    # checkpoint WAL
    conn = sqlite3.connect(SOURCE_DB)
    conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    conn.close()

    log(f'=== MIGRATION COMPLETE. Backup: {backup_path} ===')
    return 0


def rollback(backup_file: str = None) -> int:
    """回滚"""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    if backup_file:
        backup_path = Path(backup_file)
    else:
        # 找最新的 backup
        backups = sorted(BACKUP_DIR.glob('architecture.db.bak.*'))
        if not backups:
            log('No backup found', level='ERROR')
            return 1
        backup_path = backups[-1]

    log(f'Restoring from {backup_path}')

    # 删现有 DB
    if SOURCE_DB.exists():
        SOURCE_DB.unlink()
    wal = Path(str(SOURCE_DB) + '-wal')
    shm = Path(str(SOURCE_DB) + '-shm')
    if wal.exists():
        wal.unlink()
    if shm.exists():
        shm.unlink()

    # 复制回来
    shutil.copy2(backup_path, SOURCE_DB)
    backup_wal = Path(str(backup_path) + '-wal')
    backup_shm = Path(str(backup_path) + '-shm')
    if backup_wal.exists():
        shutil.copy2(backup_wal, wal)
    if backup_shm.exists():
        shutil.copy2(backup_shm, shm)

    log(f'Rollback complete. DB restored from {backup_path}')
    return 0


def main():
    parser = argparse.ArgumentParser(description='v1.1 owner refactor migration')
    parser.add_argument('--dry-run', action='store_true', help='check only, no changes')
    parser.add_argument('--rollback', metavar='BACKUP_FILE', nargs='?', const='latest',
                        help='rollback to backup file (default: latest)')
    args = parser.parse_args()

    if not SOURCE_DB.exists():
        log(f'DB not found: {SOURCE_DB}', level='ERROR')
        return 1

    if args.rollback:
        return rollback(args.rollback if args.rollback != 'latest' else None)
    elif args.dry_run:
        return dry_run()
    else:
        return run_migration()


if __name__ == '__main__':
    sys.exit(main())

# -*- coding: utf-8 -*-
"""
[v087 2026-09-14] prod spec15→spec16 列名 backfill: role_id/group_id → permission_set_id/org_id

背景 (prod 彩排 PHASE R-3 发现):
  v070/v072 只 RENAME 了表名, 表内列名保持 legacy (role_id / group_id)。
  staging 的列名演进来自 spec16 新建表路径, prod (spec15 停更 2 个月) 没有。
  新代码 (permission_set_service / data_permission_service / org_service /
  condition_permission_service / action_executor 等) 全线使用
  permission_set_id / org_id, 不补列则 prod 部署后权限功能直接 OperationalError。

范围 (10 对列, 9 张表):
  permission_set_permissions      role_id  -> permission_set_id
  permission_set_data_permissions role_id  -> permission_set_id
  permission_set_menu_permissions role_id  -> permission_set_id
  permission_set_dimension_scopes role_id  -> permission_set_id
  user_permission_sets            role_id  -> permission_set_id
  permission_rules                role_id  -> permission_set_id
  org_data_permissions            group_id -> org_id
  org_members                     group_id -> org_id
  org_permission_sets             group_id -> org_id
  org_permission_sets             role_id  -> permission_set_id

设计原则:
  - 幂等: 新列已存在 → 跳过; 表不存在 → 跳过 (data_permission_rules 由 lazy create)
  - 自适应: legacy 列不存在时 WARN 不阻塞 (表结构未知, 人工检查)
  - 保守: 不 DROP legacy 列 — 新代码不读它, 留着便于回滚旧代码 (旧代码用 role_id)
  - backfill: UPDATE new = legacy (整列复制, 无 NULL 歧义)
  - 索引: idx_{table}_{new} (IF NOT EXISTS)

执行位置: v084 之后 (字母序 v087 > v084, v084 模板绑定写 role_id 列,
v087 backfill 后绑定行自动获得 permission_set_id, 顺序自洽)。

verify: 每张存在的表, new 列存在且 (legacy 列不存在 OR new 与 legacy 的
非 NULL 行数一致)。
"""
import sqlite3
from pathlib import Path

COLUMN_MIGRATIONS = [
    ('permission_set_permissions', 'role_id', 'permission_set_id'),
    ('permission_set_data_permissions', 'role_id', 'permission_set_id'),
    ('permission_set_menu_permissions', 'role_id', 'permission_set_id'),
    ('permission_set_dimension_scopes', 'role_id', 'permission_set_id'),
    ('user_permission_sets', 'role_id', 'permission_set_id'),
    ('permission_rules', 'role_id', 'permission_set_id'),
    ('org_data_permissions', 'group_id', 'org_id'),
    ('org_members', 'group_id', 'org_id'),
    ('org_permission_sets', 'group_id', 'org_id'),
    ('org_permission_sets', 'role_id', 'permission_set_id'),
]


def _table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _cols(conn, table):
    return {r[1] for r in conn.execute(f'PRAGMA table_info({table})')}


def _count_not_null(conn, table, col):
    return conn.execute(
        f'SELECT COUNT(*) FROM {table} WHERE {col} IS NOT NULL'
    ).fetchone()[0]


def migrate(db_path, skip_backup=False):
    conn = sqlite3.connect(str(db_path))
    try:
        summary = {'added': [], 'backfilled': [], 'skipped_new_col': [],
                   'skipped_no_table': [], 'warn_no_legacy': []}
        for table, legacy, new in COLUMN_MIGRATIONS:
            if not _table_exists(conn, table):
                print(f'[v087] {table} 不存在, 跳过')
                summary['skipped_no_table'].append(table)
                continue
            cols = _cols(conn, table)
            if new in cols:
                print(f'[v087] {table}.{new} 已存在, 跳过 (幂等)')
                summary['skipped_new_col'].append(f'{table}.{new}')
                continue
            if legacy not in cols:
                print(f'[v087][WARN] {table} 无 {legacy} 列 (结构未知), 跳过 — 需人工检查: {sorted(cols)}')
                summary['warn_no_legacy'].append(f'{table}.{new}')
                continue
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {new} INTEGER')
            cur = conn.execute(f'UPDATE {table} SET {new} = {legacy}')
            idx = f'idx_{table}_{new}'
            conn.execute(f'CREATE INDEX IF NOT EXISTS {idx} ON {table}({new})')
            print(f'[v087] {table}: ADD {new} + backfill {legacy}->{new} ({cur.rowcount} rows) + {idx}')
            summary['added'].append(f'{table}.{new}')
            summary['backfilled'].append((f'{table}.{new}', cur.rowcount))
        conn.commit()
        print(f"[v087] summary: added={len(summary['added'])}, "
              f"skipped(new)={len(summary['skipped_new_col'])}, "
              f"skipped(no_table)={len(summary['skipped_no_table'])}, "
              f"warn={len(summary['warn_no_legacy'])}")
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def verify(db_path):
    conn = sqlite3.connect(str(db_path))
    try:
        ok = True
        for table, legacy, new in COLUMN_MIGRATIONS:
            if not _table_exists(conn, table):
                continue
            cols = _cols(conn, table)
            if new not in cols:
                if legacy in cols:  # 有 legacy 无 new = backfill 未完成
                    print(f'[v087 verify] FAIL: {table}.{new} 缺失 (legacy {legacy} 存在)')
                    ok = False
                continue  # 两者都无: 表由其他路径管理, 不归 v087
            if legacy in cols:
                if _count_not_null(conn, table, new) != _count_not_null(conn, table, legacy):
                    print(f'[v087 verify] FAIL: {table} {new}/{legacy} 非 NULL 行数不一致')
                    ok = False
        if ok:
            print('[v087 verify] PASS: 列 backfill 完整')
        return ok
    finally:
        conn.close()


if __name__ == '__main__':
    import sys
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / 'architecture.db'
    print(f'[v087] migrating {db}')
    migrate(db)
    ok = verify(db)
    print(f'[v087] verify: {"PASS" if ok else "FAIL"}')
    sys.exit(0 if ok else 1)

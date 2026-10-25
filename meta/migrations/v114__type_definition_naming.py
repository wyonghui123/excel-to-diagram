# -*- coding: utf-8 -*-
"""[v114] 命名收口：消费方列去掉 `sales_` 前缀

依据: docs/superpowers/specs/2026-10-25-type-definition-generalization-spec.md §8 命名收口

类型字典落地后，消费方引用的是通用的 type_definitions 行，列名不应再带
`sales_` 前缀；否则同一份元模型换个域（采购 / 调拨）就得再造一套列名。

本迁移做两件事（幂等）:
  1. `control_parameter_values` / `sales_line_type_assignments` 的
     `sales_document_type_id` → `document_type_id`
  2. 同两张表的 `sales_line_type_id` → `line_type_id`

SQLite 3.25+ 的 `ALTER TABLE ... RENAME COLUMN` 会同步改写索引与 FK 定义，
故无需重建表；重复执行时按「旧列存在且新列不存在」判定，天然幂等。

表名 / 对象名保持不变（`sales_line_type_assignments` 等），一并在后续
「把对象本身泛化」时处理，避免本次同时动对象标识、菜单与权限。

回滚: 反向改名。
"""
import sqlite3
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

RENAMES = (
    ('control_parameter_values', 'sales_document_type_id', 'document_type_id'),
    ('control_parameter_values', 'sales_line_type_id', 'line_type_id'),
    ('sales_line_type_assignments', 'sales_document_type_id', 'document_type_id'),
    ('sales_line_type_assignments', 'sales_line_type_id', 'line_type_id'),
)


def _columns(conn: sqlite3.Connection, table: str) -> set:
    return {r[1] for r in conn.execute('PRAGMA table_info(%s)' % table).fetchall()}


def _rename(conn: sqlite3.Connection, table: str, old: str, new: str) -> str:
    cols = _columns(conn, table)
    if not cols:                      # 表不存在：新库由 YAML 直接建新列名
        return 'skip_missing_table'
    if new in cols and old not in cols:
        return 'skip_done'
    if old not in cols:
        return 'skip_no_old'
    conn.execute('ALTER TABLE %s RENAME COLUMN %s TO %s' % (table, old, new))
    return 'renamed'


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v114] DB 不存在: %s' % db_path)
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        print('[v114] 开始: 消费方列名去 sales_ 前缀')
        conn.execute('PRAGMA foreign_keys = OFF')
        for table, old, new in RENAMES:
            result = _rename(conn, table, old, new)
            print('  - [%s] %s.%s → %s' % (result.upper(), table, old, new))
        conn.commit()
        print('  - [DONE] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v114] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v114 verify] DB 不存在: %s' % db_path)
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        ok = True
        for table, old, new in RENAMES:
            cols = _columns(conn, table)
            if not cols:
                continue
            if old in cols or new not in cols:
                print('[v114 verify] FAIL: %s 列名未收口（old=%s, new=%s）'
                      % (table, old in cols, new in cols))
                ok = False
        if ok:
            print('[v114 verify] OK: 两表列名已收口，旧列名不存在')
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v114] DB 不存在: %s' % db_path)
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        print('[v114] rollback: 列名恢复 sales_ 前缀')
        conn.execute('PRAGMA foreign_keys = OFF')
        for table, old, new in RENAMES:
            result = _rename(conn, table, new, old)
            print('  - [%s] %s.%s → %s' % (result.upper(), table, new, old))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print('[v114] rollback 失败: %s' % e)
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    from meta.core.db_path import get_meta_db_path
    target = get_meta_db_path()
    print('DB: %s' % target)
    print('migrate -> %s' % migrate(target))
    print('verify  -> %s' % verify(target))

# -*- coding: utf-8 -*-
"""[v115] 对象级泛化：三个对象去掉 `sales_` 前缀

依据: docs/superpowers/specs/2026-10-25-type-definition-generalization-spec.md §9 对象级泛化

v114 只收了列名，对象标识仍是销售专属名。类型字典是通用基础设施，
对象名应只表达「单据类型 / 行类型」这一层语义，不再焊死业务域：

  sales_document_type      → document_type      （视图，表名 sales_document_types → document_types）
  sales_line_type          → line_type          （视图，表名 sales_line_types   → line_types）
  sales_line_type_assignment → line_type_assignment（实表，表名 sales_line_type_assignments → line_type_assignments）

本迁移处理**物理层**（YAML 侧改名已在同批提交完成）:
  1. `sales_line_type_assignments` → `line_type_assignments`（ALTER TABLE RENAME TO，
     SQLite 会保留索引与 FK 定义）
  2. DROP VIEW `sales_document_types` / `sales_line_types`
     —— 新视图 `document_types` / `line_types` 由下一次 schema sync 按新 YAML 建出

幂等: 目标表已存在 / 旧表不存在 / 旧视图不存在时均跳过；两者共存视为冲突，
不猜测哪边是真身，仅告警并保留现状。

回滚: 表名改回，并按旧切片条件重建两个旧视图。

注意: 迁移时 `PRAGMA foreign_keys = OFF`（与 v114 一致），避免改名过程中
子表 FK 校验误伤。
"""
import sqlite3
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

OLD_TABLE = 'sales_line_type_assignments'
NEW_TABLE = 'line_type_assignments'

LEGACY_VIEWS = {
    'sales_document_types': """
        CREATE VIEW sales_document_types AS
        SELECT id, code, name,
               document_category AS category,
               default_type_id AS default_line_type_id,
               number_sequence_id,
               status, description, created_at
        FROM type_definitions
        WHERE scope_bo = 'sales_order' AND level = 'header'
    """,
    'sales_line_types': """
        CREATE VIEW sales_line_types AS
        SELECT id, code, name,
               line_category AS category,
               status, description, created_at
        FROM type_definitions
        WHERE scope_bo = 'sales_order' AND level = 'line'
    """,
}


def _objects(conn: sqlite3.Connection) -> dict:
    """name -> type（table / view）"""
    rows = conn.execute(
        "SELECT name, type FROM sqlite_master WHERE type IN ('table', 'view')"
    ).fetchall()
    return {r[0]: r[1] for r in rows}


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print('[v115] DB 不存在: %s' % db_path)
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        print('[v115] 开始: 对象标识去 sales_ 前缀')
        conn.execute('PRAGMA foreign_keys = OFF')
        objs = _objects(conn)

        if objs.get(NEW_TABLE) == 'table' and objs.get(OLD_TABLE) == 'table':
            print('  - [WARN] %s 与 %s 同时存在，跳过改名（需人工确认）'
                  % (OLD_TABLE, NEW_TABLE))
        elif objs.get(OLD_TABLE) == 'table':
            conn.execute('ALTER TABLE %s RENAME TO %s' % (OLD_TABLE, NEW_TABLE))
            print('  - [RENAMED] %s → %s' % (OLD_TABLE, NEW_TABLE))
        elif objs.get(NEW_TABLE) == 'table':
            print('  - [SKIP_DONE] %s 已存在' % NEW_TABLE)
        else:
            print('  - [SKIP_MISSING_TABLE] %s / %s 均不存在（新库由 YAML 建表）'
                  % (OLD_TABLE, NEW_TABLE))

        for view in LEGACY_VIEWS:
            if objs.get(view) == 'view':
                conn.execute('DROP VIEW IF EXISTS %s' % view)
                print('  - [DROP_VIEW] %s' % view)
            elif objs.get(view) == 'table':
                print('  - [WARN] %s 是表不是视图，保留不动' % view)
            else:
                print('  - [SKIP_NO_VIEW] %s' % view)

        conn.commit()
        print('  - [DONE] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v115] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v115 verify] DB 不存在: %s' % db_path)
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        objs = _objects(conn)
        ok = True
        if objs.get(OLD_TABLE) == 'table':
            print('[v115 verify] FAIL: 旧表 %s 仍存在' % OLD_TABLE)
            ok = False
        if objs.get(NEW_TABLE) != 'table' and objs.get(OLD_TABLE) != 'table':
            print('[v115 verify] WARN: 两表都不存在（空库可接受）')
        for view in LEGACY_VIEWS:
            if objs.get(view):
                print('[v115 verify] FAIL: 旧视图 %s 仍存在' % view)
                ok = False
        if ok:
            print('[v115 verify] OK: 实表已改名，旧视图已清理')
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v115] DB 不存在: %s' % db_path)
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        print('[v115] rollback: 对象标识恢复 sales_ 前缀')
        conn.execute('PRAGMA foreign_keys = OFF')
        objs = _objects(conn)
        if objs.get(NEW_TABLE) == 'table' and objs.get(OLD_TABLE) is None:
            conn.execute('ALTER TABLE %s RENAME TO %s' % (NEW_TABLE, OLD_TABLE))
            print('  - [RENAMED] %s → %s' % (NEW_TABLE, OLD_TABLE))
        else:
            print('  - [SKIP] 表名无需回滚')
        for view, sql in LEGACY_VIEWS.items():
            if objs.get(view) is None:
                conn.execute(sql)
                print('  - [CREATE_VIEW] %s' % view)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print('[v115] rollback 失败: %s' % e)
        return False
    finally:
        conn.close()


if __name__ == '__main__':
    from meta.core.db_path import get_meta_db_path
    target = get_meta_db_path()
    print('DB: %s' % target)
    print('migrate -> %s' % migrate(target))
    print('verify  -> %s' % verify(target))

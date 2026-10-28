# -*- coding: utf-8 -*-
"""[v146] 重建 line_types 视图：暴露 delivery_relevant

依据:
  docs/superpowers/specs/2026-10-28-sales-order-fulfillment-status-writeback-spec.md
    §5.1.1 行类型配置（delivery_relevant 落在 type_definitions）
    §4.8 INV-3（不存在 delivery_relevant=false 且有 delivery 计划行）

背景:
  v145 已给 type_definitions 加列 delivery_relevant 并回填；
  但 line_type 是 VIEW（table_name=line_types），SchemaMigrator 只对表做
  ALTER TABLE，不会重建视图 → 数据库里的视图定义仍是旧 SQL（缺该列），
  而 meta/schemas/line_type.yaml 的 view_definition 已更新。
  本迁移把视图定义同步到 YAML 口径。

视图定义（必须与 meta/schemas/line_type.yaml 的 view_definition 逐字一致）:
  SELECT id, code, name,
         line_category AS category,
         COALESCE(delivery_relevant, 1) AS delivery_relevant,
         status, description, created_at
  FROM type_definitions
  WHERE level = 'line'

幂等:
  每次执行都 DROP + CREATE，重复执行结果一致（视图定义收敛到同一份 SQL）。

回滚:
  用旧定义（无 delivery_relevant）重建视图。表列不受影响。
"""
import sqlite3
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

VIEW_NAME = 'line_types'
BASE_TABLE = 'type_definitions'
BASE_COLUMN = 'delivery_relevant'

#: 新视图定义（与 meta/schemas/line_type.yaml 的 view_definition 一致）
NEW_VIEW_SQL = """CREATE VIEW {0} AS
SELECT id, code, name,
       line_category AS category,
       COALESCE(delivery_relevant, 1) AS delivery_relevant,
       status, description, created_at
FROM type_definitions
WHERE level = 'line'""".format(VIEW_NAME)

#: 旧视图定义（v145 之前的数据库实际定义）
OLD_VIEW_SQL = """CREATE VIEW {0} AS
SELECT id, code, name,
       line_category AS category,
       status, description, created_at
FROM type_definitions
WHERE level = 'line'""".format(VIEW_NAME)


def _table_exists(conn, name):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _object_type(conn, name):
    row = conn.execute(
        "SELECT type FROM sqlite_master WHERE name=?", (name,)
    ).fetchone()
    return row[0] if row else None


def _view_columns(conn, name):
    rows = conn.execute("PRAGMA table_info(%s)" % name).fetchall()
    return [r[1] for r in rows]


def _check_inv3(conn):
    """INV-3：不存在 delivery_relevant=false 且仍有未取消 delivery 计划行的行。"""
    sql = """
        SELECT COUNT(*) FROM sales_order_schedules s
        JOIN sales_order_lines l ON l.id = s.line_id
        JOIN type_definitions d ON d.id = l.line_type_id
        WHERE s.schedule_kind = 'delivery'
          AND s.status <> 'cancelled'
          AND COALESCE(d.delivery_relevant, 1) = 0
    """
    try:
        return conn.execute(sql).fetchone()[0]
    except sqlite3.OperationalError:
        return 0


def migrate(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v146] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v146] 开始: 重建 %s 视图（暴露 %s）' % (VIEW_NAME, BASE_COLUMN))

        if not _table_exists(conn, BASE_TABLE):
            print('  - [SKIP_MISSING] 基表 %s 不存在，跳过' % BASE_TABLE)
            return True

        cols = [r[1] for r in conn.execute('PRAGMA table_info(%s)' % BASE_TABLE)]
        if BASE_COLUMN not in cols:
            print('  - [FAIL] 基表 %s 缺列 %s（v145 未执行？）' % (BASE_TABLE, BASE_COLUMN))
            return False

        obj_type = _object_type(conn, VIEW_NAME)
        if obj_type == 'table':
            print('  - [FAIL] %s 是表不是视图，需人工处理' % VIEW_NAME)
            return False
        if obj_type == 'view':
            conn.execute('DROP VIEW IF EXISTS %s' % VIEW_NAME)
            print('  - [DROP_VIEW] %s' % VIEW_NAME)
        else:
            print('  - [NO_VIEW] %s 不存在，直接创建' % VIEW_NAME)

        conn.execute(NEW_VIEW_SQL)
        print('  - [CREATE_VIEW] %s' % VIEW_NAME)

        violations = _check_inv3(conn)
        if violations:
            print('  - [INV-3 FAIL] %s 行违反 delivery_relevant 约束' % violations)
            conn.rollback()
            return False
        print('  - [INV-3 PASS]')

        conn.commit()
        print('  - [DONE] 迁移提交完成')
        return True
    except Exception as e:
        conn.rollback()
        print('[v146] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v146 verify] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        ok = True
        if _object_type(conn, VIEW_NAME) != 'view':
            print('[v146 verify] %s 不是视图' % VIEW_NAME)
            return False

        cols = _view_columns(conn, VIEW_NAME)
        expected = ['id', 'code', 'name', 'category', BASE_COLUMN,
                    'status', 'description', 'created_at']
        if cols != expected:
            print('[v146 verify] 视图列不匹配: %s != %s' % (cols, expected))
            ok = False

        rows = conn.execute(
            'SELECT code, %s FROM %s ORDER BY code' % (BASE_COLUMN, VIEW_NAME)
        ).fetchall()
        print('[v146 verify] 视图数据 (%d 行): %s' % (len(rows), rows))
        if not rows:
            print('[v146 verify] 视图为空（type_definitions 无 level=line 记录？）')
            ok = False

        if _check_inv3(conn):
            print('[v146 verify] INV-3 违反')
            ok = False

        print('[v146 verify] %s' % ('PASS' if ok else 'FAIL'))
        return ok
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v146 rollback] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if _object_type(conn, VIEW_NAME) != 'view':
            print('[v146 rollback] %s 不是视图，跳过' % VIEW_NAME)
            return True
        conn.execute('DROP VIEW IF EXISTS %s' % VIEW_NAME)
        conn.execute(OLD_VIEW_SQL)
        conn.commit()
        print('[v146 rollback] 已恢复旧视图定义（无 %s）' % BASE_COLUMN)
        return True
    except Exception as e:
        conn.rollback()
        print('[v146 rollback] 失败: %s' % e)
        return False
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(get_meta_db_path())
    print('DB: %s' % db)

    if '--verify' in sys.argv:
        sys.exit(0 if verify(db) else 1)
    elif '--rollback' in sys.argv:
        sys.exit(0 if rollback(db) else 1)
    else:
        if not migrate(db):
            sys.exit(1)
        sys.exit(0 if verify(db) else 1)

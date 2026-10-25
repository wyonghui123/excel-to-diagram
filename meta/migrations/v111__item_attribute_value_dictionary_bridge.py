# -*- coding: utf-8 -*-
"""[v111] item_attribute_values 接属性字典（外键 + 类型化值列补齐 + 存量回填）

背景:
  属性字典（v110）落地后，物料分层参数表仍以自由文本 attr_code 标识参数 ——
  与字典是两套编码，类型、值域、状态口径都无从校验。本迁移补上桥接列:

  1. `attribute_id`：字典引用（→ attribute_definitions.id）。
  2. `value_date` / `value_datetime`：平台值表模板的五列口径要求（原表只有
     text/number/boolean，date/datetime 类属性无处落值）。表头既已声明
     "datetime 类参数按同一映射增列（ADD COLUMN，成本低）"，此处兑现。
  3. 存量回填：按 `attr_code = attribute_definitions.code AND tenant_id = 0`
     回填 attribute_id。素材是平台级主数据，只认平台层定义。
     匹配不到的编码只输出对账清单，**不自动造定义** —— 类型与值域无法从编码反推。

已知限制（SQLite）:
  · ALTER TABLE 只能加列，不能补 FK 约束 ⇒ 存量库的 attribute_id 没有数据库级
    外键，靠应用层守卫（ItemAttributeValueService）保证引用有效；新建库由
    schema 同步生成真外键。
  · 保留 attr_code 作为物理唯一键（L0/L2 partial unique 依赖它），不在此换键 ——
    换键须重建索引，收益不足以抵消风险；两列一致性由应用层校验。

幂等: 缺列才 ADD；回填只碰 attribute_id IS NULL 的行；重复执行输出 [SKIP]。

回滚: SQLite 不支持安全 DROP COLUMN，downgrade 仅告警，不真删列。
"""
import sqlite3
from pathlib import Path

TABLE = 'item_attribute_values'
DEFINITION_TABLE = 'attribute_definitions'

#: 需要补齐的列: (列名, 建表声明) —— date 在平台归一为 DATETIME
MISSING_COLUMNS = [
    ('attribute_id', 'INTEGER'),
    ('value_date', 'DATETIME'),
    ('value_datetime', 'DATETIME'),
]

BACKFILL_SQL = f"""
UPDATE {TABLE}
   SET attribute_id = (
        SELECT d.id FROM {DEFINITION_TABLE} d
         WHERE d.code = {TABLE}.attr_code AND d.tenant_id = 0
       )
 WHERE attribute_id IS NULL
   AND EXISTS (
        SELECT 1 FROM {DEFINITION_TABLE} d
         WHERE d.code = {TABLE}.attr_code AND d.tenant_id = 0
       )
"""


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    if not _table_exists(conn, table):
        return False
    return any(row[1] == column
               for row in conn.execute(f'PRAGMA table_info({table})').fetchall())


def _add_column_if_missing(conn, column: str, decl: str) -> bool:
    if _column_exists(conn, TABLE, column):
        print(f'  - {TABLE}.{column} 已存在, 跳过')
        return False
    conn.execute(f'ALTER TABLE {TABLE} ADD COLUMN {column} {decl}')
    print(f'  [ADD COLUMN] {TABLE}.{column} {decl}')
    return True


def _do_columns(conn: sqlite3.Connection) -> None:
    for column, decl in MISSING_COLUMNS:
        _add_column_if_missing(conn, column, decl)


def _do_backfill(conn: sqlite3.Connection) -> None:
    if not _column_exists(conn, TABLE, 'attribute_id'):
        print('  - [SKIP] attribute_id 列尚未就绪, 跳过回填')
        return
    cur = conn.execute(BACKFILL_SQL)
    if cur.rowcount:
        print(f'  [BACKFILL] 回填 attribute_id: {cur.rowcount} 行')
    else:
        print('  - [SKIP] 无待回填行')


def _report(conn: sqlite3.Connection) -> None:
    """只读对账: 未匹配编码 + 编码与字典不一致的行。"""
    total = conn.execute(f'SELECT COUNT(*) FROM {TABLE}').fetchone()[0]
    linked = conn.execute(
        f'SELECT COUNT(*) FROM {TABLE} WHERE attribute_id IS NOT NULL').fetchone()[0]
    print(f'  - 存量 {total} 行, 已关联字典 {linked} 行')

    if total == 0:
        print('  - [OK] 表为空, 无存量需对账')
        return

    unmatched = conn.execute(
        f'SELECT attr_code, COUNT(*) FROM {TABLE} WHERE attribute_id IS NULL '
        'GROUP BY attr_code ORDER BY attr_code'
    ).fetchall()
    if unmatched:
        print(f'  - [TODO] {len(unmatched)} 个编码尚无平台层字典定义（需人工补定义）:')
        for code, cnt in unmatched:
            print(f'      · {code}  ({cnt} 行)')

    mismatched = conn.execute(
        f'SELECT v.id, v.attr_code, d.code FROM {TABLE} v '
        f'JOIN {DEFINITION_TABLE} d ON d.id = v.attribute_id '
        'WHERE v.attr_code != d.code ORDER BY v.id LIMIT 20'
    ).fetchall()
    if mismatched:
        print(f'  - [WARN] {len(mismatched)} 行 attr_code 与字典编码不一致（不自动改写）:')
        for row_id, attr_code, code in mismatched:
            print(f'      · #{row_id}: attr_code={attr_code} 定义 code={code}')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v111] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v111] 开始: item_attribute_values 接属性字典')
        if not _table_exists(conn, TABLE):
            print(f'  - [SKIP] {TABLE} 不存在 (由 schema 同步建表后再执行本迁移)')
            conn.commit()
            return True
        _do_columns(conn)
        _do_backfill(conn)
        _report(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v111] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, TABLE):
            print(f'[v111 verify] FAIL: {TABLE} 不存在')
            return False

        for column, _ in MISSING_COLUMNS:
            if not _column_exists(conn, TABLE, column):
                print(f'[v111 verify] FAIL: 缺列 {TABLE}.{column}')
                return False

        # 可匹配的存量行必须已回填（未匹配的编码属于数据治理待办，不算迁移失败）
        if _table_exists(conn, DEFINITION_TABLE):
            left = conn.execute(
                f'SELECT COUNT(*) FROM {TABLE} v WHERE v.attribute_id IS NULL '
                f'AND EXISTS (SELECT 1 FROM {DEFINITION_TABLE} d '
                'WHERE d.code = v.attr_code AND d.tenant_id = 0)'
            ).fetchone()[0]
            if left:
                print(f'[v111 verify] FAIL: {left} 行可匹配但未回填')
                return False

            orphans = conn.execute(
                f'SELECT COUNT(*) FROM {TABLE} v '
                f'WHERE v.attribute_id IS NOT NULL AND NOT EXISTS '
                f'(SELECT 1 FROM {DEFINITION_TABLE} d WHERE d.id = v.attribute_id)'
            ).fetchone()[0]
            if orphans:
                print(f'[v111 verify] FAIL: {orphans} 行 attribute_id 指向不存在的定义')
                return False

        print('[v111 verify] OK: 桥接列齐全，可匹配行均已回填，无悬空引用')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v111] DB 不存在: {db_path}')
        return False
    print('[v111] 回滚: SQLite 不支持安全 DROP COLUMN，保留 attribute_id / '
          'value_date / value_datetime 三列（加列本身不影响旧读写路径）')
    return True


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v111] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v111] verify: {"PASS" if _v else "FAIL"}')

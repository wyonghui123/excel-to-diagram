# -*- coding: utf-8 -*-
"""[v122 2026-10-25] 销售订单行 结构展开字段（P1）

背景:
  P1 让「父行 + 选配结构」能落成一棵订单行树，需要四个字段承载层次与金额归属：

    configuration_id  展开来源的配置实例（只有父行有值）
    parent_line_id    上级订单行（只有子行有值；自引用）
    component_no      配置实例的组件路径键（L0010.L0020），同一父行内唯一
    pricing_mode      金额归属：standalone / bundle_price / component_price /
                      base_plus_option，默认 standalone

  口径见 meta/schemas/sales_order_line.yaml 头注释 ⑥ / ⑦：
  层级只用 parent_line_id 表达，line_no 仍是纯数字，component_no 只做对账键。

索引:
    idx_sales_order_line_parent         按父行找子行
    idx_sales_order_line_configuration  按配置实例反查订单行
    uidx_sales_order_line_component     (parent_line_id, component_no) 唯一

  SQLite 的唯一索引把 NULL 视为互不相同，故未展开行（parent_line_id 为空）
  不参与该约束，手工新建的行可继续留空。

幂等:
  列用 PRAGMA table_info 探测，已存在则跳过；索引 CREATE INDEX IF NOT EXISTS。
  重复执行只输出 [SKIP]。

回滚:
  **保留**新增列与索引。SQLite 删列需重建表，风险大于收益；P1 之后
  四个字段是订单行树的唯一载体，回滚会造成数据不可解释。
"""
import sqlite3
from pathlib import Path

# (列名, 列定义)
COLUMNS = (
    ('configuration_id', 'INTEGER REFERENCES configurations(id)'),
    ('parent_line_id', 'INTEGER REFERENCES sales_order_lines(id)'),
    ('component_no', 'VARCHAR(200)'),
    ('pricing_mode', "VARCHAR(30) NOT NULL DEFAULT 'standalone'"),
)

# (索引名, 表达式, 是否唯一)
INDEXES = (
    ('idx_sales_order_line_parent', '(parent_line_id)', False),
    ('idx_sales_order_line_configuration', '(configuration_id)', False),
    ('uidx_sales_order_line_component', '(parent_line_id, component_no)', True),
)

TABLE = 'sales_order_lines'


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(conn: sqlite3.Connection) -> dict:
    return {row[1]: row for row in conn.execute(f'PRAGMA table_info({TABLE})')}


def _do_columns(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TABLE):
        print(f'  - [SKIP] 表 {TABLE} 不存在, 跳过列写入')
        return

    existing = _columns(conn)
    added = 0
    for column, definition in COLUMNS:
        if column in existing:
            print(f'  - [SKIP] {TABLE}.{column} 已存在')
            continue
        conn.execute(f'ALTER TABLE {TABLE} ADD COLUMN {column} {definition}')
        added += 1
        print(f'  - [NEW] {TABLE}.{column}')
    print(f'  - [SUMMARY] columns: +{added} 新增')


def _do_indexes(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, TABLE):
        print(f'  - [SKIP] 表 {TABLE} 不存在, 跳过索引写入')
        return

    added = 0
    for name, expression, unique in INDEXES:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
            (name,)).fetchone()
        if exists:
            print(f'  - [SKIP] 索引 {name} 已存在')
            continue
        keyword = 'UNIQUE INDEX' if unique else 'INDEX'
        conn.execute(
            f'CREATE {keyword} IF NOT EXISTS {name} ON {TABLE}{expression}')
        added += 1
        print(f'  - [NEW] 索引 {name} {expression}')
    print(f'  - [SUMMARY] indexes: +{added} 新增')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v122] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v122] 开始: 销售订单行 结构展开字段')
        _do_columns(conn)
        _do_indexes(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v122] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言四列就位、pricing_mode 默认 standalone、三个索引齐备。"""
    if not db_path.exists():
        print('[v122 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, TABLE):
            print(f'[v122 verify] FAIL: 表 {TABLE} 不存在')
            return False

        info = _columns(conn)
        for column, _definition in COLUMNS:
            if column not in info:
                print(f'[v122 verify] FAIL: 缺列 {TABLE}.{column}')
                return False

        for column in ('configuration_id', 'parent_line_id', 'component_no'):
            if info[column][3] != 0:
                print(f'[v122 verify] FAIL: {TABLE}.{column} 应为可空')
                return False

        pricing = info['pricing_mode']
        if pricing[3] != 1 or str(pricing[4]).strip("'\"") != 'standalone':
            print(f'[v122 verify] FAIL: pricing_mode 默认值异常 '
                  f'{pricing[4]!r} / notnull={pricing[3]}')
            return False

        for name, _expression, _unique in INDEXES:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name=?",
                (name,)).fetchone()
            if not row:
                print(f'[v122 verify] FAIL: 缺索引 {name}')
                return False

        unique_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            ('uidx_sales_order_line_component',)).fetchone()
        if not unique_row or 'UNIQUE' not in (unique_row[0] or '').upper():
            print('[v122 verify] FAIL: 组件号索引不是 UNIQUE')
            return False

        print('[v122 verify] OK: 展开字段 4 列 + 索引 3 条（组件号唯一）')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """列与索引保留（删列需重建表；字段是订单行树的唯一载体）。"""
    print('[v122] downgrade: 展开字段与索引保留，无删除动作')
    return True


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v122] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v122] verify: {"PASS" if _v else "FAIL"}')

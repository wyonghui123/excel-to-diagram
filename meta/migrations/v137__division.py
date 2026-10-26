# -*- coding: utf-8 -*-
"""[v137] 销售订单主数据补齐 B：产品组 division 种子 / 回填 / 菜单权限

依据:
  docs/superpowers/specs/2026-10-26-sales-order-master-data-gap-spec.md
    §3.4 种子与存量回填 / §3.5 菜单与权限

背景:
  订单抬头 `sales_order.division_code` 原先只存自由字符串，本次把它绑定到
  薄主数据 `division`（divisions 表由 YAML + sync_schema 建，本迁移不建表）。
  `division` 是 SAP division 语义的扁平受控值集：无层级、无带出链、不参与定价；
  **不是**物料分类 item_group。

本迁移只做 YAML 管不到的事:
  1. 断言 divisions 表存在（由 sync_schema 建）
  2. 种子 DEFAULT / 默认产品组 / active（按 code 幂等）
  3. 回填 sales_orders.division_code 的去重非空值 → divisions（name = code, active）
  4. 输出「存量值不符合 code 模式」的清单，不阻断
  5. 菜单 + 权限种子（先查后插，重复执行 SKIP）
  6. 补 YAML 已声明的唯一索引 uidx_division_code（缺失时补齐）

权限口径:
  仓库主数据惯例是双段式 {object_id}:{object_id}_{action}，5 个平台标准动作
  create / read / update / delete / list（与 v124 / v127 / v132 同口径）。
  设计稿里的 `division:view` 是简写，实际落 `division:division_read`。

幂等:
  种子 / 回填用 `INSERT ... WHERE NOT EXISTS` 按 code 判重；permissions 用
  INSERT OR IGNORE；menus / menu_permissions 先按 menu_code 判存在，缺失才 INSERT。
  重复执行只输出 [SKIP]。

回滚:
  删除菜单（menus + menu_permissions）与本次补建的索引；
  **保留** divisions 表与数据（由 YAML 声明），**保留** permissions 行
  —— 可能已被角色授予，删除有风险。
"""
import json
import re
import sqlite3
from pathlib import Path

OBJECT_ID = 'division'
MENU_CODE = 'division-list'
PARENT_MENU = 'master-data'

TABLE = 'divisions'
ORDER_TABLE = 'sales_orders'
ORDER_COLUMN = 'division_code'
UIDX_CODE = 'uidx_division_code'

#: 与 division.yaml 的 code.pattern 同口径
CODE_PATTERN = re.compile(r'^[A-Za-z0-9_]{1,10}$')

#: 保证下拉至少有一行可用
SEED_CODE = 'DEFAULT'
SEED_NAME = '默认产品组'

_RANK = ('create', 'read', 'update', 'delete', 'list')

_ACTION_LABEL = {
    'create': '新建', 'read': '查看', 'update': '修改',
    'delete': '删除', 'list': '查询',
}

PERMISSIONS = tuple(
    (f'{OBJECT_ID}:{OBJECT_ID}_{a}', f'{_ACTION_LABEL[a]}产品组',
     OBJECT_ID, a)
    for a in _RANK
)

MENUS = (
    {
        'menu_code': MENU_CODE,
        'menu_name': '产品组',
        'menu_path': '/divisions',
        'page_type': 'object_list',
        'primary_object_type': OBJECT_ID,
        'object_types': [OBJECT_ID],
        'bo_bindings': [
            {'bo_id': OBJECT_ID, 'role': 'primary', 'include_actions': list(_RANK)},
        ],
        'required_permissions': [code for code, _n, _r, _a in PERMISSIONS],
        'parent_menu': PARENT_MENU,
        'icon': 'List',
        'color': '#0ea5e9',
        'description': '产品组字典：编码、名称与启用状态',
        'sort_order': 86,
        'is_active': 1,
        'show_in_sidebar': 0,
        'auto_generated': 0,
        'data_permission_hint': {
            'resource_types': [OBJECT_ID],
            'message': '建议分配产品组数据权限',
        },
    },
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _index_sql(conn: sqlite3.Connection, name: str):
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (name,)
    ).fetchone()
    return row[0] if row else None


def _column_info(conn: sqlite3.Connection, table: str) -> dict:
    if not _table_exists(conn, table):
        return {}
    return {row[1]: row for row in conn.execute(f'PRAGMA table_info({table})')}


def _do_seed(conn: sqlite3.Connection) -> None:
    cur = conn.execute(
        f"INSERT INTO {TABLE} (code, name, status, created_at) "
        f"SELECT ?, ?, 'active', datetime('now') "
        f"WHERE NOT EXISTS (SELECT 1 FROM {TABLE} WHERE code = ?)",
        (SEED_CODE, SEED_NAME, SEED_CODE),
    )
    if cur.rowcount:
        print(f'  - [NEW] 种子 {SEED_CODE} ({SEED_NAME})')
    else:
        print(f'  - [SKIP] 种子 {SEED_CODE} 已存在')


def _do_backfill(conn: sqlite3.Connection) -> None:
    """去重非空 division_code → divisions；name = code，状态 active。"""
    if not _table_exists(conn, ORDER_TABLE) \
            or ORDER_COLUMN not in _column_info(conn, ORDER_TABLE):
        print(f'  - [SKIP] {ORDER_TABLE}.{ORDER_COLUMN} 不存在，跳过存量回填')
        return

    rows = conn.execute(
        f"SELECT DISTINCT TRIM({ORDER_COLUMN}) AS code FROM {ORDER_TABLE} "
        f"WHERE {ORDER_COLUMN} IS NOT NULL AND TRIM({ORDER_COLUMN}) <> ''"
    ).fetchall()
    if not rows:
        print('  - [SKIP] 无存量 division_code 需要回填')
        return

    inserted = 0
    for (code,) in rows:
        cur = conn.execute(
            f"INSERT INTO {TABLE} (code, name, status, created_at) "
            f"SELECT ?, ?, 'active', datetime('now') "
            f"WHERE NOT EXISTS (SELECT 1 FROM {TABLE} WHERE code = ?)",
            (code, code, code),
        )
        if cur.rowcount:
            inserted += 1
            print(f'  - [NEW] 回填 {code} (name={code}, active)')

    if inserted:
        print(f'  - [SUMMARY] 存量回填: +{inserted} 行（共 {len(rows)} 个去重值）')
    else:
        print(f'  - [SKIP] {len(rows)} 个存量值均已有对应 divisions 行')

    invalid = [code for (code,) in rows if not CODE_PATTERN.fullmatch(code)]
    if invalid:
        print(f'  - [CHECK] 存量 division_code 中 {len(invalid)} 个值不符合 '
              f'code 模式（不阻断，建议业务改名后再启用严格校验）：')
        for code in invalid:
            print(f'      {code}')
    else:
        print('  - [CHECK] 存量 division_code 全部符合 code 模式')


def _do_indexes(conn: sqlite3.Connection) -> bool:
    duplicates = conn.execute(
        f'SELECT code, COUNT(*) AS n FROM {TABLE} '
        f'GROUP BY code HAVING n > 1').fetchall()
    if duplicates:
        print(f'  - [FAIL] 发现重复产品组编码，无法建唯一索引: {duplicates}')
        return False

    if _index_sql(conn, UIDX_CODE):
        print(f'  - [SKIP] 索引 {UIDX_CODE} 已存在')
    else:
        conn.execute(
            f'CREATE UNIQUE INDEX IF NOT EXISTS {UIDX_CODE} '
            f'ON {TABLE}(code)')
        print(f'  - [NEW] 索引 {UIDX_CODE} (code) 唯一')
    return True


def _do_permissions(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'permissions'):
        print('  - permissions 表不存在, 跳过权限写入')
        return

    created = 0
    for code, name, resource_type, action in PERMISSIONS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO permissions (code, name, resource_type, action) "
            "VALUES (?, ?, ?, ?)",
            (code, name, resource_type, action),
        )
        if cur.rowcount:
            created += 1
            print(f'  - [NEW] 权限 {code} ({name})')

    if created:
        print(f'  - [SUMMARY] permissions: +{created} 新增')
    else:
        print(f'  - [SKIP] {len(PERMISSIONS)} 条权限码均已存在, 无新增')


def _do_menus(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menus'):
        print('  - menus 表不存在, 跳过菜单写入')
        return

    for menu in MENUS:
        if conn.execute(
                "SELECT 1 FROM menus WHERE menu_code = ?", (menu['menu_code'],)
        ).fetchone():
            print(f"  - [SKIP] 菜单 {menu['menu_code']} ({menu['menu_name']}) 已存在")
            continue

        conn.execute(
            "INSERT INTO menus (menu_code, menu_name, menu_path, page_type, "
            "object_types, primary_object_type, bo_bindings, required_permissions, "
            "parent_menu, icon, color, description, sort_order, is_active, "
            "show_in_sidebar, auto_generated) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                menu['menu_code'],
                menu['menu_name'],
                menu['menu_path'],
                menu['page_type'],
                json.dumps(menu['object_types'], ensure_ascii=False),
                menu['primary_object_type'],
                json.dumps(menu['bo_bindings'], ensure_ascii=False),
                json.dumps(menu['required_permissions'], ensure_ascii=False),
                menu['parent_menu'],
                menu['icon'],
                menu['color'],
                menu['description'],
                menu['sort_order'],
                menu['is_active'],
                menu['show_in_sidebar'],
                menu['auto_generated'],
            ),
        )
        print(f"  - [NEW] 菜单 {menu['menu_code']} ({menu['menu_name']}) "
              f"@ {menu['menu_path']}, sort_order={menu['sort_order']}")


def _do_menu_permissions(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, 'menu_permissions'):
        print('  - menu_permissions 表不存在, 跳过同步')
        return

    for menu in MENUS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO menu_permissions (menu_code, menu_name, menu_path, "
            "required_permissions, required_any_permission, parent_menu, icon, "
            "sort_order, is_active, data_permission_hint) "
            "VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
            (
                menu['menu_code'],
                menu['menu_name'],
                menu['menu_path'],
                json.dumps(menu['required_permissions'], ensure_ascii=False),
                menu['parent_menu'],
                menu['icon'],
                menu['sort_order'],
                menu['is_active'],
                json.dumps(menu['data_permission_hint'], ensure_ascii=False),
            ),
        )
        if cur.rowcount:
            print(f"  - [NEW] menu_permissions: {menu['menu_code']}")
        else:
            print(f"  - [SKIP] menu_permissions: {menu['menu_code']} 已存在")


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v137] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v137] 开始: 产品组 division 种子 / 回填 / 菜单权限')
        if not _table_exists(conn, TABLE):
            print(f'[v137] 表 {TABLE} 不存在：请先执行 '
                  f'`python -m meta.tools.sync_schema --source sqlite '
                  f'--local {db_path} --execute` 建表')
            return False

        _do_seed(conn)
        _do_backfill(conn)
        if not _do_indexes(conn):
            conn.rollback()
            return False
        _do_permissions(conn)
        _do_menus(conn)
        _do_menu_permissions(conn)

        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v137] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言表 / 关键列 / 唯一索引 / 种子 / 菜单权限齐备。"""
    if not db_path.exists():
        print('[v137 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        info = _column_info(conn, TABLE)
        if not info:
            print(f'[v137 verify] FAIL: 表 {TABLE} 不存在')
            return False
        for column in ('code', 'name', 'status'):
            if column not in info:
                print(f'[v137 verify] FAIL: 缺列 {TABLE}.{column}')
                return False
            if info[column][3] != 1:
                print(f'[v137 verify] FAIL: {TABLE}.{column} 应为 NOT NULL')
                return False

        sql = _index_sql(conn, UIDX_CODE)
        if not sql or 'UNIQUE' not in sql.upper() or 'CODE' not in sql.upper():
            print(f'[v137 verify] FAIL: 缺唯一索引 {UIDX_CODE}')
            return False

        seed = conn.execute(
            f"SELECT name, status FROM {TABLE} WHERE code = ?", (SEED_CODE,)
        ).fetchone()
        if not seed:
            print(f'[v137 verify] FAIL: 缺种子 {SEED_CODE}')
            return False
        if seed[1] != 'active':
            print(f'[v137 verify] FAIL: 种子 {SEED_CODE} 状态异常 {seed[1]!r}')
            return False

        if _table_exists(conn, 'permissions'):
            missing = [code for code, _n, _r, _a in PERMISSIONS
                       if not conn.execute(
                           "SELECT 1 FROM permissions WHERE code = ?",
                           (code,)).fetchone()]
            if missing:
                print(f'[v137 verify] FAIL: 缺权限码 {missing}')
                return False

        if _table_exists(conn, 'menus'):
            for menu in MENUS:
                row = conn.execute(
                    "SELECT page_type, is_active, menu_path, primary_object_type, "
                    "parent_menu, required_permissions, show_in_sidebar "
                    "FROM menus WHERE menu_code = ?", (menu['menu_code'],)
                ).fetchone()
                if not row:
                    print(f"[v137 verify] FAIL: 菜单 {menu['menu_code']} 不存在")
                    return False
                if row[0] != menu['page_type'] or row[1] != 1 \
                        or (row[2] or '') != menu['menu_path'] \
                        or (row[3] or '') != menu['primary_object_type'] \
                        or (row[4] or '') != menu['parent_menu']:
                    print(f"[v137 verify] FAIL: 菜单 {menu['menu_code']} 口径异常")
                    return False
                try:
                    codes = json.loads(row[5] or '[]')
                except Exception:
                    codes = []
                if sorted(codes) != sorted(menu['required_permissions']):
                    print(f"[v137 verify] FAIL: 菜单 {menu['menu_code']} "
                          f"required_permissions={codes}")
                    return False

        if _table_exists(conn, 'menu_permissions'):
            for menu in MENUS:
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM menu_permissions WHERE menu_code = ?",
                    (menu['menu_code'],)).fetchone()[0]
                if cnt < 1:
                    print(f"[v137 verify] FAIL: menu_permissions 缺 "
                          f"{menu['menu_code']}")
                    return False

        print(f'[v137 verify] OK: {TABLE} 就位，{UIDX_CODE} 唯一，'
              f'种子 {SEED_CODE} 可用，菜单权限齐备')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """移除菜单/菜单权限种子与唯一索引；表、数据、权限码保留。"""
    if not db_path.exists():
        print(f'[v137] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        codes = tuple(menu['menu_code'] for menu in MENUS)
        placeholders = ', '.join('?' * len(codes))
        if _table_exists(conn, 'menus'):
            cur = conn.execute(
                f'DELETE FROM menus WHERE menu_code IN ({placeholders})', codes)
            print(f'  - [DROP] menus: {cur.rowcount} 条')
        if _table_exists(conn, 'menu_permissions'):
            cur = conn.execute(
                f'DELETE FROM menu_permissions WHERE menu_code IN ({placeholders})',
                codes)
            print(f'  - [DROP] menu_permissions: {cur.rowcount} 条')
        if _index_sql(conn, UIDX_CODE):
            conn.execute(f'DROP INDEX {UIDX_CODE}')
            print(f'  - [DROP] 索引 {UIDX_CODE}')
        else:
            print(f'  - [SKIP] 索引 {UIDX_CODE} 不存在')
        print(f'  - [KEEP] 表 {TABLE} 与数据保留 (由 YAML 声明)')
        print('  - [KEEP] permissions 行保留 (可能已被角色授予)')
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v137] rollback 失败: {e}')
        raise
    finally:
        conn.close()


downgrade = rollback


if __name__ == '__main__':
    import sys
    from meta.core.db_path import get_meta_db_path

    _args = [a for a in sys.argv[1:] if a != '--rollback']
    _db = Path(_args[0]) if _args else Path(get_meta_db_path())
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v137] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v137] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v137] verify: {"PASS" if _v else "FAIL"}')

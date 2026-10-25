# -*- coding: utf-8 -*-
"""[v113 2026-10-25] 模型特征声明 权限交付

背景:
  P2 新增 item_structure_attributes（模型特征声明），作为物料结构详情页的
  第二个内联子表（child_sections），由结构详情内维护，不建顶层菜单。
  子表仍需 5 条双段式权限码，供详情内联表格的按钮判定使用
  （与 v112 为 item_structure_line 落权限的理由相同）。

本迁移补齐:
  item_structure_attribute × create / read / update / delete / list = 5 条权限。

权限口径:
  双段式 {object_id}:{object_id}_{action}（例 item_structure_attribute:item_structure_attribute_create）。

幂等:
  INSERT OR IGNORE；重复执行只输出 [SKIP]。

回滚:
  **保留** permissions 行 —— 可能已被角色授予，删除有风险。
"""
import sqlite3
from pathlib import Path


OBJECT_ID = 'item_structure_attribute'
OBJECT_LABEL = '模型特征声明'

_RANK = ('create', 'read', 'update', 'delete', 'list')

_ACTION_LABEL = {
    'create': '新建', 'read': '查看', 'update': '修改',
    'delete': '删除', 'list': '查询',
}

PERMISSIONS = tuple(
    (f'{OBJECT_ID}:{OBJECT_ID}_{action}',
     f'{_ACTION_LABEL[action]}{OBJECT_LABEL}',
     OBJECT_ID,
     action)
    for action in _RANK
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


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


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v113] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v113] 开始: 模型特征声明 权限')
        _do_permissions(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v113] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    """断言 5 条双段式权限码就位。"""
    if not db_path.exists():
        print('[v113 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'permissions'):
            print('[v113 verify] FAIL: permissions 表不存在')
            return False

        missing = []
        for code, _name, _rt, _action in PERMISSIONS:
            if not conn.execute(
                    "SELECT 1 FROM permissions WHERE code = ?", (code,)).fetchone():
                missing.append(code)
        if missing:
            print(f'[v113 verify] FAIL: 缺权限码 {missing}')
            return False

        malformed = [c for c, _n, _r, _a in PERMISSIONS
                     if c.count(':') != 1
                     or not c.split(':')[1].startswith(c.split(':')[0] + '_')]
        if malformed:
            print(f'[v113 verify] FAIL: 非双段式权限码 {malformed}')
            return False

        print('[v113 verify] OK: 5 条双段式权限码齐备')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    """permissions 行保留（可能已被角色授予），无删除动作。"""
    print('[v113] downgrade: permissions 行保留 (可能已被角色授予)')
    return True


if __name__ == '__main__':
    import sys
    _db = Path(sys.argv[1]) if len(sys.argv) > 1 \
        else Path(__file__).resolve().parents[1] / 'architecture.db'
    _ok = migrate(_db)
    print(f'[v113] migrate: {"OK" if _ok else "FAIL"}')
    _v = verify(_db)
    print(f'[v113] verify: {"PASS" if _v else "FAIL"}')

# -*- coding: utf-8 -*-
"""v230 - 规则中心三枚权限码

依据: docs/superpowers/specs/2026-11-07-rule-convergence-spec.md
      FR-014 / FR-017 / FR-018（规则中心只读层 + 试算 + 配置发布流）

背景:
  P1 只补了 `rule-center` 菜单与 menu_permissions（init_menu_permissions.py），
  但 `permissions` 表缺三枚权限码。`require_permission` 运行时按 code 查
  `permissions` / 角色授权链，缺失时非 admin 用户会被 403 拦下。

范围:
  1. permissions 表幂等写入三枚权限码（双段式 {resource}:{resource}_{action}）:
       rule_center:rule_center_read   查看 / 试算
       rule_center:rule_center_write  保存草稿 / 发布 / 回滚
       rule_center:rule_center_trace  单据推导链
  2. 校验 `rule-center` 菜单与 menu_permissions 已存在（由 init 脚本负责），
     缺失时打印 [WARN]，不在此处重复造菜单。

幂等: 全部 INSERT OR IGNORE，重复执行打印 [SKIP]。

回滚: **保留** permissions 行 —— 可能已被角色授予，删除有风险。
"""

from pathlib import Path
import sqlite3

RESOURCE_TYPE = 'rule_center'

PERMISSIONS = (
    ('rule_center:rule_center_read', '查看规则中心 / 规则试算', 'read'),
    ('rule_center:rule_center_write', '维护规则配置（草稿 / 发布 / 回滚）', 'write'),
    ('rule_center:rule_center_trace', '查看单据规则推导链', 'trace'),
)

MENU_CODE = 'rule-center'


def _table_exists(conn, name):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _do_permissions(conn):
    if not _table_exists(conn, 'permissions'):
        print('  - permissions 表不存在, 跳过权限写入')
        return

    created = 0
    for code, name, action in PERMISSIONS:
        cur = conn.execute(
            "INSERT OR IGNORE INTO permissions (code, name, resource_type, action) "
            "VALUES (?, ?, ?, ?)",
            (code, name, RESOURCE_TYPE, action),
        )
        if cur.rowcount:
            created += 1
            print(f'  - [NEW] 权限 {code} ({name})')

    if created:
        print(f'  - [SUMMARY] permissions: +{created} 新增')
    else:
        print(f'  - [SKIP] {len(PERMISSIONS)} 条权限码均已存在, 无新增')


def _check_menu(conn):
    if not _table_exists(conn, 'menus'):
        print('  - [WARN] menus 表不存在, 菜单需由 init_menu_permissions.py 建立')
        return
    row = conn.execute(
        "SELECT page_type, menu_path FROM menus WHERE menu_code = ?", (MENU_CODE,)
    ).fetchone()
    if not row:
        print(f'  - [WARN] 菜单 {MENU_CODE} 不存在, 请先执行 init_menu_permissions.py')
        return
    print(f'  - [OK] 菜单 {MENU_CODE}: page_type={row[0]}, path={row[1]}')


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    if not db_path.exists():
        print(f'[v230] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        print('[v230] 开始: 规则中心权限码')
        _do_permissions(conn)
        _check_menu(conn)
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        print(f'[v230] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v230 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'permissions'):
            print('[v230 verify] FAIL: permissions 表不存在')
            return False

        missing = [code for code, _n, _a in PERMISSIONS
                   if not conn.execute(
                       "SELECT 1 FROM permissions WHERE code = ?", (code,)).fetchone()]
        if missing:
            print(f'[v230 verify] FAIL: 缺权限码 {missing}')
            return False

        menu = conn.execute(
            "SELECT required_permissions FROM menu_permissions WHERE menu_code = ?",
            (MENU_CODE,),
        ).fetchone()
        if menu and 'rule_center:rule_center_read' not in (menu[0] or ''):
            print('[v230 verify] FAIL: menu_permissions 未声明 rule_center_read')
            return False

        print(f'[v230 verify] OK: {len(PERMISSIONS)} 条规则中心权限码就位')
        return True
    finally:
        conn.close()


def rollback(db_path: Path, skip_backup: bool = False) -> bool:
    """permissions 行保留（可能已被角色授予）。"""
    print('  - [KEEP] permissions 行保留 (可能已被角色授予)')
    return True


downgrade = rollback


if __name__ == '__main__':
    import sys

    from meta.core.db_path import get_meta_db_path

    _args = [a for a in sys.argv[1:] if a != '--rollback']
    _db = Path(_args[0]) if _args else Path(get_meta_db_path())
    if '--rollback' in sys.argv[1:]:
        _ok = rollback(_db)
        print(f'[v230] rollback: {"OK" if _ok else "FAIL"}')
    else:
        _ok = migrate(_db)
        print(f'[v230] migrate: {"OK" if _ok else "FAIL"}')
        _v = verify(_db)
        print(f'[v230] verify: {"PASS" if _v else "FAIL"}')
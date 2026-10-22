# -*- coding: utf-8 -*-
"""[v097 2026-10-22] 菜单显示名「往来单位」→「业务伙伴」

背景:
  身份域的界面口径统一。模型层 party 已是「统一主体 + 关系边 + 角色」的形态
  （party_archive 对外 / party_internal 内部 / party_relation 关系边），
  「往来单位」是客户/供应商台账式的窄口径，装不下我方组织这一半 —— 我方主体
  不是「有往来」的对象。域级词改「业务伙伴」，与 SAP Business Partner 对齐。

本迁移做什么:
  只改显示文本，不动任何标识:
    - menus.menu_code='party-management' 的 menu_name: 往来单位 → 业务伙伴
    - 该行 data_permission_hint JSON 内的 message 同步为业务伙伴口径
  menu_code / menu_path / object_types / required_permissions 一律不变
  ⇒ 前端路由、权限判定、对象 id、表名零影响。

幂等:
  按 menu_code 定位并 UPDATE 到目标值，重复执行为 no-op。

回滚:
  menu_name 改回「往来单位」，hint message 同步回滚。
"""
import json
import sqlite3
from pathlib import Path

_MENU_CODE = 'party-management'
_NEW_MENU_NAME = '业务伙伴'
_OLD_MENU_NAME = '往来单位'
_NEW_HINT = '建议分配业务伙伴 / 业务伙伴组 / 业务伙伴关系数据权限'
_OLD_HINT = '建议分配往来单位 / 往来单位组 / 往来单位关系数据权限'


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def _rewrite_hint(raw: str, message: str) -> str:
    """只替换 data_permission_hint 里的 message，其余键保持原样。"""
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return raw
    if isinstance(data, dict) and 'message' in data:
        data['message'] = message
    return json.dumps(data, ensure_ascii=False)


def _apply(db_path: Path, menu_name: str, hint: str) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v097] DB 不存在: {db_path}')
        return False

    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if not _table_exists(conn, 'menus'):
            print('[v097] SKIP: 无 menus 表（该库不承载导航域）')
            return True

        row = conn.execute(
            "SELECT id, menu_name, data_permission_hint FROM menus WHERE menu_code=?",
            (_MENU_CODE,),
        ).fetchone()
        if not row:
            print(f'[v097] SKIP: 无 {_MENU_CODE} 菜单行')
            return True

        menu_id, old_name, raw_hint = row
        conn.execute(
            "UPDATE menus SET menu_name=? WHERE id=?", (menu_name, menu_id))
        if raw_hint:
            conn.execute(
                "UPDATE menus SET data_permission_hint=? WHERE id=?",
                (_rewrite_hint(raw_hint, hint), menu_id))
        conn.commit()
        print(f'[v097] OK: menu_name {old_name!r} -> {menu_name!r}')
        return True
    finally:
        conn.close()


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    return _apply(db_path, _NEW_MENU_NAME, _NEW_HINT)


def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if not _table_exists(conn, 'menus'):
            print('[v097 verify] SKIP: 无 menus 表')
            return True
        row = conn.execute(
            "SELECT menu_name FROM menus WHERE menu_code=?", (_MENU_CODE,)
        ).fetchone()
        if not row:
            print(f'[v097 verify] SKIP: 无 {_MENU_CODE} 菜单行')
            return True
        if row[0] != _NEW_MENU_NAME:
            print(f'[v097 verify] FAIL: menu_name={row[0]!r}，期望 {_NEW_MENU_NAME!r}')
            return False
        print(f'[v097 verify] OK: menu_name={_NEW_MENU_NAME!r}')
        return True
    finally:
        conn.close()


def downgrade(db_path: Path, skip_backup: bool = False) -> bool:
    return _apply(db_path, _OLD_MENU_NAME, _OLD_HINT)


if __name__ == '__main__':
    import sys

    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(get_meta_db_path())
    print(f'[v097] migrating {db}')
    ok = migrate(db)
    print(f'[v097] migrate: {"OK" if ok else "FAIL"}')
    v = verify(db)
    print(f'[v097] verify: {"PASS" if v else "FAIL"}')
    sys.exit(0 if (ok and v) else 1)

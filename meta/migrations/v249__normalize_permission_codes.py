# -*- coding: utf-8 -*-
"""v249 —— 权限码归一：双段 `{bo}:{bo}_{action}` → 单段 `{bo}:{action}`。

背景（T1）:
  动作 id 历史上冗余携带对象前缀（`ensure_crud_actions` 产出 `{bo}_create`，
  手写动作如 `receipt_post`），派生出的权限码因此是双段：
      sales_order:sales_order_create / receipt:receipt_post
  代码侧已统一为单段（meta/core/models.py::get_permission_code +
  schema/ui_view_config/bo_action_registrations 的字面量归一）。
  存量库必须同步收敛，否则：
      · 代码查 `sales_order:create`，库里只有 `sales_order:sales_order_create`
        ⇒ strict 模式全员 403（只有持 `*` 的组幸免）；
      · 权限矩阵出现两条同义码，勾选与生效不一致。

规则:
  {bo}:{bo}_{verb}  ->  {bo}:{verb}
  verb in (list, query, view) -> read（list/query/view 与 read 同义）

策略:
  · 目标码已存在 ⇒ 合并：把授予关系重指向目标行，再删旧行；
  · 目标码不存在 ⇒ 原地重命名 code；
  · 脏码（`:` / `:_create` 等）⇒ 先删授予关系再删行；
  · 孤儿授予（permission_set_permissions 指向已删权限）⇒ 一并清理；
  · 全程幂等：第二次执行匹配 0 行，打印 [SKIP]。

注意:
  本迁移只动 DB；`menu_permissions.required_permissions` 由启动时
  init_menu_permissions 的 UPSERT 从声明侧刷新，无需在此重写。
"""

import re
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v249__normalize_permission_codes'

PERMISSIONS = 'permissions'
CODE_COL = 'code'

# 引用 permissions.id 的关联表（列名, 是否唯一约束）
LINK_TABLES = (
    ('permission_set_permissions', 'permission_id'),
)

ALIASES = {'list': 'read', 'query': 'read', 'view': 'read'}

_DOUBLE_RE = re.compile(r'^([a-z0-9_]+):\1_([a-z0-9_]+)$')
_DIRTY_RE = re.compile(r'^:.*$|.*:$')


def _normalize(code):
    """双段/脏码 → 单段；无需处理时返回 None。"""
    if not code:
        return None
    if _DIRTY_RE.match(code):
        return None  # 脏码单独删除
    match = _DOUBLE_RE.match(code)
    if not match:
        return None
    bo, verb = match.group(1), match.group(2)
    return '%s:%s' % (bo, ALIASES.get(verb, verb))


def _delete_rows(conn, ids):
    for table, column in LINK_TABLES:
        if not _has_table(conn, table):
            continue
        for pid in ids:
            conn.execute('DELETE FROM %s WHERE %s = ?' % (table, column), [pid])
    for pid in ids:
        conn.execute('DELETE FROM %s WHERE id = ?' % PERMISSIONS, [pid])


def _has_table(conn, name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", [name]).fetchone()
    return bool(row)


def _merge(conn, old_id, new_id):
    """把 old_id 的授予关系挂到 new_id，然后删 old_id。"""
    for table, column in LINK_TABLES:
        if not _has_table(conn, table):
            continue
        # UPDATE OR IGNORE：唯一约束冲突（已授予过目标码）时保留目标行，残留行随后删除
        conn.execute(
            'UPDATE OR IGNORE %s SET %s = ? WHERE %s = ?' % (table, column, column),
            [new_id, old_id])
        conn.execute('DELETE FROM %s WHERE %s = ?' % (table, column), [old_id])
    conn.execute('DELETE FROM %s WHERE id = ?' % PERMISSIONS, [old_id])


def _clean_dirty(conn):
    rows = conn.execute(
        'SELECT id, %s FROM %s' % (CODE_COL, PERMISSIONS)).fetchall()
    dirty = [pid for pid, code in rows if code and _DIRTY_RE.match(code)]
    if dirty:
        _delete_rows(conn, dirty)
    return len(dirty)


def _clean_orphan_grants(conn):
    """清掉指向已不存在权限的授予行（存量脏数据，verify 会判 FAIL）。"""
    removed = 0
    for table, column in LINK_TABLES:
        if not _has_table(conn, table):
            continue
        cur = conn.execute(
            'DELETE FROM %s WHERE %s NOT IN (SELECT id FROM %s)'
            % (table, column, PERMISSIONS))
        removed += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    return removed


def _normalize_rows(conn):
    rows = conn.execute(
        'SELECT id, %s FROM %s' % (CODE_COL, PERMISSIONS)).fetchall()
    by_code = {code: pid for pid, code in rows}
    renamed = merged = 0
    for pid, code in rows:
        target = _normalize(code)
        if not target or target == code:
            continue
        existing = by_code.get(target)
        if existing and existing != pid:
            _merge(conn, pid, existing)
            merged += 1
        else:
            conn.execute(
                'UPDATE %s SET %s = ? WHERE id = ?' % (PERMISSIONS, CODE_COL),
                [target, pid])
            by_code.pop(code, None)
            by_code[target] = pid
            renamed += 1
    return renamed, merged


def migrate(db_path, skip_backup=False):
    # skip_backup: MigrationRunner 已统一备份，迁移内部不再重复备份
    path = Path(db_path)
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        print('[v249] 开始: 权限码归一（双段 → 单段）')
        conn.execute('BEGIN')
        dirty = _clean_dirty(conn)
        renamed, merged = _normalize_rows(conn)
        orphans = _clean_orphan_grants(conn)
        conn.commit()
        print('[v249] 完成: 删除脏码 %d 行, 重命名 %d 行, 合并 %d 行, 清孤儿授予 %d 行'
              % (dirty, renamed, merged, orphans))
        if not (dirty or renamed or merged or orphans):
            print('[v249] [SKIP] 无待归一权限码')
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


upgrade = migrate


def verify(db_path) -> bool:
    path = Path(db_path)
    if not path.exists():
        print('[v249 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        rows = conn.execute('SELECT %s FROM %s' % (CODE_COL, PERMISSIONS)).fetchall()
        double = [code for (code,) in rows if _normalize(code)]
        dirty = [code for (code,) in rows if code and _DIRTY_RE.match(code)]
        orphan = 0
        for table, column in LINK_TABLES:
            if not _has_table(conn, table):
                continue
            orphan += conn.execute(
                'SELECT COUNT(*) FROM %s x WHERE NOT EXISTS '
                '(SELECT 1 FROM %s p WHERE p.id = x.%s)' % (table, PERMISSIONS, column)
            ).fetchone()[0]
        if double or dirty or orphan:
            print('[v249 verify] FAIL: 双段 %d / 脏码 %d / 孤儿授予 %d'
                  % (len(double), len(dirty), orphan))
            return False
        return True
    finally:
        conn.close()
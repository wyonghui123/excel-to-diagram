# -*- coding: utf-8 -*-
"""v251 —— 菜单权限码归一：双段/同义动词 → 单段 `{bo}:{action}`。

背景:
  v249 只收敛了 permissions 表与授予关系，并假设 menu_permissions.required_permissions
  会由启动时 init_menu_permissions 的 UPSERT 从声明侧刷新。但 MIGRATION_OWNED_MENUS
  中的菜单（收货 / 调拨单 / 调拨发货 / 工程变更 / 库龄）由迁移创建，init 脚本不接管，
  于是这些行仍持有旧码：
      receipt:receipt_read / transfer_order:transfer_order_release /
      inventory_balance:inventory_balance_read / engineering_change:view
  门禁 R5（菜单引用但未声明且未入库）因此报 18 条 ERROR。

规则（与 v249 完全一致）:
  · `{bo}:{bo}_{verb}` → `{bo}:{verb}`
  · list / query / view → read（与 read 同义）
  · 去重、保序

范围:
  · menu_permissions.required_permissions（JSON 数组文本）
  · menus.required_permissions（JSON 数组文本，导航侧冗余）

例外:
  `project:time_entry_*` 按 v182 规定 `resource_type=project`，动作不再剥前缀；
  本迁移只剥 `${bo}_` 前缀，因此该例外天然保留。

幂等: 已是单段码的行匹配 0 变化，重复执行打印 [SKIP]。
"""
import json
import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v251__normalize_menu_permission_codes'

ALIASES = {'list': 'read', 'query': 'read', 'view': 'read'}

TARGETS = (
    ('menu_permissions', 'menu_code', 'required_permissions'),
    ('menus', 'menu_code', 'required_permissions'),
)


def _normalize(code):
    """双段/同义动词 → 单段；无需处理时原样返回。"""
    if not isinstance(code, str) or ':' not in code:
        return code
    bo, _, action = code.partition(':')
    prefix = bo + '_'
    if action.startswith(prefix):
        action = action[len(prefix):]
    return '%s:%s' % (bo, ALIASES.get(action, action))


def _parse(raw):
    """required_permissions 是 JSON 数组文本；兼容逗号分隔的历史脏值。"""
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return [part.strip() for part in str(raw).split(',') if part.strip()]
    if isinstance(parsed, list):
        return [v for v in parsed if isinstance(v, str) and v]
    if isinstance(parsed, str) and parsed:
        return [parsed]
    return []


def _has_table(conn, name):
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", [name]).fetchone())


def _has_column(conn, table, column):
    return any(row[1] == column for row in conn.execute('PRAGMA table_info(%s)' % table))


def _normalize_rows(conn):
    changed_rows = changed_codes = 0
    seen_codes = set()
    for table, key_col, value_col in TARGETS:
        if not _has_table(conn, table) or not _has_column(conn, table, value_col):
            continue
        rows = conn.execute(
            'SELECT %s, %s FROM %s' % (key_col, value_col, table)).fetchall()
        for key, raw in rows:
            values = _parse(raw)
            if not values:
                continue
            normalized, seen = [], set()
            for code in values:
                target = _normalize(code)
                seen_codes.add(code)
                if target not in seen:
                    seen.add(target)
                    normalized.append(target)
            if normalized == values:
                continue
            conn.execute(
                'UPDATE %s SET %s = ? WHERE %s = ?' % (table, value_col, key_col),
                [json.dumps(normalized, ensure_ascii=False), key])
            changed_rows += 1
            changed_codes += sum(1 for a, b in zip(values, normalized) if a != b)
    return changed_rows, changed_codes, seen_codes


def migrate(db_path, skip_backup=False):
    # skip_backup: MigrationRunner 已统一备份，迁移内部不再重复备份
    path = Path(db_path)
    conn = sqlite3.connect(str(path), timeout=30)
    try:
        print('[v251] 开始: 菜单权限码归一（双段/同义动词 → 单段）')
        conn.execute('BEGIN')
        rows, codes, _ = _normalize_rows(conn)
        conn.commit()
        print('[v251] 完成: 改写 %d 行 / %d 个码位' % (rows, codes))
        if not rows:
            print('[v251] [SKIP] 菜单权限码已是单段')
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
        print('[v251 verify] FAIL: DB 不存在')
        return False
    conn = sqlite3.connect(str(path), timeout=10)
    try:
        stale = []
        for table, key_col, value_col in TARGETS:
            if not _has_table(conn, table) or not _has_column(conn, table, value_col):
                continue
            for key, raw in conn.execute(
                    'SELECT %s, %s FROM %s' % (key_col, value_col, table)).fetchall():
                for code in _parse(raw):
                    if _normalize(code) != code:
                        stale.append('%s.%s: %s' % (table, key, code))
        if stale:
            print('[v251 verify] FAIL: 残留旧码 %d 条: %s'
                  % (len(stale), ', '.join(stale[:10])))
            return False
        return True
    finally:
        conn.close()
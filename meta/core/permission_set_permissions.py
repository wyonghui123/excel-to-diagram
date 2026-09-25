# -*- coding: utf-8 -*-
"""permission_set_permissions 写入助手 —— 按实际列名自适应（三种 schema 形态）

[FIX 2026-09-25 缺陷④] `permission_set_permissions` 在不同环境存在三种形态
（形态清单见 meta/migrations/v084__org_admin_delegation_m2.py）：
  - ID-form    : (permission_set_id, permission_id, granted, created_at)
  - CODE-form  : 额外含 permission_code 列（部分 dev/worktree 库，且为 NOT NULL）
  - LEGACY-form: 列名为 role_id（v070 仅 RENAME 表名，由 v087 backfill 修复）

历史缺陷：3 处写入点硬编码了 `permission_code` 列，在 ID-form 库上 INSERT 抛
`table permission_set_permissions has no column named permission_code`：
  - 菜单保存（permission_set_menu_api，自动同步 + 显式授予两处）异常被 `except: pass`
    吞掉 → PUT 返回"已同步 0 项功能权限" → 勾选应用菜单后功能权限行永不写入 →
    矩阵 auto 来源被门禁挡住 → 应用资源行永久不可见（死锁，实测 2026-09-25）；
  - 矩阵保存（permission_dimension_api）→ HTTP 500。

本模块只按目标库**实际存在的列**拼 INSERT，三种形态均可写；写失败返回 False
（并记录 warning），由调用方决定是记数继续还是直接报错。
"""
import logging
from datetime import datetime
from typing import Optional, Set

logger = logging.getLogger(__name__)

TABLE = 'permission_set_permissions'

# id(ds) -> (ds 强引用, 列名集合)
#   [注意] 缓存同时持有 ds 引用，避免 ds 被 GC 后 id() 复用导致读到别的库的列集
_cols_cache = {}


def _query_columns(ds) -> Set[str]:
    try:
        cursor = ds.execute(f"PRAGMA table_info({TABLE})")
        rows = cursor.fetchall() if cursor else []
    except Exception as e:
        logger.warning(f"[PSP] 读取 {TABLE} 列表失败，按 ID-form 处理: {e}")
        return {'permission_set_id', 'permission_id', 'granted', 'created_at'}
    # PRAGMA 行: (cid, name, type, notnull, dflt_value, pk)
    cols = set()
    for row in rows:
        try:
            cols.add(row[1])
        except (TypeError, IndexError):
            continue
    return cols or {'permission_set_id', 'permission_id', 'granted', 'created_at'}


def get_columns(ds) -> Set[str]:
    """返回 permission_set_permissions 的实际列名集合（按 ds 缓存）"""
    key = id(ds)
    hit = _cols_cache.get(key)
    if hit is not None and hit[0] is ds:
        return hit[1]
    cols = _query_columns(ds)
    _cols_cache[key] = (ds, cols)
    return cols


def _set_id_column(cols: Set[str]) -> Optional[str]:
    if 'permission_set_id' in cols:
        return 'permission_set_id'
    if 'role_id' in cols:
        return 'role_id'
    return None


def ensure_granted(ds, permission_set_id: int, permission_id: int, code: str = '') -> bool:
    """确保 (权限集, 权限) 关联存在且 granted=1（等价原 INSERT OR IGNORE / OR REPLACE 意图）

    已有的 granted=0 行会被置 1（原 OR REPLACE 语义），不存在则插入。

    Returns:
        True 表示写入（或更新）成功；False 表示失败（已记 warning，调用方决定如何处理）
    """
    cols = get_columns(ds)
    id_col = _set_id_column(cols)
    if not id_col:
        logger.warning(f"[PSP] {TABLE} 无 permission_set_id/role_id 列，无法写入 "
                       f"(ps={permission_set_id}, pid={permission_id}, code={code})；实际列={sorted(cols)}")
        return False

    try:
        if 'granted' in cols:
            ds.execute(
                f"UPDATE {TABLE} SET granted = 1 WHERE {id_col} = ? AND permission_id = ?",
                [permission_set_id, permission_id],
            )

        names = [id_col, 'permission_id']
        values = [permission_set_id, permission_id]
        if 'permission_code' in cols:
            names.append('permission_code')
            values.append(code or '')
        if 'granted' in cols:
            names.append('granted')
            values.append(1)
        if 'created_at' in cols:
            names.append('created_at')
            values.append(datetime.now().isoformat())

        placeholders = ', '.join(['?'] * len(names))
        ds.execute(
            f"INSERT OR IGNORE INTO {TABLE} ({', '.join(names)}) VALUES ({placeholders})",
            values,
        )
        return True
    except Exception as e:
        logger.warning(f"[PSP] 写入 {TABLE} 失败 (ps={permission_set_id}, pid={permission_id}, "
                       f"code={code}): {e}")
        return False
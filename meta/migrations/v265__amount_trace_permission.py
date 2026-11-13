# -*- coding: utf-8 -*-
"""[v265 2026-11-13] 金额回溯权限码 amount:trace

依据: 统一金额回溯（销售订单 / 采购订单 / 采购发票 / 销售发票共用同一契约）

背景:
  `GET /api/v2/bo/<object_type>/<id>/amount-trace` 与详情页「金额回溯」分区
  使用同一枚权限码 `amount:trace`。`permissions` 表缺该行时：
    · 后端：非 admin 用户 403（require_permission 按码精确匹配，不做前缀推导）；
    · 前端：hasPermission 为 false ⇒ 分区静默隐藏（不报错，难排查）。
  参照 v230（rule_center 三枚码）的教训：码必须显式写进 permissions 表，
  否则只能靠 admin 的 '*' 通配看到功能。

范围:
  1. permissions 表幂等写入 1 枚权限码（单段式 {resource}:{action}）:
       amount:trace  查看单据金额回溯（金额分解 / 定价回溯 / 调整）
  2. 不建菜单：金额回溯是详情页内嵌分区，入口跟随各单据详情页。

幂等: INSERT OR IGNORE，重复执行打印 [SKIP]。

回滚: **保留** permissions 行 —— 可能已被角色授予，删除有风险。
"""

import sqlite3
from pathlib import Path

MIGRATION_NAME = 'v265__amount_trace_permission'

PERMISSION = (
    'amount:trace',
    '查看单据金额回溯（金额分解 / 定价回溯 / 调整）',
    'amount',
    'trace',
)


def _table_exists(conn, name):
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print(f'[v265] DB 不存在: {db_path}')
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        print('[v265] 开始: 金额回溯权限码')
        if not _table_exists(conn, 'permissions'):
            print('  - [WARN] permissions 表不存在, 跳过权限写入')
            return True

        cur = conn.execute(
            "INSERT OR IGNORE INTO permissions (code, name, resource_type, action) "
            "VALUES (?, ?, ?, ?)",
            PERMISSION,
        )
        if cur.rowcount:
            print(f'  - [NEW] 权限 {PERMISSION[0]} ({PERMISSION[1]})')
        else:
            print(f'  - [SKIP] 权限 {PERMISSION[0]} 已存在')
        conn.commit()
        return True
    except Exception as e:  # noqa: BLE001
        conn.rollback()
        print(f'[v265] migrate 失败: {e}')
        raise
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    db_path = Path(db_path)
    if not db_path.exists():
        print('[v265 verify] FAIL: DB 不存在')
        return False

    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, 'permissions'):
            print('[v265 verify] FAIL: permissions 表不存在')
            return False
        row = conn.execute(
            'SELECT 1 FROM permissions WHERE code = ?', (PERMISSION[0],)
        ).fetchone()
        if not row:
            print(f'[v265 verify] FAIL: 缺权限码 {PERMISSION[0]}')
            return False
        print(f'[v265 verify] OK: {PERMISSION[0]}')
        return True
    finally:
        conn.close()
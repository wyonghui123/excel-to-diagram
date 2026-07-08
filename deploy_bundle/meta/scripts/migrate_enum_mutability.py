# -*- coding: utf-8 -*-
"""
enum_types.mutability 字段值迁移脚本 (v3.18 enum-mgmt-spec)

【背景】enum_types.mutability 字段原设计 5 值（mutable/immutable/extensible/frozen/locked），
       实际代码只使用 2 值（extensible/locked）。本次规范化为 3 值。

【映射表】
  mutable       → fullEditable
  immutable     → extensible
  frozen        → locked
  extensible    → extensible   (no-op)
  locked        → locked       (no-op)
  fullEditable  → fullEditable (no-op, 已在 3 值空间)

【执行】
  python meta/scripts/migrate_enum_mutability.py --dry-run
  python meta/scripts/migrate_enum_mutability.py --execute
  python meta/scripts/migrate_enum_mutability.py --execute --backup-meta/architecture.db.bak.pre-mutability

【安全】
  - 默认 --dry-run，仅打印变更计划
  - --execute 前必先备份 DB
  - 全程在单事务中（成功提交 / 失败回滚）
  - 不修改 enum_values 表
  - 旧值若不在映射表 → 抛 RuntimeError（不静默跳过）
"""
import sys
import os
import argparse
import json
import shutil
import sqlite3
import logging
from datetime import datetime

script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(script_dir))
sys.path.insert(0, project_root)

logger = logging.getLogger(__name__)
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def _get_db_path():
    """获取主 DB 路径（meta/architecture.db）"""
    return os.path.join(project_root, 'meta', 'architecture.db')


def _connect():
    """直连 sqlite3 DB（绕开 datasource 单例）"""
    db_path = _get_db_path()
    if not os.path.exists(db_path):
        raise RuntimeError(f"DB not found: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

# 映射表：old_value → new_value
MUTABILITY_MAP = {
    'mutable':       'fullEditable',
    'immutable':     'extensible',
    'frozen':        'locked',
    'fully_editable': 'fullEditable',  # 历史遗留：snake_case 写法
    'extensible':    'extensible',   # no-op
    'locked':        'locked',        # no-op
    'fullEditable':  'fullEditable',  # no-op (already 3-value space)
}

ALLOWED_VALUES = {'fullEditable', 'extensible', 'locked'}


def _scan(conn):
    """扫描 enum_types 表的 mutability 分布"""
    cursor = conn.execute("SELECT mutability, COUNT(*) AS cnt FROM enum_types GROUP BY mutability")
    return {row['mutability']: row['cnt'] for row in cursor.fetchall()}


def _plan(conn):
    """计算变更计划"""
    distribution = _scan(conn)
    plan = []
    for old_val, count in distribution.items():
        if old_val not in MUTABILITY_MAP:
            raise RuntimeError(
                f"发现未映射的 mutability 值: '{old_val}' (count={count})。"
                f"需先在 MUTABILITY_MAP 中添加映射规则后再执行。\n"
                f"当前已支持: {list(MUTABILITY_MAP.keys())}"
            )
        new_val = MUTABILITY_MAP[old_val]
        if old_val != new_val:
            plan.append({
                'old': old_val,
                'new': new_val,
                'count': count,
            })
    return plan, distribution


def _execute(backup_path):
    """执行迁移（单事务）"""
    if backup_path:
        db_path = _get_db_path()
        shutil.copy2(db_path, backup_path)
        logger.info(f"DB backup created: {backup_path}")

    conn = _connect()
    try:
        # CHECK 禁用外键以避免 enum_value→enum_type FK 锁
        conn.execute("BEGIN")
        for old_val, new_val in MUTABILITY_MAP.items():
            if old_val == new_val:
                continue
            cursor = conn.execute(
                "UPDATE enum_types SET mutability = ? WHERE mutability = ?",
                [new_val, old_val]
            )
            logger.info(f"  {old_val} → {new_val}: {cursor.rowcount} rows")
        conn.execute("COMMIT")
        logger.info("Transaction committed.")
    except Exception as e:
        conn.execute("ROLLBACK")
        logger.error(f"Migration failed, rolled back: {e}")
        raise
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description='enum_types.mutability 值迁移')
    parser.add_argument('--dry-run', action='store_true', default=True,
                        help='仅打印变更计划（默认）')
    parser.add_argument('--execute', action='store_true',
                        help='实际执行迁移（必须先备份 DB）')
    parser.add_argument('--backup', type=str, default=None,
                        help='DB 备份路径（仅 --execute 时生效）')
    args = parser.parse_args()

    is_execute = args.execute

    logger.info(f"=== Mutability Migration {'EXECUTE' if is_execute else 'DRY-RUN'} ===")
    logger.info(f"Mapping:")
    for k, v in MUTABILITY_MAP.items():
        marker = " (no-op)" if k == v else ""
        logger.info(f"  {k:>15} → {v:<15}{marker}")

    conn = _connect()
    try:
        plan, distribution = _plan(conn)
    finally:
        conn.close()

    logger.info(f"\n当前 mutability 分布:")
    for val, cnt in sorted(distribution.items()):
        logger.info(f"  {val:>15}: {cnt}")

    if not plan:
        logger.info("\n✓ 无需变更：所有值已在 3 值空间内。")
        return 0

    logger.info(f"\n变更计划 ({len(plan)} 项):")
    for p in plan:
        logger.info(f"  {p['old']} → {p['new']} (影响 {p['count']} 条)")

    if is_execute:
        if not args.backup:
            logger.error("✗ --execute 必须指定 --backup 路径（防止数据丢失）")
            return 1
        _execute(args.backup)
        # 验证
        conn = _connect()
        try:
            post = _scan(conn)
        finally:
            conn.close()
        non_3val = {k: v for k, v in post.items() if k not in ALLOWED_VALUES}
        if non_3val:
            logger.error(f"✗ 验证失败：仍有非 3 值空间的值: {non_3val}")
            return 1
        logger.info(f"\n✓ 迁移完成。新分布: {post}")
    else:
        logger.info(f"\n(DRY-RUN，未实际执行) 加 --execute 启动实际迁移。")

    return 0


if __name__ == '__main__':
    sys.exit(main())

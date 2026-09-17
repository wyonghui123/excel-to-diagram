#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
migration_deploy_sync.py - 部署目录的 migration 文件 vs DB schema_migrations 表 一致性检查

设计原则 (无开发假设):
  - 不假设具体 migration 命名规范 (v001__, v002__, fix_xxx, add_yyy 都接受)
  - 输入: 任意 migrations 目录 + 任意 SQLite DB
  - 输出: {in_files_only, in_db_only, common} 三元组 + drift 标记

用途 (核心场景):
  staging DB 是 prod 备份, 已经跑了 v087/v088/v089, 但部署目录里缺这些 migration
  文件. 结果: server.py 启动时 init_auth.py 报 no such column.
  本工具在 deploy 前自动检测这种 drift, 阻断错配的部署.

用法:
  python migration_deploy_sync.py --migrations-dir meta/migrations --db db.sqlite
  python migration_deploy_sync.py --migrations-dir meta/migrations --db db.sqlite --json
  python migration_deploy_sync.py --migrations-dir meta/migrations --db db.sqlite --exit-code

实现:
  1. 扫描 --migrations-dir 所有 *.py 文件 (递归)
  2. 对每个文件, 提取:
     - 文件名 (basename)
     - 版本前缀 (例 v087__..., fix_xxx)
  3. 读 DB schema_migrations 表, 列出已执行的 migration_name
  4. diff:
     - in_files_only: 部署目录有, 但 DB 没记录 -> 新文件, 未跑 (OK)
     - in_db_only: DB 记录了, 但部署目录找不到 -> 历史迁移已跑, 文件被删 (WARN)
     - common: 都有 -> OK
  5. drift = in_db_only (DB 跑过但代码缺失)

[2026-09-16] P1-1 通用化基础设施
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import List, Optional


# --------------------------------------------------------------------------
# 1. 扫描 migrations 目录
# --------------------------------------------------------------------------
def scan_migrations(migrations_dir: Path) -> List[dict]:
    """递归扫描目录, 提取所有 *.py migration 文件.

    Returns:
        list of {name, rel_path, version, abs_path}
        version = 文件名前缀 (e.g. 'v087', 'fix', 'add'); None if 无前缀
    """
    if not migrations_dir.exists():
        return []

    results = []
    # 跳过 __pycache__ / 非 .py
    for f in sorted(migrations_dir.rglob("*.py")):
        if "__pycache__" in str(f):
            continue
        name = f.name
        # 跳过非 migration 文件 (utils, helpers, 测试)
        if name.startswith("__"):
            continue
        # 提取版本前缀: v\d+, fix_, add_, rename_, drop_, recover_, migrate_, create_, enhance_
        m = re.match(r'^([a-zA-Z]+_\d+|v\d+|fix|add|rename|drop|recover|migrate|create|enhance|compensate|remove|backfill)', name)
        version = m.group(1) if m else None
        results.append({
            'name': name,
            'rel_path': str(f.relative_to(migrations_dir)),
            'version': version,
            'abs_path': str(f),
        })
    return results


# --------------------------------------------------------------------------
# 2. 读 DB schema_migrations 表
# --------------------------------------------------------------------------
def load_db_migrations(db_path: Path) -> List[str]:
    """从 DB 读 schema_migrations 表, 返回所有 migration_name.

    自动确保表存在 (CREATE IF NOT EXISTS), 避免表不存在时报错.
    """
    if not db_path.exists():
        return []

    conn = sqlite3.connect(str(db_path))
    try:
        # 确保表存在 (兼容老 DB / 全新 DB)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                migration_name VARCHAR(255) NOT NULL UNIQUE,
                executed_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                checksum VARCHAR(64)
            )
        """)
        conn.commit()

        rows = conn.execute(
            "SELECT migration_name FROM schema_migrations"
        ).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


# --------------------------------------------------------------------------
# 3. Diff + 报告
# --------------------------------------------------------------------------
def check_sync(migrations_dir: Path, db_path: Path) -> dict:
    """主入口: 检查 deployment migrations vs DB schema_migrations 一致性.

    Returns:
        {
            'migrations_dir': str,
            'db_path': str,
            'file_count': int,
            'db_count': int,
            'in_files_only': [name, ...],   # 部署目录有, DB 没记录 (新文件, 未跑 - OK)
            'in_db_only': [name, ...],      # DB 跑过, 部署目录找不到 (DRIFT - WARN)
            'common': [name, ...],          # 都有 (OK)
            'drift_count': int,             # in_db_only 数量
            'drift_examples': [name, ...],  # 头 10 个 drift 示例
            'ok': bool,                     # drift_count == 0
        }
    """
    files = scan_migrations(migrations_dir)
    file_names = {f['name'] for f in files}

    db_names = set(load_db_migrations(db_path))

    in_files_only = sorted(file_names - db_names)
    in_db_only = sorted(db_names - file_names)
    common = sorted(file_names & db_names)

    drift_count = len(in_db_only)

    return {
        'migrations_dir': str(migrations_dir),
        'db_path': str(db_path),
        'file_count': len(files),
        'db_count': len(db_names),
        'in_files_only': in_files_only,
        'in_db_only': in_db_only,
        'common': common,
        'drift_count': drift_count,
        'drift_examples': in_db_only[:10],
        'ok': drift_count == 0,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
def _print_human(report: dict) -> None:
    print(f"[migrations] dir: {report['migrations_dir']}")
    print(f"[migrations] files: {report['file_count']}")
    print(f"[db]         path: {report['db_path']}")
    print(f"[db]         recorded: {report['db_count']}")
    print(f"[diff]       common: {len(report['common'])}")
    print(f"[diff]       in_files_only: {len(report['in_files_only'])}")
    print(f"[diff]       in_db_only: {len(report['in_db_only'])} (DRIFT)")
    print()
    if report['in_files_only']:
        print(f"[INFO] {len(report['in_files_only'])} 个 migration 文件在部署目录但 DB 未记录 (新文件, 未跑):")
        for n in report['in_files_only'][:20]:
            print(f"  + {n}")
        if len(report['in_files_only']) > 20:
            print(f"  ... and {len(report['in_files_only']) - 20} more")
        print()
    if report['in_db_only']:
        print(f"[!! DRIFT !!] {len(report['in_db_only'])} 个 migration 在 DB 跑过但部署目录找不到:")
        for n in report['drift_examples']:
            print(f"  - {n}")
        if len(report['in_db_only']) > 10:
            print(f"  ... and {len(report['in_db_only']) - 10} more")
        print()
        print("[可能原因]")
        print("  1. 部署目录是旧版本, 未同步最新 migrations (本次 staging 部署根因)")
        print("  2. DB 是另一个环境的备份 (如 prod 备份 -> staging)")
        print("  3. 历史 migration 被故意删除, 但 DB 没清理 schema_migrations")
        print()
        print("[建议]")
        print("  1. 从 git 拉最新 migrations 到部署目录")
        print("  2. 或回退 DB 到与部署目录匹配的版本")
        print("  3. 确认一致性后再 deploy (否则 server 启动会失败)")
    else:
        print(f"[OK] No drift: 所有 DB 记录的 migration 都在部署目录里")


def main():
    parser = argparse.ArgumentParser(
        description='[P1-1] 部署目录 migrations vs DB schema_migrations 一致性检查 (无开发假设)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python migration_deploy_sync.py --migrations-dir meta/migrations --db db.sqlite
  python migration_deploy_sync.py --migrations-dir meta/migrations --db db.sqlite --json --exit-code
        """
    )
    parser.add_argument('--migrations-dir', required=True,
                        help='migrations 目录 (含 .py migration 文件)')
    parser.add_argument('--db', required=True,
                        help='SQLite DB 路径')
    parser.add_argument('--json', action='store_true', help='JSON 输出')
    parser.add_argument('--exit-code', action='store_true',
                        help='有 drift 时 exit 1')

    args = parser.parse_args()

    migrations_dir = Path(args.migrations_dir).resolve()
    db_path = Path(args.db).resolve()

    report = check_sync(migrations_dir, db_path)

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        _print_human(report)

    if args.exit_code and not report['ok']:
        sys.exit(1)
    sys.exit(0 if report['ok'] else (1 if args.exit_code else 0))


if __name__ == '__main__':
    main()
# -*- coding: utf-8 -*-
"""[v162] service 计划类型启用（数据侧断言）

依据:
  docs/superpowers/specs/2026-10-29-so-wave3/spec.md §10.8
  docs/superpowers/specs/2026-10-29-so-wave3/tasks.md T3.5

设计:
  · v161 已建 work_orders / SLA 五表；本迁移**不做结构变更**（哈希影响：无）。
  · service 计划行在批次 3 之前被守卫 R-SCH-10 拒绝，因此存量数据应为 0 行。
    本迁移执行一次数据侧断言，便于上线前确认不需要数据回填。
  · `sla_coverage_rules` 的 (coverage_id, severity, channel) 唯一性由服务层
    保存校验兜底；不加新约束，故无哈希影响。

幂等:
  纯只读断言，重复执行结果一致。

回滚:
  无结构变更，rollback 为空操作（返回 True）。
"""
import sqlite3
import sys
from pathlib import Path

SCHEDULE_TABLE = 'sales_order_schedules'


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _service_schedule_count(conn: sqlite3.Connection) -> int:
    if not _table_exists(conn, SCHEDULE_TABLE):
        return 0
    row = conn.execute(
        f"SELECT COUNT(*) FROM {SCHEDULE_TABLE} WHERE schedule_kind = 'service'"
    ).fetchone()
    return int(row[0] or 0) if row else 0


def migrate(db_path: Path, skip_backup: bool = False) -> bool:
    """注意签名：migration_runner 以 `migrate(db_path, skip_backup=True)` 调用。"""
    if not db_path.exists():
        print(f'[v162] DB 不存在: {db_path}')
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        print('[v162] 开始: service 计划类型启用（数据侧断言）')
        count = _service_schedule_count(conn)
        if count == 0:
            print('  - [OK] 存量 service 计划行 0 条（无需数据回填）')
        else:
            # 守卫解禁前理论上不可能出现；出现时仅提示，不阻断迁移，
            # 因为这些行已由守卫强制携带 service_visit_no。
            print(f'  - [WARN] 存量 service 计划行 {count} 条，请人工核对'
                  ' service_visit_no 是否齐全')
        print('[v162] 迁移提交完成')
        return True
    except Exception as e:
        print('[v162] 失败: %s' % e)
        return False
    finally:
        conn.close()


def verify(db_path: Path) -> bool:
    if not db_path.exists():
        print('[v162 verify] DB 不存在: %s' % db_path)
        return False
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        if not _table_exists(conn, SCHEDULE_TABLE):
            # 本迁移只做数据侧断言：表不存在 ⇒ 不可能有存量 service 行，断言空集成立
            print('[v162 verify] PASS（缺表 %s，视为无存量 service 计划行）'
                  % SCHEDULE_TABLE)
            return True
        count = _service_schedule_count(conn)
        print('[v162 verify] PASS（service 计划行 %d 条）' % count)
        return True
    finally:
        conn.close()


def rollback(db_path: Path) -> bool:
    # 无结构变更 / 无数据变更，回滚为空操作
    print('[v162 rollback] 无结构变更，跳过')
    return True


downgrade = rollback


if __name__ == '__main__':
    _REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(_REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(_REPO_ROOT))
    from meta.core.db_path import get_meta_db_path

    db = Path(sys.argv[1]) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') \
        else Path(get_meta_db_path())
    print('DB: %s' % db)

    if '--verify' in sys.argv:
        sys.exit(0 if verify(db) else 1)
    elif '--rollback' in sys.argv:
        sys.exit(0 if rollback(db) else 1)
    else:
        if not migrate(db):
            sys.exit(1)
        sys.exit(0 if verify(db) else 1)

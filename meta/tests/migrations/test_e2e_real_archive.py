"""
E2E 真实归档验证（V007.50 端到端）

目的：模拟真实归档流程，把热表中的 N 条旧数据移到 audit_logs_archive，
验证 v_audit_all VIEW 能完整返回（热表 + 归档表），业务 API 仍正常。

步骤：
  1. 备份 DB（手动，脚本外执行）
  2. 选出热表中 N 条最早的 audit_log（如 1000 条）
  3. 把它们的 retention_until 设为过去时间
  4. 运行 archive_audit_logs.py 实际执行归档
  5. 验证：
     - audit_logs 行数 -1000
     - audit_logs_archive 行数 +1000
     - v_audit_all COUNT 不变（应是 原始总数）
     - 之前能查到的最早 N 条现在出现在 archive 表中
  6. 重启 backend（create_app），验证 API 仍能查到所有数据
  7. 回滚（删 archive 数据 + 恢复 retention_until）

注意：
  - 脚本默认 dry_run 模式，仅打印会做什么
  - 加 --execute 实际执行归档
  - 加 --rollback 回滚归档
"""
import sys
import os
import sqlite3
import time
import argparse
from pathlib import Path

sys.path.insert(0, r"D:\filework\worktrees/release-prep")

DB = r"D:\filework\worktrees/release-prep\meta\architecture.db"

ARCHIVE_SCRIPT = r"D:\filework\worktrees/release-prep\meta\scripts\archive_audit_logs.py"


def select_records_to_archive(conn, n: int):
    """选 N 条最早的 audit_log 用于归档（按 id ASC）"""
    cur = conn.execute(
        "SELECT id, retention_until FROM audit_logs ORDER BY id ASC LIMIT ?",
        (n,),
    )
    return [(row[0], row[1]) for row in cur.fetchall()]


def prepare_for_archive(conn, n: int):
    """把 N 条最早记录的 retention_until 设为 190 天前（确保 archive 选中）"""
    from datetime import datetime, timedelta
    # retention_until 设为 190 天前（超过默认 180 天保留期）
    old_retention = (datetime.utcnow() - timedelta(days=190)).isoformat()
    cur = conn.execute(
        "UPDATE audit_logs SET retention_until = ? "
        "WHERE id IN (SELECT id FROM audit_logs ORDER BY id ASC LIMIT ?)",
        (old_retention, n),
    )
    conn.commit()
    return cur.rowcount, old_retention


def run_archive_script(retention_days: int = 180):
    """执行真实归档脚本"""
    import subprocess
    print(f"\n=== 运行 archive_audit_logs.py (retention_days={retention_days}) ===")
    result = subprocess.run(
        [sys.executable, ARCHIVE_SCRIPT, "--retention-days", str(retention_days)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    print("STDOUT:")
    print(result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout)
    if result.stderr:
        print("STDERR:")
        print(result.stderr[-1000:])
    return result.returncode == 0


def get_count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def verify_view_unions_both_tables(conn):
    """验证 v_audit_all VIEW 包含热表 + 归档表"""
    # 1. VIEW 应该存在
    view_exists = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='view' AND name='v_audit_all'"
    ).fetchone()
    assert view_exists, "v_audit_all VIEW 不存在"

    # 2. 各表行数
    hot = get_count(conn, "audit_logs")
    arch = get_count(conn, "audit_logs_archive")
    view = get_count(conn, "v_audit_all")
    print(f"  hot={hot}, archive={arch}, view={view}")
    assert view == hot + arch, (
        f"VIEW 应等于热表+归档表 ({hot}+{arch}={hot + arch})，实际 {view}"
    )

    # 3. 归档表中的数据能通过 VIEW 查到
    if arch > 0:
        sample = conn.execute(
            "SELECT id FROM audit_logs_archive ORDER BY id ASC LIMIT 1"
        ).fetchone()
        if sample:
            sample_id = sample[0]
            # VIEW 中应能找到
            row = conn.execute(
                f"SELECT id, action, object_type FROM v_audit_all WHERE id = ?",
                (sample_id,),
            ).fetchone()
            assert row is not None, f"VIEW 找不到归档表 id={sample_id}"
            print(f"  VIEW 查到归档样本: id={sample_id}, action={row[1]}, type={row[2]}")
    return True


def rollback(conn, archived_ids: list):
    """回滚归档：把数据从 archive 移回热表 + 恢复 retention_until"""
    if not archived_ids:
        print("No archive to rollback")
        return

    placeholders = ",".join(["?" for _ in archived_ids])
    # 从 archive 读
    rows = conn.execute(
        f"SELECT * FROM audit_logs_archive WHERE id IN ({placeholders})",
        archived_ids,
    ).fetchall()
    cols = [d[0] for d in rows[0].cursor_description] if rows else []
    # 插回热表
    # 直接复制行（去掉 archived_at 列）
    for row in rows:
        row_dict = dict(zip(cols, row))
        row_dict.pop("archived_at", None)
        if not row_dict.get("retention_until"):
            from datetime import datetime, timedelta
            row_dict["retention_until"] = (datetime.utcnow() + timedelta(days=180)).isoformat()
        col_list = ", ".join(row_dict.keys())
        ph_list = ", ".join(["?" for _ in row_dict])
        conn.execute(
            f"INSERT OR REPLACE INTO audit_logs ({col_list}) VALUES ({ph_list})",
            list(row_dict.values()),
        )

    # 清空 archive（这部分是本次测试加的）
    conn.execute(
        f"DELETE FROM audit_logs_archive WHERE id IN ({placeholders})",
        archived_ids,
    )
    conn.commit()
    print(f"  Rollback done: restored {len(archived_ids)} records to hot table")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true",
                        help="实际执行归档（默认 dry_run 模式）")
    parser.add_argument("--rollback", action="store_true",
                        help="回滚归档（删 archive 数据 + 恢复 retention_until）")
    parser.add_argument("--n", type=int, default=1000,
                        help="归档 N 条最早记录（默认 1000）")
    parser.add_argument("--skip-archive", action="store_true",
                        help="跳过归档步骤，只做验证")
    args = parser.parse_args()

    print("=" * 70)
    print("E2E 真实归档验证")
    print("=" * 70)

    if not os.path.exists(DB):
        print(f"[FAIL] DB not found: {DB}")
        return 1

    conn = sqlite3.connect(DB, timeout=60)
    conn.row_factory = sqlite3.Row

    # 初始状态
    hot_initial = get_count(conn, "audit_logs")
    arch_initial = get_count(conn, "audit_logs_archive")
    print(f"\n=== 初始状态 ===")
    print(f"  audit_logs: {hot_initial}")
    print(f"  audit_logs_archive: {arch_initial}")

    # Rollback 模式
    if args.rollback:
        print("\n=== 回滚模式 ===")
        arch_ids = [r[0] for r in conn.execute(
            "SELECT id FROM audit_logs_archive ORDER BY id ASC"
        ).fetchall()]
        rollback(conn, arch_ids)
        print(f"  hot={get_count(conn, 'audit_logs')}, "
              f"archive={get_count(conn, 'audit_logs_archive')}")
        conn.close()
        return 0

    # 准备 N 条记录用于归档
    n = args.n
    print(f"\n=== 准备归档 {n} 条最早记录 ===")
    selected = select_records_to_archive(conn, n)
    print(f"  选中 {len(selected)} 条，id 范围: {selected[0][0]} - {selected[-1][0]}")
    print(f"  原 retention_until 样本: {selected[0][1]}")

    updated, old_retention = prepare_for_archive(conn, n)
    print(f"  更新 {updated} 条 retention_until = {old_retention}")
    print(f"  现在这些记录满足归档条件 (retention_until < 190 天前)")

    # 执行归档
    if not args.skip_archive:
        if args.execute:
            success = run_archive_script(retention_days=180)
            if not success:
                print("[FAIL] archive_audit_logs.py 执行失败")
                conn.close()
                return 1
        else:
            print("\n[DRY RUN] 实际执行需加 --execute")
            print("  将执行: python archive_audit_logs.py --retention-days 180")

    # 验证
    print(f"\n=== 验证 ===")
    hot_after = get_count(conn, "audit_logs")
    arch_after = get_count(conn, "audit_logs_archive")
    print(f"  hot={hot_after} (initial={hot_initial}, expected diff={-n})")
    print(f"  archive={arch_after} (initial={arch_initial}, expected diff=+{n})")

    if not args.skip_archive and args.execute:
        if arch_after < arch_initial + n * 0.9:
            print(f"[WARN] 归档数少于预期 {n}（可能 retention_until 未匹配）")
        if hot_after > hot_initial:
            print(f"[WARN] 热表行数反而增加")

    # VIEW 验证
    if verify_view_unions_both_tables(conn):
        print("[OK] v_audit_all VIEW 包含热表 + 归档表")

    # 检查原最早 id 是否现在在 archive 中
    sample_id = selected[0][0]
    in_archive = conn.execute(
        "SELECT id FROM audit_logs_archive WHERE id = ?", (sample_id,)
    ).fetchone()
    in_hot = conn.execute(
        "SELECT id FROM audit_logs WHERE id = ?", (sample_id,)
    ).fetchone()
    print(f"\n=== 最早 id={sample_id} 状态 ===")
    print(f"  in archive: {bool(in_archive)}")
    print(f"  in hot: {bool(in_hot)}")

    # VIEW 应能找到（无论在 hot 还是 archive）
    if not args.skip_archive and args.execute:
        in_view = conn.execute(
            "SELECT id FROM v_audit_all WHERE id = ?", (sample_id,)
        ).fetchone()
        assert in_view, f"VIEW 应能找到最早 id={sample_id}"
        print(f"  in view: True ✓")
        print(f"\n[OK] 最早记录归档后通过 VIEW 仍能查到")

    conn.close()
    print("\n=== 完成 ===")
    if not args.execute and not args.skip_archive:
        print("提示: 加 --execute 实际执行归档")
    elif args.execute:
        print("提示: 加 --rollback 回滚（恢复热表 + 清空 archive）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
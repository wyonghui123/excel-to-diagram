# -*- coding: utf-8 -*-
"""
[2026-06-20 P2.2] 回填剩余的 system 类 tx_id 缺失记录

策略:
- 同一秒内, 相同 (object_type, action, user_name) 的记录视为同一事务
- 启发式: 2 秒窗口 + 上面 3 个字段分组
- 单独记录 (无邻近) 也分配新 tx_id
"""
import sqlite3
import sys
import uuid
import re
from datetime import datetime, timedelta

DB_PATH = 'meta/architecture.db'
WINDOW_SEC = 2

def parse_iso(ts):
    """解析 SQLite ISO 时间字符串"""
    if not ts:
        return None
    s = ts.replace('Z', '+00:00')
    # 截断到微秒 (sqlite 精度限制)
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        # 尝试常见格式
        for fmt in ('%Y-%m-%dT%H:%M:%S.%f', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S.%f', '%Y-%m-%d %H:%M:%S'):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        return None


def heuristic_backfill(dry_run=True):
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # 拉所有 tx_id 为空的记录
    rows = cur.execute("""
        SELECT id, object_type, action, user_name, ip_address, created_at
        FROM audit_logs
        WHERE transaction_id IS NULL OR transaction_id = ''
        ORDER BY user_name, object_type, action, created_at
    """).fetchall()

    print(f'[INFO] Found {len(rows)} records to backfill')

    # 按 (user_name, object_type, action) 分组
    groups = {}
    for r in rows:
        key = (r[2], r[1], r[3])  # (action, object_type, user_name)
        groups.setdefault(key, []).append(r)

    updates = []
    merged_count = 0
    new_count = 0

    for key, recs in groups.items():
        # 按时间排序
        recs.sort(key=lambda x: parse_iso(x[5]) or datetime.min)

        current_window = []  # (rec_id, timestamp)
        current_tx = None

        for rec in recs:
            rid, otype, action, uname, ip, ts = rec
            t = parse_iso(ts)

            # 检查是否在当前窗口内
            matched = False
            if current_window and current_tx and t:
                anchor_id, anchor_t = current_window[0]
                if abs((t - anchor_t).total_seconds()) <= WINDOW_SEC:
                    # 也在 user_name/object_type 一致
                    matched = True

            if matched:
                # 合并到当前 tx
                updates.append((current_tx, rid))
                current_window.append((rid, t))
                merged_count += 1
            else:
                # 创建新 tx
                current_tx = f"tx_p22_{uuid.uuid4().hex[:16]}"
                updates.append((current_tx, rid))
                current_window = [(rid, t)]
                new_count += 1

    print(f'[INFO] Plan: {len(updates)} updates')
    print(f'        - merged into existing: {merged_count}')
    print(f'        - new tx_id assigned:   {new_count}')

    # 打印几个示例
    if updates:
        print('[SAMPLE]')
        for tx, rid in updates[:5]:
            print(f'  id={rid} tx_id={tx}')
        if len(updates) > 5:
            print(f'  ... +{len(updates)-5} more')

    if dry_run:
        print('[DRY-RUN] No changes applied')
        con.close()
        return 0

    # 执行更新
    print(f'[EXEC] Applying {len(updates)} updates...')
    cur.executemany("UPDATE audit_logs SET transaction_id = ? WHERE id = ?", updates)
    con.commit()

    # 验证
    remaining = cur.execute("""
        SELECT COUNT(*) FROM audit_logs
        WHERE transaction_id IS NULL OR transaction_id = ''
    """).fetchone()[0]
    print(f'[OK] Updated {len(updates)} records')
    print(f'[OK] Remaining NULL tx_id: {remaining}')

    # 覆盖率
    total = cur.execute("SELECT COUNT(*) FROM audit_logs").fetchone()[0]
    with_tx = cur.execute("""
        SELECT COUNT(*) FROM audit_logs
        WHERE transaction_id IS NOT NULL AND transaction_id != ''
    """).fetchone()[0]
    print(f'[COVERAGE] {with_tx}/{total} = {with_tx*100/total:.2f}%')

    con.close()
    return len(updates)


if __name__ == '__main__':
    dry_run = '--execute' not in sys.argv
    if dry_run:
        print('[DRY-RUN MODE] Use --execute to actually apply')
    else:
        print('[EXECUTE MODE] Changes will be committed to DB')
    print()
    sys.exit(heuristic_backfill(dry_run=dry_run))
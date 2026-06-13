#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_hash_chain.py — 防篡改 hash chain (FR-014, TBD-1 决策)

设计:
  - prev_hash = 上一条 row_hash, 首条为 "0" * 64
  - row_hash = sha256(prev_hash + canonical_json(payload))
  - 写入 audit_logs.prev_hash / row_hash
  - verify_chain(start_id): 从 start_id 算到最新, 不匹配返告警

API:
  - compute_row_hash(prev_hash, record_dict) -> str
  - backfill_chain(conn, start_id=0) -> int  # 返处理的行数
  - verify_chain(conn, start_id=0) -> List[dict]  # 返篡改列表 (空=OK)
"""
import sqlite3
import hashlib
import json
from pathlib import Path
from typing import List, Dict, Any


# 字段顺序必须稳定 (canonical)
# 注: action_kind / parent_action_id 在 AuditRecord (v2 设计) 里有, 但 schema 没加, 暂排除
HASH_FIELDS = [
    "object_type", "object_id", "action", "field_name",
    "old_value", "new_value", "user_id", "user_name",
    "ip_address", "user_agent", "trace_id", "transaction_id",
    "agent_id", "agent_session_id", "tool_call_id",
    "log_category", "log_level", "outcome",
    "parent_object_type", "parent_object_id",
    "cascade_root_id", "cascade_root_action", "created_at",
    "extra_data",  # 字典会被 JSON 序列化
]


def _canonical_payload(record: Dict[str, Any]) -> str:
    """构造规范化的 payload 字符串 (字段顺序固定)"""
    payload = {}
    for f in HASH_FIELDS:
        v = record.get(f)
        # 字典 / 列表 → JSON
        if isinstance(v, (dict, list)):
            payload[f] = json.dumps(v, ensure_ascii=False, sort_keys=True)
        else:
            payload[f] = v if v is not None else ""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def compute_row_hash(prev_hash: str, record: Dict[str, Any]) -> str:
    """计算单条记录的 row_hash

    Args:
        prev_hash: 上一条的 row_hash, 首条为 "0" * 64
        record: 当前记录的 dict
    Returns:
        64 字符的 SHA-256 hex string
    """
    payload = _canonical_payload(record)
    raw = (prev_hash + payload).encode('utf-8')
    return hashlib.sha256(raw).hexdigest()


def backfill_chain(conn: sqlite3.Connection, start_id: int = 0, batch: int = 500) -> int:
    """从 start_id 开始 backfill 全部 prev_hash/row_hash

    Returns:
        处理的行数
    """
    cur = conn.execute(
        "SELECT id FROM audit_logs WHERE id >= ? ORDER BY id ASC",
        (start_id,),
    )
    all_ids = [r[0] for r in cur.fetchall()]
    if not all_ids:
        return 0

    # 找 start_id 之前的最新 row_hash (链起点)
    prev_hash = "0" * 64
    if start_id > 0:
        cur = conn.execute(
            "SELECT row_hash FROM audit_logs WHERE id < ? ORDER BY id DESC LIMIT 1",
            (start_id,),
        )
        row = cur.fetchone()
        if row and row[0]:
            prev_hash = row[0]

    processed = 0
    for i in range(0, len(all_ids), batch):
        ids = all_ids[i:i + batch]
        placeholders = ','.join('?' for _ in ids)
        cur = conn.execute(
            f"SELECT {', '.join(HASH_FIELDS)}, id FROM audit_logs "
            f"WHERE id IN ({placeholders}) ORDER BY id ASC",
            ids,
        )
        rows = cur.fetchall()
        for row in rows:
            rec_id = row[-1]
            rec = {f: row[idx] for idx, f in enumerate(HASH_FIELDS)}
            new_hash = compute_row_hash(prev_hash, rec)
            conn.execute(
                "UPDATE audit_logs SET prev_hash=?, row_hash=? WHERE id=?",
                (prev_hash, new_hash, rec_id),
            )
            prev_hash = new_hash
            processed += 1
        conn.commit()
        print(f"  [BACKFILL] {processed}/{len(all_ids)} done")
    return processed


def verify_chain(conn: sqlite3.Connection, start_id: int = 0) -> List[Dict[str, Any]]:
    """验证 hash chain 是否被篡改

    Returns:
        篡改的记录列表 (空 = OK)
    """
    cur = conn.execute(
        "SELECT id FROM audit_logs WHERE id >= ? ORDER BY id ASC",
        (start_id,),
    )
    all_ids = [r[0] for r in cur.fetchall()]
    if not all_ids:
        return []

    prev_hash = "0" * 64
    if start_id > 0:
        cur = conn.execute(
            "SELECT row_hash FROM audit_logs WHERE id < ? ORDER BY id DESC LIMIT 1",
            (start_id,),
        )
        row = cur.fetchone()
        if row and row[0]:
            prev_hash = row[0]

    tampered = []
    placeholders = ','.join('?' for _ in all_ids)
    cur = conn.execute(
        f"SELECT id, prev_hash, row_hash, {', '.join(HASH_FIELDS)} FROM audit_logs "
        f"WHERE id IN ({placeholders}) ORDER BY id ASC",
        all_ids,
    )
    for row in cur.fetchall():
        rec_id = row[0]
        stored_prev = row[1]
        stored_hash = row[2]
        rec = {f: row[idx + 3] for idx, f in enumerate(HASH_FIELDS)}
        # 1. prev_hash 必须等于上一条的 row_hash
        if stored_prev != prev_hash:
            tampered.append({
                "id": rec_id, "type": "prev_hash_mismatch",
                "expected": prev_hash, "actual": stored_prev,
            })
            # 用 stored_hash 继续, 不要中断
            prev_hash = stored_hash or "0" * 64
            continue
        # 2. row_hash 必须等于 sha256(prev + payload)
        computed = compute_row_hash(prev_hash, rec)
        if stored_hash != computed:
            tampered.append({
                "id": rec_id, "type": "row_hash_mismatch",
                "expected": computed, "actual": stored_hash,
            })
        prev_hash = stored_hash or "0" * 64
    return tampered


# ============ 自测 ============

if __name__ == "__main__":
    from pathlib import Path
    DB = Path(__file__).parent.parent / "architecture.db"
    conn = sqlite3.connect(str(DB))
    try:
        print("=== 1. Backfill hash chain ===")
        n = backfill_chain(conn)
        print(f"  处理 {n} 条\n")

        print("=== 2. Verify chain ===")
        tampered = verify_chain(conn)
        if tampered:
            print(f"  [ALERT] 检测到 {len(tampered)} 条篡改:")
            for t in tampered[:5]:
                print(f"    ID={t['id']} {t['type']}: expected={t['expected'][:16]}... actual={t['actual'][:16] if t['actual'] else None}...")
        else:
            print("  [OK] chain 完整无篡改")

        # 3. 模拟篡改 (修改 1 条) → verify 应能检出
        print("\n=== 3. 篡改模拟 ===")
        cur = conn.execute("SELECT id FROM audit_logs WHERE row_hash IS NOT NULL LIMIT 1")
        first_id = cur.fetchone()
        if first_id:
            tid = first_id[0]
            cur = conn.execute("SELECT new_value FROM audit_logs WHERE id=?", (tid,))
            old_val = cur.fetchone()[0]
            new_val = (old_val or "") + "_TAMPERED"
            conn.execute("UPDATE audit_logs SET new_value=? WHERE id=?", (new_val, tid))
            conn.commit()
            print(f"  模拟改 ID={tid} new_value")
            tampered2 = verify_chain(conn, start_id=tid)
            if tampered2:
                print(f"  [DETECTED] verify_chain 检出 {len(tampered2)} 条篡改")
            else:
                print("  [MISS] verify_chain 未检出 (BUG)")
            # 还原
            conn.execute("UPDATE audit_logs SET new_value=? WHERE id=?", (old_val, tid))
            conn.execute("UPDATE audit_logs SET row_hash=NULL, prev_hash=NULL WHERE id=?", (tid,))
            conn.commit()
            # 从 tid 之前再 backfill
            backfill_chain(conn, start_id=tid)
            print("  已还原")
    finally:
        conn.close()

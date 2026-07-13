#!/usr/bin/env python3
"""
audit_recovery.py - 基于 audit_logs 的通用对象恢复框架 [V007.49-C 2026-07-13]
[L13.2 fix]

背景: 实测发现 audit_logs 已经是事实上的"软删除快照表"
  - 主实体 DELETE 含完整 deleted_data (id/code/name/...)
  - DISSOCIATE 含 through_table + fk_column + target_id
  - 配合 L13.1 audit 缺口补全, 可 100% 恢复

API:
  - find_recoverable(object_type, object_id) -> dict
  - preview(object_type, object_id) -> list[str]
  - restore(object_type, object_id, dry_run=True, skip_warnings=False) -> dict
"""
import sqlite3
import json
import os
import sys
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple

DB_PATH = "/opt/app/deployments/meta/architecture.db"
RETENTION_DAYS = 365  # 1 年


class AuditRecovery:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"DB not found: {db_path}")
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def find_recoverable(self, object_type: str, object_id: int) -> Dict[str, Any]:
        """查询可恢复信息, 返回: {main_record, relations, audit_log_ids, warnings, confidence, recoverable}"""
        result = {
            "object_type": object_type,
            "object_id": object_id,
            "main_record": None,
            "relations": [],
            "audit_log_ids": [],
            "warnings": [],
            "confidence": 0.0,
            "recoverable": False,
            "checked_at": datetime.now().isoformat(),
        }
        cursor = self.conn.cursor()

        # 1. 查主实体最新 DELETE 记录
        cursor.execute("""
            SELECT id, extra_data, user_name, created_at, retention_until
            FROM audit_logs
            WHERE action = 'DELETE' AND field_name = '_record'
              AND object_type = ? AND object_id = ?
              AND created_at > datetime('now', ?)
            ORDER BY id DESC LIMIT 1
        """, (object_type, object_id, f'-{RETENTION_DAYS} days'))
        row = cursor.fetchone()
        if not row:
            result["warnings"].append(f"no DELETE audit_log for {object_type}#{object_id} in last {RETENTION_DAYS} days")
            return result

        try:
            extra = json.loads(row['extra_data'])
            deleted_data = extra.get('deleted_data', {})
            result["main_record"] = {
                "data": deleted_data,
                "audit_log_id": row['id'],
                "deleted_by": row['user_name'],
                "deleted_at": row['created_at'],
                "retention_until": row['retention_until'],
            }
            result["audit_log_ids"].append(row['id'])
        except Exception as e:
            result["warnings"].append(f"parse main_record failed: {e}")
            return result

        # 2. 查所有 DISSOCIATE 关联记录 (按 cascade_reason 过滤)
        cursor.execute("""
            SELECT id, field_name, old_value, extra_data, created_at
            FROM audit_logs
            WHERE action = 'DISSOCIATE' AND object_type = ?
              AND object_id = ?
              AND json_extract(extra_data, '$.cascade_reason') LIKE ?
            ORDER BY id
        """, (object_type, object_id, f'%{object_type}#{object_id} deletion%'))
        total_relations = 0
        tables_covered = set()
        for row in cursor.fetchall():
            try:
                old_value = json.loads(row['old_value'])
                extra = json.loads(row['extra_data'])
                target_type = old_value.get('target_type')
                target_id = old_value.get('target_id')
                through_table = extra.get('through_table')
                fk_column = extra.get('fk_column')
                if not (target_id and through_table and fk_column):
                    result["warnings"].append(f"incomplete DISSOCIATE record #{row['id']}")
                    continue
                result["relations"].append({
                    "audit_log_id": row['id'],
                    "through_table": through_table,
                    "fk_column": fk_column,
                    "target_type": target_type,
                    "target_id": target_id,
                    "field_name": row['field_name'],
                    "dissociated_at": row['created_at'],
                })
                result["audit_log_ids"].append(row['id'])
                total_relations += 1
                tables_covered.add(through_table)
            except Exception as e:
                result["warnings"].append(f"parse DISSOCIATE #{row['id']} failed: {e}")

        result["total_relations"] = total_relations
        result["tables_covered"] = list(tables_covered)

        # 3. 检查关联表的当前状态 (看关联是否真的没了)
        for rel in result["relations"]:
            try:
                cursor.execute(
                    f"SELECT COUNT(*) AS cnt FROM {rel['through_table']} WHERE {rel['fk_column']} = ?",
                    (object_id,)
                )
                current_count = cursor.fetchone()['cnt']
                rel["current_count_after_dissoc"] = current_count
            except Exception as e:
                rel["current_count_after_dissoc"] = f"ERR: {e}"

        # 4. 计算 confidence (主实体 50% + 关联 50%)
        main_ok = 1 if result["main_record"] else 0
        # 每张表覆盖 +10%, 最多 50%
        table_score = min(0.5, len(tables_covered) * 0.1)
        # 如果有 warnings, 扣分
        warning_penalty = min(0.2, len(result["warnings"]) * 0.05)
        result["confidence"] = round(0.5 * main_ok + table_score - warning_penalty, 2)
        result["recoverable"] = result["main_record"] is not None and result["confidence"] >= 0.5

        return result

    def preview(self, object_type: str, object_id: int) -> List[str]:
        """生成预览 SQL 列表 (不执行)"""
        info = self.find_recoverable(object_type, object_id)
        if not info["recoverable"]:
            return [f"-- NOT RECOVERABLE: {', '.join(info['warnings'])}"]

        sqls = []
        # 1. INSERT 主实体
        main = info["main_record"]["data"]
        if main:
            cols = list(main.keys())
            vals = [self._sql_value(v) for v in main.values()]
            sqls.append(
                f"INSERT INTO {object_type} ({', '.join(cols)}) VALUES ({', '.join(vals)});"
            )
        # 2. INSERT 关联
        for rel in info["relations"]:
            sqls.append(
                f"INSERT INTO {rel['through_table']} ({rel['fk_column']}, {rel['field_name']}) "
                f"VALUES ({object_id}, {rel['target_id']});"
            )
        return sqls

    def restore(self, object_type: str, object_id: int,
                dry_run: bool = True,
                skip_warnings: bool = False) -> Dict[str, Any]:
        """执行恢复 (dry_run=True 默认只预览)"""
        info = self.find_recoverable(object_type, object_id)
        result = {
            "object_type": object_type,
            "object_id": object_id,
            "recoverable": info["recoverable"],
            "confidence": info["confidence"],
            "warnings": info["warnings"],
            "restored": 0,
            "skipped": 0,
            "sql_executed": [],
            "error": None,
        }
        if not info["recoverable"]:
            result["error"] = "not recoverable"
            return result
        if not skip_warnings and info["warnings"]:
            result["error"] = f"warnings present: {info['warnings']}"
            return result

        sqls = self.preview(object_type, object_id)
        result["sqls"] = sqls

        if dry_run:
            result["dry_run"] = True
            result["note"] = "Set dry_run=False to actually execute"
            return result

        # 实际执行
        cursor = self.conn.cursor()
        try:
            for sql in sqls:
                if sql.startswith('--'):
                    continue
                try:
                    cursor.execute(sql)
                    result["restored"] += 1
                    result["sql_executed"].append(sql)
                except Exception as e:
                    result["skipped"] += 1
                    result["warnings"].append(f"exec failed: {sql[:100]}: {e}")
            self.conn.commit()
        except Exception as e:
            self.conn.rollback()
            result["error"] = f"txn failed: {e}"
        return result

    def _sql_value(self, v: Any) -> str:
        if v is None:
            return "NULL"
        if isinstance(v, (int, float)):
            return str(v)
        if isinstance(v, bool):
            return "1" if v else "0"
        s = str(v).replace("'", "''")
        return f"'{s}'"


def main():
    """CLI: audit_recovery.py find/preview/restore <object_type> <object_id>"""
    if len(sys.argv) < 4:
        print("Usage:")
        print("  audit_recovery.py find    <object_type> <object_id>")
        print("  audit_recovery.py preview <object_type> <object_id>")
        print("  audit_recovery.py restore <object_type> <object_id> [--apply]")
        sys.exit(1)

    action = sys.argv[1]
    object_type = sys.argv[2]
    object_id = int(sys.argv[3])
    apply = "--apply" in sys.argv

    with AuditRecovery() as ar:
        if action == "find":
            info = ar.find_recoverable(object_type, object_id)
            print(json.dumps(info, indent=2, ensure_ascii=False))
        elif action == "preview":
            sqls = ar.preview(object_type, object_id)
            for sql in sqls:
                print(sql)
        elif action == "restore":
            result = ar.restore(object_type, object_id, dry_run=not apply)
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"Unknown action: {action}")
            sys.exit(1)


if __name__ == "__main__":
    main()
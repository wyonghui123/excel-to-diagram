# -*- coding: utf-8 -*-
"""
PermissionRuleV2DAO — permission_rules_v2 表的 CRUD 操作

[Phase 3 P3.1] 为前端 UnifiedPermissionPanel 提供数据访问层

[表结构] (见 meta/migrations/add_permission_rules_v2.py)
    id, role_id, resource_type, permission_level,
    include_conditions, exclude_conditions,
    derivation_mode, source, created_at, updated_at
"""
import json
import sqlite3
from typing import Any, Dict, List, Optional


class PermissionRuleV2DAO:
    """permission_rules_v2 表的 CRUD"""

    def __init__(self, db_path: str):
        self._db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def list_by_role(
        self, role_id: int, resource_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """按 role_id 查询规则列表"""
        sql = 'SELECT * FROM permission_rules_v2 WHERE role_id = ?'
        params: List[Any] = [role_id]
        if resource_type:
            sql += ' AND resource_type = ?'
            params.append(resource_type)
        sql += ' ORDER BY id'
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def list_all(self, resource_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """查询全部规则"""
        sql = 'SELECT * FROM permission_rules_v2'
        params: List[Any] = []
        if resource_type:
            sql += ' WHERE resource_type = ?'
            params.append(resource_type)
        sql += ' ORDER BY id'
        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_dict(r) for r in rows]

    def get(self, rule_id: int) -> Optional[Dict[str, Any]]:
        """查询单条规则"""
        with self._connect() as conn:
            row = conn.execute(
                'SELECT * FROM permission_rules_v2 WHERE id = ?', [rule_id]
            ).fetchone()
            return self._row_to_dict(row) if row else None

    def create(
        self,
        role_id: int,
        resource_type: str,
        permission_level: str = 'read',
        include_conditions: Optional[List[Dict]] = None,
        exclude_conditions: Optional[List[Dict]] = None,
        derivation_mode: str = 'static',
        source: str = 'manual',
    ) -> int:
        """创建规则, 返回新 id"""
        inc_json = json.dumps(include_conditions or [], ensure_ascii=False)
        exc_json = json.dumps(exclude_conditions or [], ensure_ascii=False)
        with self._connect() as conn:
            cursor = conn.execute(
                '''INSERT INTO permission_rules_v2
                   (role_id, resource_type, permission_level,
                    include_conditions, exclude_conditions,
                    derivation_mode, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?)''',
                [role_id, resource_type, permission_level,
                 inc_json, exc_json, derivation_mode, source],
            )
            conn.commit()
            return cursor.lastrowid

    def update(
        self,
        rule_id: int,
        permission_level: Optional[str] = None,
        include_conditions: Optional[List[Dict]] = None,
        exclude_conditions: Optional[List[Dict]] = None,
        derivation_mode: Optional[str] = None,
        source: Optional[str] = None,
    ) -> int:
        """更新规则 (只更新非 None 字段), 返回受影响行数"""
        sets: List[str] = []
        params: List[Any] = []
        if permission_level is not None:
            sets.append('permission_level = ?')
            params.append(permission_level)
        if include_conditions is not None:
            sets.append('include_conditions = ?')
            params.append(json.dumps(include_conditions, ensure_ascii=False))
        if exclude_conditions is not None:
            sets.append('exclude_conditions = ?')
            params.append(json.dumps(exclude_conditions, ensure_ascii=False))
        if derivation_mode is not None:
            sets.append('derivation_mode = ?')
            params.append(derivation_mode)
        if source is not None:
            sets.append('source = ?')
            params.append(source)
        if not sets:
            return 0
        sets.append('updated_at = CURRENT_TIMESTAMP')
        params.append(rule_id)
        with self._connect() as conn:
            cursor = conn.execute(
                f'UPDATE permission_rules_v2 SET {", ".join(sets)} WHERE id = ?',
                params,
            )
            conn.commit()
            return cursor.rowcount

    def delete(self, rule_id: int) -> int:
        """删除规则, 返回受影响行数"""
        with self._connect() as conn:
            cursor = conn.execute(
                'DELETE FROM permission_rules_v2 WHERE id = ?', [rule_id]
            )
            conn.commit()
            return cursor.rowcount

    def _row_to_dict(self, row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        # 解析 JSON 字段
        for field in ('include_conditions', 'exclude_conditions'):
            if d.get(field):
                try:
                    d[field] = json.loads(d[field])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d

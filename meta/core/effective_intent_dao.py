# -*- coding: utf-8 -*-
"""
EffectiveIntentDAO

role_effective_intents 表的 CRUD 操作。

[表结构]
  role_effective_intents:
    role_id, bo_id, action_name   — 联合唯一键
    data_scope                    — JSON: {include: [...], exclude: [...]}
    derivation_mode               — static | dynamic
    source                        — manual | derived | template
    is_stale                      — 是否需要重推导

[设计原则]
  - data_scope 以 JSON 存储, 保持灵活性
  - upsert 语义: 存在则覆盖, 不存在则插入
  - stale 标记用于推导管道的增量更新
"""
import json
import sqlite3
from typing import Any, Dict, List, Optional


class EffectiveIntentDAO:
    """role_effective_intents 表 DAO"""

    def __init__(self, db_path: str):
        self._db_path = db_path

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def upsert(
        self,
        role_id: int,
        bo_id: str,
        action_name: str,
        data_scope: Dict[str, Any],
        derivation_mode: str = 'static',
        source: str = 'derived',
    ) -> None:
        """写入或覆盖 Intent (upsert 语义)

        Args:
            role_id: 角色 ID
            bo_id: 业务对象 ID
            action_name: 操作名称 (read/write/delete/...)
            data_scope: 数据范围 {include: [...], exclude: [...]}
            derivation_mode: static (显式值) | dynamic (CHILDREN_OF)
            source: manual | derived | template
        """
        scope_json = json.dumps(data_scope, ensure_ascii=False)

        with self._get_conn() as conn:
            conn.execute(
                '''
                INSERT INTO role_effective_intents
                    (role_id, bo_id, action_name, data_scope, derivation_mode, source, is_stale)
                VALUES (?, ?, ?, ?, ?, ?, 0)
                ON CONFLICT (role_id, bo_id, action_name)
                DO UPDATE SET
                    data_scope = excluded.data_scope,
                    derivation_mode = excluded.derivation_mode,
                    source = excluded.source,
                    is_stale = 0,
                    updated_at = CURRENT_TIMESTAMP
                ''',
                [role_id, bo_id, action_name, scope_json, derivation_mode, source],
            )
            conn.commit()

    def list_for_role(self, role_id: int) -> List[Dict[str, Any]]:
        """列出角色的所有 Intent"""
        with self._get_conn() as conn:
            rows = conn.execute(
                'SELECT * FROM role_effective_intents WHERE role_id = ? ORDER BY bo_id, action_name',
                [role_id],
            ).fetchall()
            return [dict(r) for r in rows]

    def get_for_bo_action(
        self,
        role_id: int,
        bo_id: str,
        action_name: str,
    ) -> List[Dict[str, Any]]:
        """查询特定 bo+action 的 Intent"""
        with self._get_conn() as conn:
            rows = conn.execute(
                '''
                SELECT * FROM role_effective_intents
                WHERE role_id = ? AND bo_id = ? AND action_name = ?
                ''',
                [role_id, bo_id, action_name],
            ).fetchall()
            return [dict(r) for r in rows]

    def get_intents(
        self,
        role_id: int,
        bo_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """查询角色的 Intent (可按 bo_id 过滤)"""
        if bo_id:
            with self._get_conn() as conn:
                rows = conn.execute(
                    'SELECT * FROM role_effective_intents WHERE role_id = ? AND bo_id = ?',
                    [role_id, bo_id],
                ).fetchall()
        else:
            with self._get_conn() as conn:
                rows = conn.execute(
                    'SELECT * FROM role_effective_intents WHERE role_id = ?',
                    [role_id],
                ).fetchall()
        return [dict(r) for r in rows]

    def mark_stale(self, role_id: int) -> int:
        """标记角色的所有 Intent 为 stale (需要重推导)

        Returns:
            受影响的行数
        """
        with self._get_conn() as conn:
            cursor = conn.execute(
                'UPDATE role_effective_intents SET is_stale = 1, updated_at = CURRENT_TIMESTAMP '
                'WHERE role_id = ?',
                [role_id],
            )
            conn.commit()
            return cursor.rowcount

    def clear_stale(self, role_id: int) -> int:
        """清除 stale 标记

        Returns:
            受影响的行数
        """
        with self._get_conn() as conn:
            cursor = conn.execute(
                'UPDATE role_effective_intents SET is_stale = 0, updated_at = CURRENT_TIMESTAMP '
                'WHERE role_id = ?',
                [role_id],
            )
            conn.commit()
            return cursor.rowcount

    def get_stale_roles(self) -> List[int]:
        """获取所有有 stale Intent 的角色 ID"""
        with self._get_conn() as conn:
            rows = conn.execute(
                'SELECT DISTINCT role_id FROM role_effective_intents WHERE is_stale = 1'
            ).fetchall()
            return [r[0] for r in rows]

    def delete_for_role(self, role_id: int) -> int:
        """删除角色的所有 Intent

        Returns:
            删除的行数
        """
        with self._get_conn() as conn:
            cursor = conn.execute(
                'DELETE FROM role_effective_intents WHERE role_id = ?',
                [role_id],
            )
            conn.commit()
            return cursor.rowcount

    def delete_for_bo_action(
        self,
        role_id: int,
        bo_id: str,
        action_name: str,
    ) -> int:
        """删除特定 bo+action 的 Intent"""
        with self._get_conn() as conn:
            cursor = conn.execute(
                'DELETE FROM role_effective_intents '
                'WHERE role_id = ? AND bo_id = ? AND action_name = ?',
                [role_id, bo_id, action_name],
            )
            conn.commit()
            return cursor.rowcount

    def count_for_role(self, role_id: int) -> int:
        """统计角色的 Intent 数量"""
        with self._get_conn() as conn:
            row = conn.execute(
                'SELECT COUNT(*) FROM role_effective_intents WHERE role_id = ?',
                [role_id],
            ).fetchone()
            return row[0]
